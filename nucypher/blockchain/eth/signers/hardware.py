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


from collections import namedtuple
from typing import List, Tuple, Union
from urllib.parse import urlparse

import rlp
from eth_account._utils.transactions import assert_valid_fields, Transaction
from eth_utils.address import to_canonical_address
from eth_utils.applicators import apply_key_map
from eth_utils.conversions import to_int
from hexbytes import HexBytes
from web3 import Web3

from nucypher.blockchain.eth.signers.base import Signer

try:
    import trezorlib
    from trezorlib import ethereum
    from trezorlib.client import get_default_client
    from trezorlib.tools import parse_path, Address, H_
    from trezorlib.transport import TransportException
except ImportError:
    raise RuntimeError("The nucypher package wasn't installed with the 'trezor' extra.")

from functools import wraps

from nucypher.blockchain.eth.decorators import validate_checksum_address


def handle_trezor_call(device_func):
    """
    Decorator for calls to trezorlib that require physical device interactions.
    """
    @wraps(device_func)
    def wrapped(trezor, *args, **kwargs):
        import usb1  # may not be installed on all systems including CI
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

    URI_SCHEME = 'trezor'

    # Key Derivation Paths

    __BIP_44 = 44
    __ETH_COIN_TYPE = 60

    CHAIN_ID = 0  # 0 is mainnet
    DEFAULT_ACCOUNT = 0
    DEFAULT_ACCOUNT_INDEX = 0
    DERIVATION_ROOT = f"{__BIP_44}'/{__ETH_COIN_TYPE}'/{DEFAULT_ACCOUNT}'/{CHAIN_ID}"
    ADDRESS_CACHE_SIZE = 10  # default number of accounts to derive and internally track

    # Types

    SignedMessage = namedtuple('SignedMessage', ['signature', 'signer'])

    class DeviceError(Exception):
        """Base exception for trezor signing API"""

    class NoDeviceDetected(DeviceError):
        """Raised when an operation requires a device but none are available"""

    def __init__(self):
        try:
            self.__client = get_default_client()
        except TransportException:
            raise self.NoDeviceDetected("Could not find a TREZOR device to connect to. Have you unlocked it?")
        self._device_id = self.__client.get_device_id()
        self.__addresses = dict()  # track derived addresses
        self.__load_addresses()

    #
    # Internal
    #

    def __get_address_path(self, index: int = None, checksum_address: str = None) -> List[H_]:
        """Resolves a checksum address into an HD path and returns it."""
        if index is not None and checksum_address:
            raise ValueError("Expected index or checksum address; Got both.")
        elif index is not None:
            hd_path = parse_path(f"{self.DERIVATION_ROOT}/{index}")
        else:
            try:
                hd_path = self.__addresses[checksum_address]
            except KeyError:
                raise RuntimeError(f"{checksum_address} was not loaded into the device address cache.")
        return hd_path

    @handle_trezor_call
    def __get_address(self, index: int = None, hd_path: Address = None, show_display: bool = True) -> str:
        """Resolves a trezorlib HD path into a checksum address and returns it."""
        if not hd_path:
            if index is None:
                raise ValueError("No index or HD path supplied.")  # TODO: better error handling here
            hd_path = self.__get_address_path(index=index)
        address = ethereum.__get_address(client=self.__client, n=hd_path, show_display=show_display)
        return address

    def __load_addresses(self) -> None:
        """
        Derive trezor addresses up to ADDRESS_CACHE_SIZE relative to
        the calculated base path and internally cache them.
        """
        for index in range(self.ADDRESS_CACHE_SIZE):
            hd_path = self.__get_address_path(index=index)
            address = self.__get_address(hd_path=hd_path, show_display=False)
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
        v, r, s = trezorlib.ethereum.sign_tx(client=self.__client, n=n, **trezor_transaction)
        return v, r, s

    #
    # Trezor Signer API
    #

    @classmethod
    def from_signer_uri(cls, uri: str) -> 'TrezorSigner':
        """Return a trezor signer from URI string i.e. trezor:///my/trezor/path """
        decoded_uri = urlparse(uri)
        if decoded_uri.scheme != cls.URI_SCHEME or decoded_uri.netloc:
            raise cls.InvalidSignerURI(uri)
        return cls()

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
    def sign_message(self, message: bytes, checksum_address: str) -> SignedMessage:
        """
        Signs a message via the TREZOR ethereum sign_message API and returns
        a named tuple containing the signature and the address used to sign it.
        This method requires interaction between the TREZOR and the user.
        """
        hd_path = self.__get_address_path(checksum_address=checksum_address)
        signed_message = trezorlib.ethereum.sign_message(self.__client, hd_path, message)
        return self.SignedMessage(signed_message.signature, signed_message.address)

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

        # Read the sender inside the transaction request
        checksum_address = transaction_dict.pop('from')

        # Format contract data field for both trezor and eth_account
        if transaction_dict.get('data') is not None:  # empty string is valid
            transaction_dict['data'] = Web3.toBytes(HexBytes(transaction_dict['data']))

        # Format transaction fields for Trezor, Lookup HD path, and Sign Transaction
        # If `chain_id` is included, an EIP-155 transaction signature will be applied
        # https://github.com/trezor/trezor-core/pull/311
        trezor_transaction = self._format_transaction(transaction_dict=transaction_dict)
        n = self.__get_address_path(checksum_address=checksum_address)
        v, r, s = self.__sign_transaction(n=n, trezor_transaction=trezor_transaction)

        # Format the transaction for eth_account Transaction consumption
        # v = (v + 2) * (chain_id + 35)
        # https://github.com/ethereum/eips/issues/155
        del transaction_dict['chainId']   # see above

        # Format ethereum address for eth_account and rlp
        transaction_dict['to'] = to_canonical_address(checksum_address)

        # Create RLP serializable Transaction
        signed_transaction = Transaction(v=to_int(v),  # int
                                         r=to_int(r),  # bytes -> int
                                         s=to_int(s),  # bytes -> int
                                         **transaction_dict)

        # Optionally encode as RLP for broadcasting
        if rlp_encoded:
            signed_transaction = HexBytes(rlp.encode(signed_transaction))

        return signed_transaction
