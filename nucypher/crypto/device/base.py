
from abc import ABC, abstractmethod
from collections import namedtuple


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

    class NoDeviceDetected(DeviceError):
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
    def sign_eth_transaction(self, chain_id: int, **transaction):
        """
        Abstract method for signing an Ethereum transaction via a device's
        API.
        """
        raise NotImplementedError
