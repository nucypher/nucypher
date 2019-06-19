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


from functools import wraps
from typing import Tuple

from nucypher.blockchain.eth.decorators import validate_checksum_address
from nucypher.crypto.signing import InvalidSignature
from nucypher.device.base import TrustedDevice

try:
    from trezorlib import client as trezor_client
    from trezorlib import device as trezor_device
    from trezorlib import ethereum as trezor_eth
    from trezorlib import tools as trezor_tools
    from trezorlib.transport import TransportException
    from usb1 import USBErrorNoDevice, USBErrorBusy
except ImportError:
    raise RuntimeError("The nucypher package wasn't installed with the 'trezor' extra")


class Trezor(TrustedDevice):
    """
    An implementation of a Trezor device for staking on the NuCypher network.
    """

    def __init__(self, cached_index: int = 1):
        """
        Initializes a Trezor device.

        `cached_index` is the highest address_index to cache in memory.
        TODO: Use a device config to determine some init settings like how many
              addresses to cache.
        """
        try:
            self.client = trezor_client.get_default_client()
        except TransportException:
            raise RuntimeError("Could not find a TREZOR device to connect to. Have you unlocked it?")

        self.__addresses = {}
        for addr_idx in range(cached_index + 1):
            hd_path = self.ETH_BIP44_PATH.format(address_index=addr_idx)
            address = self.get_address(hd_path=hd_path)
            self.__addresses[address] = trezor_tools.parse_path(hd_path)

    def _handle_device_call(device_func):
        @wraps(device_func)
        def wrapped_call(inst, *args, **kwargs):
            try:
                result = device_func(inst, *args, **kwargs)
            except USBErrorNoDevice:
                raise inst.DeviceError("The client cannot communicate to the TREZOR USB device. Was it disconnected?")
            except USBErrorBusy:
                raise inst.DeviceError("The TREZOR USB device is busy.")
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
        return trezor_device.wipe(self.client)

    @_handle_device_call
    def configure(self):
        raise NotImplementedError

    @_handle_device_call
    @validate_checksum_address
    def sign_message(self, message: bytes, checksum_address: str):
        """
        Signs a message via the TREZOR ethereum sign_message API and returns
        the signature and the address used to sign it. This method requires
        interaction between the TREZOR and the user.

        It will sign the message with the account described by checksum_address.
        """
        try:
            bip44_path = self.__addresses[checksum_address]
        except KeyError:
            raise self.DeviceError(f'{checksum_address} is not available as a cached address on this device.')

        sig = trezor_eth.sign_message(self.client, bip44_path, message)
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
        is_valid = trezor_eth.verify_message(self.client, checksum_address,
                                             signature, message)
        if not is_valid:
            raise InvalidSignature("Signature verification failed.")
        return True

    @_handle_device_call
    def get_address(self, address_index: int = None, hd_path: str = None):
        """
        Derives an address available on the Trezor via the ethereum
        get_address API and returns it.
        """
        if address_index is not None and hd_path is None:
            hd_path = self.ETH_BIP44_PATH.format(address_index=address_index)
            hd_path = trezor_tools.parse_path(hd_path)
        elif address_index is None and hd_path is not None:
            hd_path = trezor_tools.parse_path(hd_path)
        else:
            raise ValueError("You must provider either an address_index or an hd_path.")

        address = trezor_eth.get_address(self.client, hd_path)
        return address

    @_handle_device_call
    def sign_eth_transaction(self, chain_id: int, **transaction) -> Tuple[bytes]:
        """
        Signs an Ethereum transaction via the Trezor ethereum sign_tx API
        and returns the signed transaction.

        TODO: Is there any input validation required for the transaction
              data that is passed in?
        """
        signed_tx = trezor_eth.sign_tx(client=self.client,
                                       chain_id=chain_id,
                                       **transaction)
        return signed_tx
