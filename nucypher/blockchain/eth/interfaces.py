import json
import os
import warnings
from pathlib import Path
from typing import Tuple, List

from constant_sorrow import constants
from web3 import Web3, WebsocketProvider, HTTPProvider, IPCProvider
from web3.contract import Contract

from nucypher.blockchain.eth.sol.compile import SolidityCompiler

_DEFAULT_CONFIGURATION_DIR = os.path.join(str(Path.home()), '.nucypher')


class EthereumContractRegistry:
    """
    Records known contracts on the disk for future access and utility. This
    lazily writes to the filesystem during contract enrollment.

    WARNING: Unless you are developing NuCypher, you most likely won't ever need
    to use this.
    """
    __default_registry_path = os.path.join(_DEFAULT_CONFIGURATION_DIR,
                                            'registry.json')

    class UnknownContract(KeyError):
        pass

    def __init__(self, registry_filepath: str=None):
        self.__registry_filepath = registry_filepath or self.__default_registry_path

    def __write(self, registry_data: list) -> None:
        """
        Writes the registry data list as JSON to the registry file. If no
        file exists, it will create it and write the data. If a file does exist
        it will _overwrite_ everything in it.
        """
        with open(self.__registry_filepath, 'w+') as registry_file:
            registry_file.seek(0)
            registry_file.write(json.dumps(registry_data))
            registry_file.truncate()

    def __read(self) -> dict:
        """
        Reads the registry file and parses the JSON and returns a list.
        If the file is empty or the JSON is corrupt, it will return an empty
        list.
        If you are modifying or updating the registry file, you _must_ call
        this function first to get the current state to append to the dict or
        modify it because _write_registry_file overwrites the file.
        """
        try:
            with open(self.__registry_filepath, 'r') as registry_file:
                registry_file.seek(0)
                registry_data = json.loads(registry_file.read())
        except (json.decoder.JSONDecodeError, FileNotFoundError):
            registry_data = list()
        return registry_data

    def enroll(self, contract_name, contract_address, contract_abi):
        """
        Enrolls a contract to the chain registry by writing the name, address,
        and abi information to the filesystem as JSON.

        Note: Unless you are developing NuCypher, you most likely won't ever
        need to use this.
        """
        contract_data = [contract_name, contract_address, contract_abi]
        registry_data = self.__read()
        registry_data.append(contract_data)
        self.__write(registry_data)

    def search(self, contract_name: str=None, contract_address: str=None):
        """
        Searches the registry for a contract with the provided name or address
        and returns the contracts.
        """
        if not (bool(contract_name) ^ bool(contract_address)):
            raise ValueError("Pass contract_name or contract_address, not both.")

        contracts = list()
        registry_data = self.__read()
        for name, addr, abi in registry_data:
            if (contract_name or contract_address) == name:
                contracts.append((name, addr, abi))
        return contracts[0] if len(contracts) == 1 else return contracts


class ControlCircumflex:
    """
    Interacts with a solidity compiler and a registry in order to instantiate compiled
    ethereum contracts with the given web3 provider backend.
    """
    __fallabck_providers = (IPCProvider(ipc_path='/tmp/geth.ipc'), )  # user-managed geth over IPC default
    __default_timeout = 10  # seconds
    __default_network = 'tester'
    __default_transaction_gas_limit = 500000  # TODO: determine sensible limit and validate transactions

    class UnknownContract(Exception):
        pass

    class InterfaceError(Exception):
        pass

    def __init__(self, network_name: str=None, endpoint_uri: str=None,
                 websocket=False, ipc_path=None, timeout=None, providers: list=None,
                 registry: EthereumContractRegistry=None, compiler: SolidityCompiler=None):

        """
        A blockchain "network inerface"; The circumflex wraps entirely around the bounds of
        contract operations including compilation, deployment, and execution.


         Solidity Files -- SolidityCompiler ---                  --- HTTPProvider --
                                               |                |                   |
                                               |                |                    -- External EVM (geth, etc.)
                                                                                    |
                                               *ControlCircumflex* -- IPCProvider --

                                               |      |         |
                                               |      |         |
         Registry File -- ContractRegistry --       |          ---- TestProvider -- EthereumTester
                                                      |
                                                      |                                  |
                                                      |
                                                                                       Pyevm (development chain)
                                                 Blockchain

                                                      |

                                                    Agent ... (Contract API)

                                                      |

                                                Character / Actor


        The circumflex is the junction of the solidity compiler, a contract registry, and a collection of
        web3 network __providers as a means of interfacing with the ethereum blockchain to execute
        or deploy contract code on the network.


        Compiler and Registry Usage
        -----------------------------

        Contracts are freshly re-compiled if an instance of SolidityCompiler is passed; otherwise,
        The registry will read contract data saved to disk that is be used to retrieve contact address and op-codes.
        Optionally, A registry instance can be passed instead.


        Provider Usage
        ---------------
        https: // github.com / ethereum / eth - tester     # available-backends


        * HTTP Provider - supply endpiont_uri
        * Websocket Provider - supply endpoint uri and websocket=True
        * IPC Provider - supply IPC path
        * Custom Provider - supply an iterable of web3.py provider instances

        """

        self.__network = network_name if network_name is not None else self.__default_network
        self.timeout = timeout if timeout is not None else self.__default_timeout

        #
        # Providers
        #

        # If custom __providers are not injected...
        self.__providers = list() if providers is None else providers
        if providers is None:
            # Mutates self.__providers
            self.add_provider(endpoint_uri=endpoint_uri, websocket=websocket,
                              ipc_path=ipc_path, timeout=timeout)

        web3_instance = Web3(providers=self.__providers)  # Instantiate Web3 object with provider
        self.w3 = web3_instance                           # capture web3

        # if a SolidityCompiler class instance was passed, compile from solidity source code
        recompile = True if compiler is not None else False
        self.__recompile = recompile
        self.__sol_compiler = compiler

        # Setup the registry and base contract factory cache
        registry = registry if registry is not None else EthereumContractRegistry(chain_name=network)
        self._registry = registry

        # Execute the compilation if we're recompiling, otherwise read compiled contract data from the registry
        interfaces = self.__sol_compiler.compile() if self.__recompile is True else self._registry.dump_chain()
        self.__raw_contract_cache = interfaces

    @property
    def network(self) -> str:
        return self.__network

    @property
    def is_connected(self) -> bool:
        """
        https://web3py.readthedocs.io/en/stable/__providers.html#examples-using-automated-detection
        """
        return self.w3.isConnected()

    @property
    def version(self) -> str:
        """Return node version information"""
        return self.w3.version.node           # type of connected node

    def add_provider(self, provider=None, endpoint_uri: str=None, websocket=False, ipc_path=None, timeout=None) -> None:

        if provider is None:
            # Validate parameters
            if websocket and not endpoint_uri:
                if ipc_path is not None:
                    raise self.InterfaceError("Use either HTTP/Websocket or IPC params, not both.")
                raise self.InterfaceError('Must pass endpoint_uri when using websocket __providers.')

            if ipc_path is not None:
                if endpoint_uri or websocket:
                    raise self.InterfaceError("Use either HTTP/Websocket or IPC params, not both.")

            # HTTP / Websocket Provider
            if endpoint_uri is not None:
                if websocket is True:
                    provider = WebsocketProvider(endpoint_uri)
                else:
                    provider = HTTPProvider(endpoint_uri)

            # IPC Provider
            elif ipc_path:
                provider = IPCProvider(ipc_path=ipc_path, testnet=False, timeout=timeout)
            else:
                raise self.InterfaceError("Invalid interface parameters. Pass endpoint_uri or ipc_path")

        self.__providers.append(provider)

    def get_contract_factory(self, contract_name) -> Contract:
        """Retrieve compiled interface data from the cache and return web3 contract"""
        try:
            interface = self.__raw_contract_cache[contract_name]
        except KeyError:
            raise self.UnknownContract('{} is not a compiled contract.'.format(contract_name))

        contract = self.w3.eth.contract(abi=interface['abi'],
                                        bytecode=interface['bin'],
                                        ContractFactoryClass=Contract)

        return contract

    def get_contract_address(self, contract_name: str) -> List[str]:
        """Retrieve all known addresses for this contract"""
        contracts = self._registry.lookup_contract(contract_name=contract_name)
        addresses = [c['addr'] for c in contracts]
        return addresses

    def get_contract(self, address: str) -> Contract:
        """Instantiate a deployed contract from registry data"""
        contract_data = self._registry.dump_contract(address=address)
        contract = self.w3.eth.contract(abi=contract_data['abi'], address=contract_data['addr'])
        return contract


class DeployerCircumflex(ControlCircumflex):

    def __init__(self, deployer_address: str=None, *args, **kwargs):

        # Depends on web3 instance
        super().__init__(*args, **kwargs)
        self.__deployer_address = deployer_address if deployer_address is not None else constants.NO_DEPLOYER_CONFIGURED

    @property
    def deployer_address(self):
        return self.__deployer_address

    @deployer_address.setter
    def deployer_address(self, ether_address: str) -> None:
        if self.deployer_address is not constants.NO_DEPLOYER_CONFIGURED:
            raise RuntimeError("{} already has a deployer address set.".format(self.__class__.__name__))
        self.__deployer_address = ether_address

    def deploy_contract(self, contract_name: str, *args, **kwargs) -> Tuple[Contract, str]:
        """
        Retrieve compiled interface data from the cache and
        return an instantiated deployed contract
        """

        #
        # Build the deployment tx #
        #
        contract_factory = self.get_contract_factory(contract_name=contract_name)
        deploy_transaction = {'from': self.deployer_address, 'gasPrice': self.w3.eth.gasPrice}  # TODO: price?
        deploy_bytecode = contract_factory.constructor(*args, **kwargs).buildTransaction(deploy_transaction)

        # TODO: Logging
        contract_sizes = dict()
        if len(deploy_bytecode['data']) > 1000:
            contract_sizes[contract_name] = str(len(deploy_bytecode['data']))

        #
        # Transmit the deployment tx #
        #
        txhash = contract_factory.constructor(*args, **kwargs).transact(transaction=deploy_transaction)

        # Wait for receipt
        receipt = self.w3.eth.waitForTransactionReceipt(txhash)
        address = receipt['contractAddress']

        #
        # Instantiate & enroll contract
        #
        contract = contract_factory(address=address)
        self._registry.enroll(contract_name=contract_name,
                               contract_addr=contract.address,
                               contract_abi=contract_factory.abi)

        return contract, txhash
