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


class TrustedDevice(ABC):
    """
    An Abstract Base Class for implementing wallet-like functions for stakers
    utilizing trusted hardware devices.
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
    def _handle_device_call(device_func):
        """
        Abstract method useful as a decorator for device API calls to handle
        any side effects that occur during execution (exceptions, etc).
        """
        raise NotImplementedError

    @abstractmethod
    def _reset(self):
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
