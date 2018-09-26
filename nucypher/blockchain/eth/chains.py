from logging import getLogger

from constant_sorrow.constants import NO_BLOCKCHAIN_AVAILABLE
from typing import Union
from web3.contract import Contract

from nucypher.blockchain.eth.interfaces import BlockchainInterface, BlockchainDeployerInterface


class Blockchain:
    """A view of a blockchain through a provided interface"""

    _instance = NO_BLOCKCHAIN_AVAILABLE
    __default_interface_class = BlockchainInterface

    class ConnectionNotEstablished(RuntimeError):
        pass

    def __init__(self, interface: Union[BlockchainInterface, BlockchainDeployerInterface] = None) -> None:

        self.log = getLogger("blockchain")                       # type: Logger

        # Default interface
        if interface is None:
            interface = self.__default_interface_class()
        self.__interface = interface

        # Singleton
        if self._instance is NO_BLOCKCHAIN_AVAILABLE:
            Blockchain._instance = self
        else:
            raise RuntimeError("Connection already established - Use .connect()")

    def __repr__(self):
        class_name = self.__class__.__name__
        r = "{}(interface={})"
        return r.format(class_name, self.__interface)

    @property
    def interface(self) -> Union[BlockchainInterface, BlockchainDeployerInterface]:
        return self.__interface

    @classmethod
    def connect(cls, provider_uri: str = None) -> 'Blockchain':
        if cls._instance is NO_BLOCKCHAIN_AVAILABLE:
            cls._instance = cls(interface=BlockchainInterface(provider_uri=provider_uri))
        else:
            if provider_uri is not None:
                existing_uri = cls._instance.interface.provider_uri
                if existing_uri != provider_uri:
                    raise ValueError("There is an existing blockchain connection to {}. "
                                     "Use Interface.add_provider to connect additional providers".format(existing_uri))
        return cls._instance

    def get_contract(self, name: str) -> Contract:
        """
        Gets an existing contract from the registry, or raises UnknownContract
        if there is no contract data available for the name/identifier.
        """
        return self.__interface.get_contract_by_name(name)

    def wait_for_receipt(self, txhash: str, timeout: int = None) -> dict:
        """Wait for a transaction receipt and return it"""
        timeout = timeout if timeout is not None else self.interface.timeout
        result = self.__interface.w3.eth.waitForTransactionReceipt(txhash, timeout=timeout)
        return result
