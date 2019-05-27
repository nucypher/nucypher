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


from abc import ABC, abstractmethod
from collections import namedtuple
from functools import wraps
from trezorlib import client as trezor_client
from trezorlib import device as trezor_device
from trezorlib import ethereum as trezor_eth
from trezorlib.tools import parse_path
from trezorlib.transport import TransportException
from usb1 import USBErrorNoDevice, USBErrorBusy

from nucypher.crypto.signing import InvalidSignature


class TrustedDevice(ABC):
    """
    An Abstract Base Class for implementing wallet-like functions for stakers
    utilizing trusted hardware devices (e.g. trezor).
    This class specifies a few basic functions required for staking on the
    NuCypher network.

    TODO: Define an abstractmethod for BIP44 derivation?
    """

    # We intentionally keep the address index off the path so that the
    # subclass interfaces can handle which address index to use.
    DEFAULT_BIP44_PATH = "m/44'/60'/0'/0"

    Signature = namedtuple('Signature', ['signature', 'address'])

    class DeviceError(Exception):
        pass

    @abstractmethod
    def __handle_device_call(device_func):
        """
        Abstract method useful as a decorator for device API calls to handle
        any side effects that occur during execution (exceptions, etc).
        """
        raise NotImplementedError

    @abstractmethod
    def __reset(self):
        """
        Abstract method for resetting the device to a state that's ready to
        be configured for staking. This may or may not wipe the device,
        therefore, appropriate care should be taken.
        """
        raise NotImplementedError

    @abstractmethod
    def configure(self):
        """
        Abstract method for configuring the device to work with the NuCypher
        network. It should be assumed that this is configuring a dedicated
        device intended for staking _only_.
        """
        raise NotImplementedError

    @abstractmethod
    def sign_message(self, message: bytes, address_index: int = 0):
        """
        Abstract method for signing any arbitrary message via a device's API.

        TODO: What format should signatures output?
        """
        raise NotImplementedError

    @abstractmethod
    def verify_message(self, signature: bytes, messsage: bytes, address: str):
        """
        Abstract method for verifying a signature via a device's API.
        """
        raise NotImplementedError

    @abstractmethod
    def sign_eth_transaction(self):
        """
        Abstract method for signing an Ethereum transaction via a device's
        API.
        """
        raise NotImplementedError


class Trezor(TrustedDevice):
    """
    An implementation of a Trezor device for staking on the NuCypher network.
    """

    def __init__(self):
        try:
            self.client = trezor_client.get_default_client()
            self.__bip44_path = parse_path(self.DEFAULT_BIP44_PATH)
        except TransportException:
            raise RuntimeError("Could not find a TREZOR device to connect to. Have you unlocked it?")

    def __handle_device_call(device_func):
        @wraps(device_func)
        def wrapped_call(inst, *args, **kwargs):
            try:
                result = device_func(inst, *args, **kwargs)
            except USBErrorNoDevice:
                raise inst.DeviceError("The client cannot communicate to the TREZOR USB device. Is it connected?")
            except USBErrorBusy:
                raise inst.DeviceError("The TREZOR USB device is busy.")
            else:
                return result
        return wrapped_call

    @__handle_device_call
    def __reset(self):
        """
        Erases the TREZOR device by calling the wipe device function in
        preparation to configure it for staking.

        WARNING: This will delete ALL data on the TREZOR.
        """
        trezor_device.wipe(self.client)

    @__handle_device_call
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

        sig = trezor_eth.sign_message(self.client, bip44_path, message)
        return self.Signature(sig.signature, sig.address)

    @__handle_device_call
    def verify_message(self, signature: bytes, message: bytes, address: str):
        """
        Verifies that a signature and message pair are from a specified
        address via the TREZOR ethereum verify_message API. This method
        requires interaction between the TREZOR and the user.

        If the signature or message is not valid, it will raise a
        nucypher.crypto.signing.InvalidSignature exception. Otherwise, it
        will return True.

        TODO: Should we provide some input validation for the ETH address?
        """
        is_valid = trezor_eth.verify_message(self.client, address, signature,
                                             message)
        if not is_valid:
            raise InvalidSignature("Signature verification failed.")
        return True
