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
import time

import geth
import maya
from geth.chain import write_genesis_file, initialize_chain
from twisted.logger import Logger
from web3.middleware import geth_poa_middleware

from constant_sorrow.constants import NO_BLOCKCHAIN_AVAILABLE
from typing import Union
from web3.contract import Contract

from nucypher.blockchain.eth.interfaces import BlockchainInterface, BlockchainDeployerInterface
from nucypher.blockchain.eth.registry import EthereumContractRegistry
from nucypher.blockchain.eth.sol.compile import SolidityCompiler


class Blockchain:
    """A view of a blockchain through a provided interface"""

    NULL_ADDRESS = '0x' + '0' * 40

    _instance = NO_BLOCKCHAIN_AVAILABLE
    __default_interface_class = BlockchainInterface

    def __init__(
            self,
            provider_process=None,
            interface: Union[BlockchainInterface, BlockchainDeployerInterface] = None,
            dev: bool = False):

        self.log = Logger("blockchain")
        self.dev = dev

        self.__provider_process = provider_process

        # Default interface
        if interface is None:
            interface = self.__default_interface_class()
        self.__interface = interface

        # Agency
        if self._instance is NO_BLOCKCHAIN_AVAILABLE:
            Blockchain._instance = self
        else:
            raise RuntimeError("Connection already established - Use .connect()")

    def __repr__(self):
        class_name = self.__class__.__name__
        r = "{}(interface={}, process={})"
        return r.format(class_name, self.__interface, self.__provider_process)

    @property
    def interface(self) -> Union[BlockchainInterface, BlockchainDeployerInterface]:
        return self.__interface

    @property
    def peers(self):
        if self._instance is NO_BLOCKCHAIN_AVAILABLE:
            raise self.ConnectionNotEstablished
        return self.interface.peers()

    @property
    def chain_id(self):
        return self.interface.chain_id

    def chain_name(self):
        return self.interface.chain_name

    @property
    def syncing(self):
        if self._instance is NO_BLOCKCHAIN_AVAILABLE:
            raise self.ConnectionNotEstablished
        return self.interface.client.syncing

    def sync(self, timeout: int = 600):
        """
        Blocking call that polls the ethereum client for at least one ethereum peer
        and knowledge of all blocks known by bootnodes.
        """

        return self.interface.client.sync(timeout=timeout)

    @classmethod
    def connect(cls,
                provider_process=None,
                provider_uri: str = None,
                registry: EthereumContractRegistry = None,
                deployer: bool = False,
                compile: bool = False,
                poa: bool = False,
                force: bool = True,
                fetch_registry: bool = True,
                sync: bool = True,
                dev: bool = False,
                ) -> 'Blockchain':

        log = Logger('blockchain-init')
        if cls._instance is NO_BLOCKCHAIN_AVAILABLE:

            # Spawn child process
            if provider_process:
                provider_process.start()
                provider_uri = provider_process.provider_uri(scheme='file')
            else:
                log.info(f"Using external Web3 Provider '{provider_uri}'")

            compiler = SolidityCompiler() if compile is True else None
            InterfaceClass = BlockchainDeployerInterface if deployer is True else BlockchainInterface
            interface = InterfaceClass(provider_uri=provider_uri, compiler=compiler, registry=registry)

            if poa is True:
                log.debug('Injecting POA middleware at layer 0')
                interface.middleware_onion.inject(geth_poa_middleware, layer=0)

            cls._instance = cls(interface=interface, provider_process=provider_process, dev=dev)

            # Sync blockchain
            if sync:
                cls._instance.sync()

        else:

            if provider_uri is not None:
                existing_uri = cls._instance.interface.provider_uri
                if (existing_uri != provider_uri) and not force:
                    raise ValueError("There is an existing blockchain connection to {}. "
                                     "Use Interface.add_provider to connect additional providers".format(existing_uri))

            if registry is not None:
                # This can happen when there is a cached singleton instance
                # but we want to connect using a different registry.
                cls._instance.interface.registry = registry

        return cls._instance

    @classmethod
    def disconnect(cls):
        if cls._instance is not NO_BLOCKCHAIN_AVAILABLE:
            if cls._instance.__provider_process:
                cls._instance.__provider_process.stop()

    def get_contract(self, name: str) -> Contract:
        """
        Gets an existing contract from the registry, or raises UnknownContract
        if there is no contract data available for the name/identifier.
        """
        return self.__interface.get_contract_by_name(name)

    def wait_for_receipt(self, txhash: bytes, timeout: int = None) -> dict:
        """Wait for a transaction receipt and return it"""
        timeout = timeout if timeout is not None else self.interface.timeout
        result = self.__interface.w3.eth.waitForTransactionReceipt(txhash, timeout=timeout)
        return result
