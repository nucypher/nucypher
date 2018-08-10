import binascii
import json
import os
import warnings
from pathlib import Path
from typing import Tuple, List
from urllib.parse import urlparse

from constant_sorrow import constants
from eth_utils import to_canonical_address
from eth_keys.datatypes import PublicKey, Signature
from web3.providers.eth_tester.main import EthereumTesterProvider
from web3 import Web3, WebsocketProvider, HTTPProvider, IPCProvider
from web3.contract import Contract

from nucypher.blockchain.eth.sol.compile import SolidityCompiler
from nucypher.config.constants import DEFAULT_CONFIG_ROOT, DEFAULT_INI_FILEPATH, DEFAULT_SIMULATION_REGISTRY_FILEPATH
from nucypher.config.parsers import parse_blockchain_config


class EthereumContractRegistry:
    """
    Records known contracts on the disk for future access and utility. This
    lazily writes to the filesystem during contract enrollment.

    WARNING: Unless you are developing NuCypher, you most likely won't ever need
    to use this.
    """
    __default_registry_path = os.path.join(DEFAULT_CONFIG_ROOT, 'registry.json')

    class RegistryError(Exception):
        pass

    class UnknownContract(RegistryError):
        pass

    class IllegalRegistrar(RegistryError):
        """Raised when invalid data is encountered in the registry"""

    def __init__(self, registry_filepath: str=None):
        self._registry_filepath = registry_filepath or self.__default_registry_path

    @classmethod
    def from_config(cls, filepath=None, **overrides) -> 'EthereumContractRegistry':
        from nucypher.blockchain.eth.utilities import TemporaryEthereumContractRegistry

        filepath = filepath if filepath is None else DEFAULT_INI_FILEPATH
        payload = parse_blockchain_config(filepath=filepath)

        if payload['tmp_registry']:
            # In memory only
            registry = TemporaryEthereumContractRegistry()
        else:
            registry = EthereumContractRegistry(**overrides)

        return registry

    @property
    def registry_filepath(self):
        return self._registry_filepath

    def __write(self, registry_data: list) -> None:
        """
        Writes the registry data list as JSON to the registry file. If no
        file exists, it will create it and write the data. If a file does exist
        it will _overwrite_ everything in it.
        """
        with open(self._registry_filepath, 'w+') as registry_file:
            registry_file.seek(0)
            registry_file.write(json.dumps(registry_data))
            registry_file.truncate()

    def read(self) -> list:
        """
        Reads the registry file and parses the JSON and returns a list.
        If the file is empty or the JSON is corrupt, it will return an empty
        list.
        If you are modifying or updating the registry file, you _must_ call
        this function first to get the current state to append to the dict or
        modify it because _write_registry_file overwrites the file.
        """
        try:
            with open(self._registry_filepath, 'r') as registry_file:
                registry_file.seek(0)
                file_data = registry_file.read()
                if file_data:
                    registry_data = json.loads(file_data)
                else:
                    registry_data = list()  # Existing, but empty registry

        except FileNotFoundError:
            raise self.RegistryError("No registy at filepath: {}".format(self._registry_filepath))

        return registry_data

    def enroll(self, contract_name, contract_address, contract_abi):
        """
        Enrolls a contract to the chain registry by writing the name, address,
        and abi information to the filesystem as JSON.

        Note: Unless you are developing NuCypher, you most likely won't ever
        need to use this.
        """
        contract_data = [contract_name, contract_address, contract_abi]
        registry_data = self.read()
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
        registry_data = self.read()

        for name, addr, abi in registry_data:
            if contract_name == name or contract_address == addr:
                contracts.append((name, addr, abi))

        if not contracts:
            raise self.UnknownContract
        if contract_address and len(contracts) > 1:
            m = "Multiple records returned for address {}"
            raise self.IllegalRegistrar(m.format(contract_address))

        return contracts if contract_name else contracts[0]


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

    def __init__(self,
                 network_name: str = None,
                 provider_uri: str = None,
                 providers: list = None,
                 autoconnect: bool = True,
                 timeout: int = None,
                 registry: EthereumContractRegistry = None,
                 compiler: SolidityCompiler=None) -> None:

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
        if provider_uri and providers:
            raise self.InterfaceError("Pass a provider URI string, or a list of provider instances.")
        self.provider_uri = provider_uri
        self._providers = list() if providers is None else providers

        # If custom __providers are not injected...
        self.w3 = constants.NO_BLOCKCHAIN_CONNECTION
        if autoconnect is True:
            self.connect(provider_uri=self.provider_uri)

        # if a SolidityCompiler class instance was passed, compile from solidity source code
        recompile = True if compiler is not None else False
        self.__recompile = recompile
        self.__sol_compiler = compiler

        # Setup the registry and base contract factory cache
        registry = registry if registry is not None else EthereumContractRegistry()
        self._registry = registry

        if self.__recompile is True:
            # Execute the compilation if we're recompiling, otherwise read compiled contract data from the registry
            interfaces = self.__sol_compiler.compile()
            self.__raw_contract_cache = interfaces

    def connect(self,
                provider_uri: str = None,
                providers: list = None):

        if provider_uri is None and not providers:
            raise self.InterfaceError("No URI supplied.")

        if provider_uri and not providers:
            uri_breakdown = urlparse(provider_uri)
        elif providers and not provider_uri:
            raise NotImplementedError
        else:
            raise self.InterfaceError("Pass a provider URI string or a list of providers, not both.")

        # stub
        if providers is None:
            providers = list()

        # IPC
        if uri_breakdown.scheme == 'ipc':
            provider = IPCProvider(ipc_path=uri_breakdown.path, timeout=self.timeout)

        # Websocket
        elif uri_breakdown.scheme == 'ws':
            provider = WebsocketProvider(endpoint_uri=provider_uri)
            raise NotImplementedError

        # HTTP
        elif uri_breakdown.scheme in ('http', 'https'):
            provider = HTTPProvider(endpoint_uri=provider_uri)
            raise NotImplementedError

        else:
            raise self.InterfaceError("'{}' is not a blockchain provider protocol".format(uri_breakdown.scheme))

        providers.append(provider)

        # Connect
        self._providers = providers
        web3_instance = Web3(providers=self._providers)  # Instantiate Web3 object with provider
        self.w3 = web3_instance

        # Check connection
        if not self.is_connected:
            raise self.InterfaceError('Failed to connect to {}'.format(provider_uri))

        return True

    @classmethod
    def from_config(cls, filepath=None, registry_filepath: str=None) -> 'ControlCircumflex':
        filepath = filepath if filepath is None else DEFAULT_INI_FILEPATH
        payload = parse_blockchain_config(filepath=filepath)

        compiler = SolidityCompiler() if payload['compile'] else None

        registry = EthereumContractRegistry.from_config(filepath=filepath)

        interface_class = ControlCircumflex if not payload['deploy'] else DeployerCircumflex
        circumflex = interface_class(timeout=payload['timeout'],
                                     provider_uri=payload['provider_uri'],
                                     compiler=compiler,
                                     registry=registry)

        return circumflex

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

    def add_provider(self, provider=None, endpoint_uri: str=None,
                     websocket=False, ipc_path=None, timeout=None) -> None:

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

        self._providers.append(provider)

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

    def _wrap_contract(self, dispatcher_contract: Contract,
                       target_contract: Contract, factory=Contract) -> Contract:
        """Used for upgradeable contracts."""

        # Wrap the contract
        wrapped_contract = self.w3.eth.contract(abi=target_contract.abi,
                                                address=dispatcher_contract.address,
                                                ContractFactoryClass=factory)
        return wrapped_contract

    def get_contract_by_address(self, address: str):
        """Read a single contract's data from the registrar and return it."""
        try:
            contract_records = self._registry.search(contract_address=address)
        except RuntimeError:
            raise self.InterfaceError('Corrupted Registrar')  # TODO: Integrate with Registry
        else:
            if not contract_records:
                raise self.InterfaceError("No such contract with address {}".format(address))
            return contract_records[0]

    def get_contract_by_name(self, name: str, upgradeable=False, factory=Contract) -> Contract:
        """
        Instantiate a deployed contract from registrar data,
        and assemble it with it's dispatcher if it is upgradeable.
        """
        target_contract_records = self._registry.search(contract_name=name)

        if not target_contract_records:
            raise self.InterfaceError("No such contract records with name {}".format(name))

        if upgradeable:
            # Lookup dispatchers; Search fot a published dispatcher that targets this contract record
            dispatcher_records = self._registry.search(contract_name='Dispatcher')

            matching_pairs = list()
            for dispatcher_name, dispatcher_addr, dispatcher_abi in dispatcher_records:

                dispatcher_contract = self.w3.eth.contract(abi=dispatcher_abi,
                                                           address=dispatcher_addr,
                                                           ContractFactoryClass=factory)

                # Read this dispatchers target address from the blockchain
                live_target_address = dispatcher_contract.functions.target().call()

                for target_name, target_addr, target_abi in target_contract_records:
                    if target_addr == live_target_address:
                        pair = dispatcher_addr, target_abi
                        matching_pairs.append(pair)

            else:  # for/else

                if len(matching_pairs) == 0:
                    raise self.InterfaceError("No dispatcher targets known contract records for {}".format(name))

                elif len(matching_pairs) > 1:
                    raise self.InterfaceError("There is more than one dispatcher targeting {}".format(name))

                selected_contract_address, selected_contract_abi = matching_pairs[0]
        else:
            if len(target_contract_records) != 1:  # TODO: Allow multiple non-upgradeable records (UserEscrow)
                m = "Multiple records returned from the registry for non-upgradeable contract {}"
                raise self.InterfaceError(m.format(name))

            selected_contract_name, selected_contract_address, selected_contract_abi = target_contract_records[0]

        # Create the contract from selected sources
        unified_contract = self.w3.eth.contract(abi=selected_contract_abi,
                                                address=selected_contract_address,
                                                ContractFactoryClass=factory)

        return unified_contract


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
                              contract_address=contract.address,
                              contract_abi=contract_factory.abi)

        return contract, txhash

    def call_backend_sign(self, account: str, message: bytes) -> str:
        """
        Calls the appropriate signing function for the specified account on the
        backend. If the backend is based on eth-tester, then it uses the
        eth-tester signing interface to do so.
        """
        provider = self._providers[0]
        if isinstance(provider, EthereumTesterProvider):
            address = to_canonical_address(account)
            sig_key = provider.ethereum_tester.backend._key_lookup[address]
            signed_message = sig_key.sign_msg(message)
            return signed_message
        else:
            return self.w3.eth.sign(account, data=message) # Technically deprecated...

    def call_backend_verify(self, pubkey: PublicKey, signature: Signature, msg_hash: bytes):
        """
        Verifies a hex string signature and message hash are from the provided
        public key.
        """
        is_valid_sig = signature.verify_msg_hash(msg_hash, pubkey)
        sig_pubkey = signature.recover_public_key_from_msg_hash(msg_hash)

        return is_valid_sig and (sig_pubkey == pubkey)
