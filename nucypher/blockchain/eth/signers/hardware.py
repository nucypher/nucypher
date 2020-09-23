"""
 This file is part of nucypher.

 nucypher is free software: you can redistribute it and/or modify
 it under the terms of the GNU Affero General Public License as published by
 the Free Software Foundation, either version 3 of the License, or
 (at your option) any later version.

 nucypher is distributed in the hope that it will be useful,
 but WITHOUT ANY WARRANTY; without even the implied warranty of
 MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 GNU Affero General Public License for more details.

 You should have received a copy of the GNU Affero General Public License
 along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""


import rlp
from eth_account._utils.transactions import assert_valid_fields, Transaction
from eth_utils.address import to_canonical_address
from eth_utils.applicators import apply_key_map
from eth_utils.conversions import to_int
from functools import wraps
from hexbytes import HexBytes
from trezorlib import ethereum
from trezorlib.client import get_default_client, TrezorClient
from trezorlib.tools import parse_path, Address, H_
from trezorlib.transport import TransportException
from typing import List, Tuple, Union
from web3 import Web3

from nucypher.blockchain.eth.decorators import validate_checksum_address
from nucypher.blockchain.eth.signers.base import Signer


def handle_trezor_call(device_func):
    """
    Decorator for calls to trezorlib that require physical device interactions.
    """
    @wraps(device_func)
    def wrapped(trezor, *args, **kwargs):
        import usb1  # may not be installable on some systems (consider CI)
        try:
            result = device_func(trezor, *args, **kwargs)
        except usb1.USBErrorNoDevice:
            error = "The client cannot communicate to the TREZOR USB device. Was it disconnected?"
            raise trezor.NoDeviceDetected(error)
        except usb1.USBErrorBusy:
            raise trezor.DeviceError("The TREZOR USB device is busy.")
        else:
            return result

    return wrapped


class TrezorSigner(Signer):
    """A trezor message and transaction signing client."""

    # BIP44 HD derivation paths
    # https://wiki.trezor.io/Cryptocurrency_standards#bip44
    # https://wiki.trezor.io/Cryptocurrency_standards#slip44

    __BIP_44 = 44
    __ETH_COIN_TYPE = 60     # mainnet
    __TESTNET_COIN_TYPE = 1  # all testnets

    _COIN_TYPE = None  # set in __init__
    _CHAIN_ID = 0
    _DEFAULT_ACCOUNT = 0
    _DERIVATION_ROOT = f"{__BIP_44}'/{__ETH_COIN_TYPE}'/{_DEFAULT_ACCOUNT}'/{_CHAIN_ID}"

    # Cache
    DEFAULT_ACCOUNT_INDEX = 0
    ADDRESS_CACHE_SIZE = 10  # default number of accounts to derive and internally track

    class DeviceError(Exception):
        """Base exception for trezor signing API"""

    class NoDeviceDetected(DeviceError):
        """Raised when an operation requires a device but none are available"""

    def __init__(self, testnet: bool = False):

        self.__client = self._open()
        self._device_id = self.__client.get_device_id()

        # SLIP44 testnet support for EIP-155 sigatures
        # TODO: there is no way to change this back to mainnet
        self.testnet = testnet
        TrezorSigner._COIN_TYPE = self.__TESTNET_COIN_TYPE if self.testnet else self.__ETH_COIN_TYPE

        self.__addresses = dict()  # track derived addresses
        self.__cache_addresses()

    @handle_trezor_call
    def _open(self) -> TrezorClient:
        try:
            client = get_default_client()
        except TransportException:
            raise self.NoDeviceDetected("Could not find a TREZOR device to connect to. Have you unlocked it?")
        return client

    @classmethod
    def uri_scheme(cls) -> str:
        return 'trezor'

    #
    # Internal
    #

    def __get_address_path(self, index: int = None, checksum_address: str = None) -> List[H_]:
        """Resolves a checksum address into an HD path and returns it."""
        if index is not None and checksum_address:
            raise ValueError("Expected index or checksum address; Got both.")
        elif index is not None:
            hd_path = parse_path(f"{self._DERIVATION_ROOT}/{index}")
        else:
            try:
                hd_path = self.__addresses[checksum_address]
            except KeyError:
                raise RuntimeError(f"{checksum_address} was not loaded into the device address cache.")
        return hd_path

    @handle_trezor_call
    def __derive_account(self, index: int = None, hd_path: Address = None) -> str:
        """Resolves a trezorlib HD path into a checksum address and returns it."""
        if not hd_path:
            if index is None:
                raise ValueError("No index or HD path supplied.")  # TODO: better error handling here
            hd_path = self.__get_address_path(index=index)
        address = ethereum.get_address(client=self.__client, n=hd_path, show_display=False)  # TODO: show display?
        return address

    def __cache_addresses(self) -> None:
        """
        Derives trezor ethereum addresses up to ADDRESS_CACHE_SIZE relative to
        the calculated base path and internally caches them for later use.
        """
        for index in range(self.ADDRESS_CACHE_SIZE):
            hd_path = self.__get_address_path(index=index)
            address = self.__derive_account(hd_path=hd_path)
            self.__addresses[address] = hd_path

    @staticmethod
    def _format_transaction(transaction_dict: dict) -> dict:
        """
        Handle Web3.py -> Trezor native transaction field formatting
        # https://web3py.readthedocs.io/en/latest/web3.eth.html#web3.eth.Eth.sendRawTransaction
        """
        assert_valid_fields(transaction_dict)
        trezor_transaction_keys = {'gas': 'gas_limit', 'gasPrice': 'gas_price', 'chainId': 'chain_id'}
        trezor_transaction = dict(apply_key_map(trezor_transaction_keys, transaction_dict))
        return trezor_transaction

    @handle_trezor_call
    def __sign_transaction(self, n: List[int], trezor_transaction: dict) -> Tuple[bytes, bytes, bytes]:
        """Internal wrapper for trezorlib transaction signing calls"""
        v, r, s = ethereum.sign_tx(client=self.__client, n=n, **trezor_transaction)
        return v, r, s

    #
    # Trezor Signer API
    #

    @classmethod
    def from_signer_uri(cls, uri: str, testnet: bool = False) -> 'TrezorSigner':
        """Return a trezor signer from URI string i.e. trezor:///my/trezor/path """
        if uri != cls.uri_scheme():  # TODO: #2269 Support "rich URIs" for trezors
            raise cls.InvalidSignerURI(f'{uri} is not a valid trezor URI scheme')
        return cls(testnet=testnet)

    def is_device(self, account: str) -> bool:
        """Trezor is always a device."""
        return True

    @validate_checksum_address
    def unlock_account(self, account: str, password: str, duration: int = None) -> bool:
        """Defer account unlocking to the trezor, do not indicate application level unlocking logic."""
        return True

    @validate_checksum_address
    def lock_account(self, account: str) -> bool:
        """Defer account locking to the trezor, do not indicate application level unlocking logic."""
        return True

    @property
    def accounts(self) -> List[str]:
        """Returns a list of cached trezor checksum addresses from initial derivation."""
        return list(self.__addresses.keys())

    @handle_trezor_call
    def sign_message(self, message: bytes, checksum_address: str) -> HexBytes:
        """
        Signs a message via the TREZOR ethereum sign_message API and returns
        a named tuple containing the signature and the address used to sign it.
        This method requires interaction between the TREZOR and the user.
        """
        # TODO: #2262 Implement Trezor Message Signing
        hd_path = self.__get_address_path(checksum_address=checksum_address)
        signed_message = ethereum.sign_message(self.__client, hd_path, message)
        return HexBytes(signed_message.signature)

    def sign_transaction(self,
                         transaction_dict: dict,
                         rlp_encoded: bool = True
                         ) -> Union[HexBytes, Transaction]:
        """
        Sign a transaction with a trezor hardware wallet.

        This method handles transaction validation, field formatting, signing,
        and outgoing serialization.  Accepts a standard transaction dictionary as input,
        and produces an RLP encoded raw signed transaction by default.

        Internally the standard transaction dictionary is reformatted for trezor API consumption
        via calls `trezorlib.client.ethereum.sign_tx`.

        WARNING: This function returns a raw signed transaction which can be
        broadcast by anyone with a connection to the ethereum network.

        ***Treat pre-signed raw transactions produced by this function like money.***

        """

        # Consume the sender inside the transaction request's 'from field.
        checksum_address = transaction_dict.pop('from')

        # Format contract data field for both trezor and eth_account's Transaction
        if transaction_dict.get('data') is not None:  # empty string is valid
            transaction_dict['data'] = Web3.toBytes(HexBytes(transaction_dict['data']))

        # Eager enforcement of EIP-155
        # https://github.com/ethereum/EIPs/blob/master/EIPS/eip-155.md
        #
        # Leave the chain ID in tact for the trezor signing request so that an EIP-155 transaction signature will be applied
        # https://github.com/trezor/trezor-core/pull/311
        if 'chainId' not in transaction_dict:
            raise self.SignerError('Invalid EIP-155 transaction - "chain_id" field is missing in trezor signing request.')

        # Format transaction fields for Trezor, Lookup HD path
        trezor_transaction = self._format_transaction(transaction_dict=transaction_dict)

        # Note that the derivation path on the trezor must correlate with the chain id
        # in the transaction. Since Trezor firmware version 2.3.1 mismatched chain_id
        # and derivation path will fail to sign with 'forbidden key path'.
        # https://github.com/trezor/trezor-firmware/issues/1050#issuecomment-640718622
        hd_path = self.__get_address_path(checksum_address=checksum_address)  # from cache

        # Fire Trezor device signing request
        _v, _r, _s = self.__sign_transaction(n=hd_path, trezor_transaction=trezor_transaction)

        # Post-signing sanity check for replay attack protection.
        chain_id = transaction_dict.pop('chainId')
        eip155_v = 1 + chain_id * 2 + 35
        if _v != eip155_v:
            raise self.SignerError(f'Invalid EIP-155 transaction signature - v({_v}) does not match calculation {eip155_v}')

        # Create RLP serializable Transaction instance with eth_account
        transaction_dict['to'] = to_canonical_address(checksum_address)  # str -> bytes
        signed_transaction = Transaction(v=to_int(_v),                   # type: int
                                         r=to_int(_r),                   # bytes -> int
                                         s=to_int(_s),                   # bytes -> int
                                         **transaction_dict)

        # Optionally encode as RLP for broadcasting
        if rlp_encoded:
            signed_transaction = HexBytes(rlp.encode(signed_transaction))

        return signed_transaction
