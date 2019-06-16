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
from eth_utils import to_canonical_address, to_int, ValidationError
from rlp.sedes import (
    Binary,
    big_endian_int,
    binary,
)
from trezorlib.tools import parse_path, Address
from eth_account._utils.transactions import Transaction, encode_transaction, assert_valid_fields

from nucypher.crypto.device.base import TrustedDevice

try:

    # Trezor firmware
    import trezorlib

    # Handle imports specific for trezor devices
    from trezorlib.transport import TransportException

    # Sub-deps
    import usb1

except ImportError:
    raise RuntimeError("The nucypher package wasn't installed with the 'trezor' extra.")

else:
    from trezorlib import transport, client, device, ethereum, tools

from functools import wraps
from typing import Tuple, List

from nucypher.blockchain.eth.decorators import validate_checksum_address
from nucypher.crypto.signing import InvalidSignature


class Trezor(TrustedDevice):
    """
    An implementation of a Trezor device for staking on the NuCypher network.
    """

    ADDRESS_CACHE_SIZE = 10

    def __init__(self):
        try:
            self.client = client.get_default_client()
        except TransportException:
            raise self.NoDeviceDetected("Could not find a TREZOR device to connect to. Have you unlocked it?")

        self._device_id = self.client.get_device_id()
        self.__addresses = dict()
        self.__load_addresses()

    def _handle_device_call(device_func):
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

    @_handle_device_call
    def _reset(self):
        """
        Erases the TREZOR device by calling the wipe device function in
        preparation to configure it for staking.

        WARNING: This will delete ALL data on the TREZOR.
        """
        return device.wipe(self.client)

    @_handle_device_call
    def configure(self):
        raise NotImplementedError

    @_handle_device_call
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
        sig = ethereum.sign_message(self.client, hd_path, message)
        return self.Signature(sig.signature, sig.address)

    @_handle_device_call
    @validate_checksum_address
    def verify_message(self, signature: bytes, message: bytes, checksum_address: str):
        """
        Verifies that a signature and message pair are from a specified
        address via the TREZOR ethereum verify_message API. This method
        requires interaction between the TREZOR and the user.

        If the signature or message is not valid, it will raise a
        nucypher.crypto.signing.InvalidSignature exception. Otherwise, it
        will return True.

        TODO: Should we provide some input validation for the ETH address?
        """
        is_valid = ethereum.verify_message(self.client,
                                           checksum_address,
                                           signature,
                                           message)
        if not is_valid:
            raise InvalidSignature("Signature verification failed.")
        return True

    def get_address_path(self, index: int = None, checksum_address: str = None) -> List[int]:
        if index is not None and checksum_address:
            raise ValueError("Expected index or checksum address; Got both.")
        elif index is not None:
            hd_path = parse_path(f"{self.ETH_CHAIN_ROOT}/{index}")
        else:
            try:
                hd_path = self.__addresses[checksum_address]
            except KeyError:
                raise self.DeviceError(f"{checksum_address} was not loaded into the device address cache.")
        return hd_path

    def __load_addresses(self):
        for index in range(self.ADDRESS_CACHE_SIZE):
            hd_path = self.get_address_path(index=index)
            address = self.get_address(hd_path=hd_path, show_display=False)
            self.__addresses[address] = hd_path

    @_handle_device_call
    def get_address(self, index: int = None, hd_path: Address = None, show_display: bool = True) -> str:
        if not hd_path:
            if index is None:
                raise ValueError("No index or HD path supplied.")  # TODO: better error handling here
            hd_path = self.get_address_path(index=index)
        address = ethereum.get_address(client=self.client, n=hd_path, show_display=show_display)
        return address

    @_handle_device_call
    def sign_eth_transaction(self,
                             checksum_address: str,
                             unsigned_transaction: dict,
                             rlp_encoded: bool = True,
                             ) -> Tuple[bytes]:

        # TODO: Handle web3.py formatting
        unsigned_transaction.update(dict(to=to_canonical_address(checksum_address)))

        n = self.get_address_path(checksum_address=checksum_address)
        v, r, s = ethereum.sign_tx(client=self.client, n=n, **unsigned_transaction)
        signed_transaction = Transaction(v=to_int(v),
                                         r=to_int(r),
                                         s=to_int(s),
                                         **unsigned_transaction)
        if rlp_encoded:
            signed_transaction = rlp.encode(signed_transaction)
        return signed_transaction
