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
from typing import List, Tuple
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



class TrezorSigner(Signer):
    """
    An implementation of a Trezor device for staking on the NuCypher network.
    """

    URI_SCHEME = 'trezor'

    # We intentionally keep the address index off the path so that the
    # subclass interfaces can handle which address index to use.
    __BIP_44 = 44
    __ETH_COIN_TYPE = 60

    CHAIN_ID = 0  # mainnet
    DEFAULT_ACCOUNT = 0
    DEFAULT_ACCOUNT_INDEX = 0

    DERIVATION_ROOT = f"{__BIP_44}'/{__ETH_COIN_TYPE}'/{DEFAULT_ACCOUNT}'/{CHAIN_ID}"
    ADDRESS_CACHE_SIZE = 3

    Signature = namedtuple('Signature', ['signature', 'address'])

    class DeviceError(Exception):
        pass

    class NoDeviceDetected(DeviceError):
        pass

    def __init__(self):
        try:
            self.client = get_default_client()
        except TransportException:
            raise self.NoDeviceDetected("Could not find a TREZOR device to connect to. Have you unlocked it?")
        self._device_id = self.client.get_device_id()
        self.__addresses = dict()
        self.__load_addresses()

    @classmethod
    def from_signer_uri(cls, uri: str) -> 'TrezorSigner':
        """Return a trezor signer from URI string i.e. trezor:///my/trezor/path """
        decoded_uri = urlparse(uri)
        if decoded_uri.scheme != cls.URI_SCHEME or decoded_uri.netloc:
            raise cls.InvalidSignerURI(uri)
        return cls()

    def is_device(self, account: str) -> bool:
        return True

    @validate_checksum_address
    def unlock_account(self, account: str, password: str, duration: int = None) -> bool:
        return True

    @validate_checksum_address
    def lock_account(self, account: str) -> bool:
        return True

    def get_address_path(self, index: int = None, checksum_address: str = None) -> List[int]:
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

    def __load_addresses(self):
        for index in range(self.ADDRESS_CACHE_SIZE):
            hd_path = self.get_address_path(index=index)
            address = self.get_address(hd_path=hd_path, show_display=False)
            self.__addresses[address] = hd_path

    @property
    def accounts(self) -> List[str]:
        return list(self.__addresses.keys())

    #
    # Device Calls
    #

    def __handle_device_call(device_func):
        try:
            import usb1
        except ImportError:
            raise ImportError('libusb is not installed or available.')

        @wraps(device_func)
        def wrapped_call(trezor, *args, **kwargs):
            try:
                result = device_func(trezor, *args, **kwargs)
            except usb1.USBErrorNoDevice:
                error = "The client cannot communicate to the TREZOR USB device. Was it disconnected?"
                raise trezor.NoDeviceDetected(error)
            except usb1.USBErrorBusy:
                raise trezor.DeviceError("The TREZOR USB device is busy.")
            else:
                return result
        return wrapped_call

    @__handle_device_call
    def get_address(self, index: int = None, hd_path: Address = None, show_display: bool = True) -> str:
        if not hd_path:
            if index is None:
                raise ValueError("No index or HD path supplied.")  # TODO: better error handling here
            hd_path = self.get_address_path(index=index)
        address = ethereum.get_address(client=self.client, n=hd_path, show_display=show_display)
        return address

    @__handle_device_call
    def sign_message(self, message: bytes, checksum_address: str):
        """
        Signs a message via the TREZOR ethereum sign_message API and returns
        the signature and the address used to sign it. This method requires
        interaction between the TREZOR and the user.

        If an address_index is provided, it will use the address at that
        index to sign the message. If no index is provided, the address at
        the 0th index is used by default.
        """
        hd_path = self.get_address_path(checksum_address=checksum_address)
        sig = trezorlib.ethereum.sign_message(self.client, hd_path, message)
        return self.Signature(sig.signature, sig.address)

    @__handle_device_call
    def sign_transaction(self,
                         transaction_dict: dict,
                         rlp_encoded: bool = True
                         ) -> Tuple[bytes]:

        # Read the sender inside the transaction request
        checksum_address = transaction_dict.pop('from')

        # Handle Web3.py -> Trezor native transaction formatting
        # https://web3py.readthedocs.io/en/latest/web3.eth.html#web3.eth.Eth.sendRawTransaction
        assert_valid_fields(transaction_dict)
        trezor_transaction_keys = {'gas': 'gas_limit', 'gasPrice': 'gas_price', 'chainId': 'chain_id'}
        transaction_dict = dict(apply_key_map(trezor_transaction_keys, transaction_dict))

        # Format data
        if transaction_dict.get('data'):
            transaction_dict['data'] = Web3.toBytes(HexBytes(transaction_dict['data']))

        # Lookup HD path & Sign Transaction
        n = self.get_address_path(checksum_address=checksum_address)

        # Sign TX
        v, r, s = trezorlib.ethereum.sign_tx(client=self.client, n=n, **transaction_dict)

        # If `chain_id` is included, an EIP-155 transaction signature will be applied:
        # v = (v + 2) * (chain_id + 35)
        # https://github.com/ethereum/eips/issues/155
        # https://github.com/trezor/trezor-core/pull/311
        del transaction_dict['chainId']   # see above

        # Create RLP serializable Transaction
        transaction_dict['to'] = to_canonical_address(checksum_address)
        signed_transaction = Transaction(v=to_int(v),
                                         r=to_int(r),
                                         s=to_int(s),
                                         **transaction_dict)
        if rlp_encoded:
            signed_transaction = rlp.encode(signed_transaction)
        return signed_transaction
