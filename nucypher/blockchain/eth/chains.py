"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""
from twisted.logger import Logger

from constant_sorrow.constants import NO_BLOCKCHAIN_AVAILABLE
from typing import Union
from web3.contract import Contract

from nucypher.blockchain.eth.interfaces import BlockchainInterface, BlockchainDeployerInterface
from nucypher.blockchain.eth.registry import EthereumContractRegistry
from nucypher.blockchain.eth.sol.compile import SolidityCompiler


class Blockchain:
    """A view of a blockchain through a provided interface"""

    _instance = NO_BLOCKCHAIN_AVAILABLE
    __default_interface_class = BlockchainInterface

    class ConnectionNotEstablished(RuntimeError):
        pass

    def __init__(self, interface: Union[BlockchainInterface, BlockchainDeployerInterface] = None) -> None:

        self.log = Logger("blockchain")                       # type: Logger

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
    def connect(cls,
                provider_uri: str = None,
                registry: EthereumContractRegistry = None,
                deployer: bool = False,
                compile: bool = False,
                ) -> 'Blockchain':

        if cls._instance is NO_BLOCKCHAIN_AVAILABLE:
            registry = registry or EthereumContractRegistry()
            compiler = SolidityCompiler() if compile is True else None
            InterfaceClass = BlockchainDeployerInterface if deployer is True else BlockchainInterface
            interface = InterfaceClass(provider_uri=provider_uri, registry=registry, compiler=compiler)
            cls._instance = cls(interface=interface)
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
