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
from nucypher.hardware.backends import TrustedDevice

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
from typing import Tuple

from nucypher.blockchain.eth.decorators import validate_checksum_address
from nucypher.crypto.signing import InvalidSignature


class Trezor(TrustedDevice):
    """
    An implementation of a Trezor device for staking on the NuCypher network.
    """

    def __init__(self):
        try:
            self.client = client.get_default_client()
        except TransportException:
            raise self.NoDeviceDetected("Could not find a TREZOR device to connect to. Have you unlocked it?")
        else:
            self.__bip44_path = tools.parse_path(self.DEFAULT_BIP44_PATH)
            # ethereum.get_address()

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
    def sign_message(self, message: bytes, address_index: int = 0):
        """
        Signs a message via the TREZOR ethereum sign_message API and returns
        the signature and the address used to sign it. This method requires
        interaction between the TREZOR and the user.

        If an address_index is provided, it will use the address at that
        index to sign the message. If no index is provided, the address at
        the 0th index is used by default.
        """
        bip44_path = self.__bip44_path + [address_index]

        sig = ethereum.sign_message(self.client, bip44_path, message)
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
        is_valid = ethereum.verify_message(self.client, checksum_address,
                                                  signature, message)
        if not is_valid:
            raise InvalidSignature("Signature verification failed.")
        return True

    @_handle_device_call
    def sign_eth_transaction(self, chain_id: int, **transaction) -> Tuple[bytes]:
        response = ethereum.sign_tx(client=self.client, chain_id=chain_id, **transaction)
        return response
