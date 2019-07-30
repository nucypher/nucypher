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

import pprint
from typing import List
from typing import Tuple
from typing import Union
from urllib.parse import urlparse

import requests
from constant_sorrow.constants import (
    NO_BLOCKCHAIN_CONNECTION,
    NO_COMPILATION_PERFORMED,
    NO_DEPLOYER_CONFIGURED,
    UNKNOWN_TX_STATUS,
    NO_PROVIDER_PROCESS,
    READ_ONLY_INTERFACE
)
from eth_tester import EthereumTester
from eth_utils import to_checksum_address
from twisted.logger import Logger
from web3 import Web3, WebsocketProvider, HTTPProvider, IPCProvider
from web3.contract import Contract, ContractFunction
from web3.contract import ContractConstructor
from web3.exceptions import TimeExhausted
from web3.exceptions import ValidationError
from web3.middleware import geth_poa_middleware

from nucypher.blockchain.eth.clients import Web3Client, NuCypherGethProcess
from nucypher.blockchain.eth.providers import (
    _get_tester_pyevm,
    _get_test_geth_parity_provider,
    _get_auto_provider,
    _get_infura_provider,
    _get_IPC_provider,
    _get_websocket_provider,
    _get_HTTP_provider
)
from nucypher.blockchain.eth.registry import EthereumContractRegistry
from nucypher.blockchain.eth.sol.compile import SolidityCompiler
from nucypher.crypto.powers import TransactingPower

Web3Providers = Union[IPCProvider, WebsocketProvider, HTTPProvider, EthereumTester]


class BlockchainInterface:
    """
    Interacts with a solidity compiler and a registry in order to instantiate compiled
    ethereum contracts with the given web3 provider backend.
    """

    TIMEOUT = 180  # seconds
    NULL_ADDRESS = '0x' + '0' * 40

    _instance = NO_BLOCKCHAIN_CONNECTION.bool_value(False)
    process = NO_PROVIDER_PROCESS.bool_value(False)
    Web3 = Web3

    _contract_factory = Contract

    class InterfaceError(Exception):
        pass

    class NoProvider(InterfaceError):
        pass

    class ConnectionFailed(InterfaceError):
        pass

    class UnknownContract(InterfaceError):
        pass

    def __init__(self,
                 poa: bool = True,
                 provider_process: NuCypherGethProcess = NO_PROVIDER_PROCESS,
                 provider_uri: str = NO_BLOCKCHAIN_CONNECTION,
                 transacting_power: TransactingPower = READ_ONLY_INTERFACE,
                 provider: Web3Providers = NO_BLOCKCHAIN_CONNECTION,
                 registry: EthereumContractRegistry = None):

        """
        A blockchain "network interface"; The circumflex wraps entirely around the bounds of
        contract operations including compilation, deployment, and execution.

         Filesystem          Configuration           Node              Client                  EVM
        ================ ====================== =============== =====================  ===========================

         Solidity Files -- SolidityCompiler ---                  --- HTTPProvider ------ ...
                                               |                |
                                               |                |

                                                 *Blockchain* -- IPCProvider ----- External EVM (geth, parity...)

                                               |      |         |
                                               |      |         |
         Registry File -- ContractRegistry ---        |          ---- TestProvider ----- EthereumTester
                                                      |
                        |                             |                                         |
                        |                             |
                                                                                        PyEVM (Development Chain)
         Runtime Files --                 -------- Blockchain
                                         |
                        |                |             |

         Key Files ------ CharacterConfiguration -------- Agent ... (Contract API)

                        |                |             |
                        |                |
                        |                 ---------- Actor ... (Blockchain-Character API)
                        |
                        |                              |
                        |
         Config File ---                           Character ... (Public API)

                                                       |

                                                     Human


        The Blockchain is the junction of the solidity compiler, a contract registry, and a collection of
        web3 network providers as a means of interfacing with the ethereum blockchain to execute
        or deploy contract code on the network.


        Compiler and Registry Usage
        -----------------------------

        Contracts are freshly re-compiled if an instance of SolidityCompiler is passed; otherwise,
        The registry will read contract data saved to disk that is be used to retrieve contact address and op-codes.
        Optionally, A registry instance can be passed instead.


        Provider Usage
        ---------------
        https: // github.com / ethereum / eth - tester     # available-backends


        * HTTP Provider - Web3 HTTP provider, typically JSON RPC 2.0 over HTTP
        * Websocket Provider - Web3 WS provider, typically JSON RPC 2.0 over WS, supply endpoint uri and websocket=True
        * IPC Provider - Web3 File based IPC provider transported over standard I/O
        * Custom Provider - A pre-initialized web3.py provider instance to attach to this interface

        """

        self.log = Logger('Blockchain')
        self.poa = poa
        self.provider_uri = provider_uri
        self._provider = provider
        self._provider_process = provider_process
        self.client = NO_BLOCKCHAIN_CONNECTION
        self.transacting_power = transacting_power
        self.registry = registry
        BlockchainInterface._instance = self

    def __repr__(self):
        r = '{name}({uri})'.format(name=self.__class__.__name__, uri=self.provider_uri)
        return r

    @classmethod
    def from_dict(cls, payload: dict, **overrides) -> 'BlockchainInterface':

        # Apply overrides
        payload.update({k: v for k, v in overrides.items() if v is not None})

        registry = EthereumContractRegistry(registry_filepath=payload['registry_filepath'])
        blockchain = cls(provider_uri=payload['provider_uri'], registry=registry)
        return blockchain

    def to_dict(self) -> dict:
        payload = dict(provider_uri=self.provider_uri,
                       poa=self.poa,
                       registry_filepath=self.registry.filepath)
        return payload

    def _configure_registry(self, fetch_registry: bool = True) -> None:
        RegistryClass = EthereumContractRegistry._get_registry_class(local=self.client.is_local)
        if fetch_registry:
            registry = RegistryClass.from_latest_publication()
        else:
            registry = RegistryClass()
        self.registry = registry
        self.log.info("Using contract registry {}".format(self.registry.filepath))

    @property
    def is_connected(self) -> bool:
        """
        https://web3py.readthedocs.io/en/stable/__provider.html#examples-using-automated-detection
        """
        if self.client is NO_BLOCKCHAIN_CONNECTION:
            return False
        return self.client.is_connected

    def disconnect(self) -> None:
        if self._provider_process:
            self._provider_process.stop()
        self._provider_process = NO_PROVIDER_PROCESS
        self._provider = NO_BLOCKCHAIN_CONNECTION
        BlockchainInterface._instance = NO_BLOCKCHAIN_CONNECTION

    @classmethod
    def reconnect(cls, *args, **kwargs) -> 'BlockchainInterface':
        return cls._instance

    def attach_middleware(self):

        # For use with Proof-Of-Authority test-blockchains
        if self.poa is True:
            self.log.debug('Injecting POA middleware at layer 0')
            self.client.inject_middleware(geth_poa_middleware, layer=0)

    def connect(self, fetch_registry: bool = True, sync_now: bool = False):

        # Spawn child process
        if self._provider_process:
            self._provider_process.start()
            provider_uri = self._provider_process.provider_uri(scheme='file')
        else:
            provider_uri = self.provider_uri
            self.log.info(f"Using external Web3 Provider '{self.provider_uri}'")

        # Attach Provider
        self._attach_provider(provider=self._provider, provider_uri=provider_uri)
        self.log.info("Connecting to {}".format(self.provider_uri))
        if self._provider is NO_BLOCKCHAIN_CONNECTION:
            raise self.NoProvider("There are no configured blockchain providers")

        # Connect Web3 Instance
        try:
            self.w3 = self.Web3(provider=self._provider)
            self.client = Web3Client.from_w3(w3=self.w3)
        except requests.ConnectionError:  # RPC
            raise self.ConnectionFailed(f'Connection Failed - {str(self.provider_uri)} - is RPC enabled?')
        except FileNotFoundError:         # IPC File Protocol
            raise self.ConnectionFailed(f'Connection Failed - {str(self.provider_uri)} - is IPC enabled?')
        else:
            self.attach_middleware()

        # Wait for chaindata sync
        if sync_now:
            self.client.sync()

        # Establish contact with NuCypher contracts
        if not self.registry:
            self._configure_registry(fetch_registry=fetch_registry)

        return self.is_connected

    @property
    def provider(self) -> Union[IPCProvider, WebsocketProvider, HTTPProvider]:
        return self._provider

    def _attach_provider(self, provider: Web3Providers = None, provider_uri: str = None) -> None:
        """
        https://web3py.readthedocs.io/en/latest/providers.html#providers
        """

        if not provider_uri and not provider:
            raise self.NoProvider("No URI or provider instances supplied.")

        if provider_uri and not provider:
            uri_breakdown = urlparse(provider_uri)

            if uri_breakdown.scheme == 'tester':
                providers = {
                    'pyevm': _get_tester_pyevm,
                    'geth': _get_test_geth_parity_provider,
                    'parity-ethereum': _get_test_geth_parity_provider,
                }
                provider_scheme = uri_breakdown.netloc
            else:
                providers = {
                    'auto': _get_auto_provider,
                    'infura': _get_infura_provider,
                    'ipc': _get_IPC_provider,
                    'file': _get_IPC_provider,
                    'ws': _get_websocket_provider,
                    'http': _get_HTTP_provider,
                    'https': _get_HTTP_provider,
                }
                provider_scheme = uri_breakdown.scheme
            try:
                self._provider = providers[provider_scheme](provider_uri)
            except KeyError:
                raise ValueError(f"{provider_uri} is an invalid or unsupported blockchain provider URI")
            else:
                self.provider_uri = provider_uri or NO_BLOCKCHAIN_CONNECTION
        else:
            self._provider = provider

    def send_transaction(self,
                         contract_function: ContractFunction,
                         sender_address: str,
                         payload: dict = None,
                         ) -> dict:

        if self.transacting_power is READ_ONLY_INTERFACE:
            raise self.InterfaceError(str(READ_ONLY_INTERFACE))

        #
        # Build
        #

        if not payload:
            payload = {}

        nonce = self.client.w3.eth.getTransactionCount(sender_address)
        payload.update({'chainId': int(self.client.net_version),
                        'nonce': nonce,
                        'from': sender_address,
                        'gasPrice': self.client.gas_price,
                        # 'gas': 0,  # TODO: Gas Management
                        })

        # Get interface name
        deployment = True if isinstance(contract_function, ContractConstructor) else False

        try:
            transaction_name = contract_function.fn_name.upper()
        except AttributeError:
            if deployment:
                transaction_name = 'DEPLOY'
            else:
                transaction_name = 'UNKNOWN'

        payload_pprint = dict(payload)
        payload_pprint['from'] = to_checksum_address(payload['from'])
        payload_pprint = ', '.join("{}: {}".format(k, v) for k, v in payload_pprint.items())
        self.log.debug(f"[TX-{transaction_name}] | {payload_pprint}")

        # Build transaction payload
        try:
            unsigned_transaction = contract_function.buildTransaction(payload)
        except ValidationError as e:
            # TODO: Handle validation failures for gas limits, invalid fields, etc.
            self.log.warn(f"Validation error: {e}")
            raise
        else:
            if deployment:
                self.log.info(f"Deploying contract: {len(unsigned_transaction['data'])} bytes")


        #
        # Broadcast
        #

        signed_raw_transaction = self.transacting_power.sign_transaction(unsigned_transaction)
        txhash = self.client.send_raw_transaction(signed_raw_transaction)


        try:
            receipt = self.client.wait_for_receipt(txhash, timeout=self.TIMEOUT)
        except TimeExhausted:
            # TODO: Handle transaction timeout
            raise
        else:
            self.log.debug(f"[RECEIPT-{transaction_name}] | txhash: {receipt['transactionHash'].hex()}")

        #
        # Confirm
        #

        # Primary check
        deployment_status = receipt.get('status', UNKNOWN_TX_STATUS)
        if deployment_status is 0:
            failure = f"Transaction transmitted, but receipt returned status code 0. " \
                      f"Full receipt: \n {pprint.pformat(receipt, indent=2)}"
            raise self.InterfaceError(failure)

        if deployment_status is UNKNOWN_TX_STATUS:
            self.log.info(f"Unknown transaction status for {txhash} (receipt did not contain a status field)")

            # Secondary check TODO: Is this a sensible check?
            tx = self.client.get_transaction(txhash)
            if tx["gas"] == receipt["gasUsed"]:
                raise self.InterfaceError(f"Transaction consumed 100% of transaction gas."
                                          f"Full receipt: \n {pprint.pformat(receipt, indent=2)}")

        return receipt

    def get_contract_by_name(self,
                             name: str,
                             proxy_name: str = None,
                             use_proxy_address: bool = True
                             ) -> Union[Contract, List[tuple]]:
        """
        Instantiate a deployed contract from registry data,
        and assimilate it with its proxy if it is upgradeable,
        or return all registered records if use_proxy_address is False.
        """
        target_contract_records = self.registry.search(contract_name=name)

        if not target_contract_records:
            raise self.UnknownContract(f"No such contract records with name {name}.")

        if proxy_name:  # It's upgradeable
            # Lookup proxies; Search for a published proxy that targets this contract record

            proxy_records = self.registry.search(contract_name=proxy_name)

            results = list()
            for proxy_name, proxy_addr, proxy_abi in proxy_records:
                proxy_contract = self.client.w3.eth.contract(abi=proxy_abi,
                                                             address=proxy_addr,
                                                             ContractFactoryClass=self._contract_factory)

                # Read this dispatcher's target address from the blockchain
                proxy_live_target_address = proxy_contract.functions.target().call()
                for target_name, target_addr, target_abi in target_contract_records:

                    if target_addr == proxy_live_target_address:
                        if use_proxy_address:
                            pair = (proxy_addr, target_abi)
                        else:
                            pair = (proxy_live_target_address, target_abi)
                    else:
                        continue

                    results.append(pair)

            if len(results) > 1:
                address, abi = results[0]
                message = "Multiple {} deployments are targeting {}".format(proxy_name, address)
                raise self.InterfaceError(message.format(name))

            else:
                selected_address, selected_abi = results[0]

        else:  # It's not upgradeable
            if len(target_contract_records) != 1:
                m = "Multiple records registered for non-upgradeable contract {}"
                raise self.InterfaceError(m.format(name))
            _target_contract_name, selected_address, selected_abi = target_contract_records[0]

        # Create the contract from selected sources
        unified_contract = self.client.w3.eth.contract(abi=selected_abi,
                                                       address=selected_address,
                                                       ContractFactoryClass=self._contract_factory)

        return unified_contract


class BlockchainDeployerInterface(BlockchainInterface):

    TIMEOUT = 600  # seconds
    _contract_factory = Contract

    class NoDeployerAddress(RuntimeError):
        pass

    class DeploymentFailed(RuntimeError):
        pass

    def __init__(self,
                 deployer_address: str = None,
                 compiler: SolidityCompiler = None,
                 *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.compiler = compiler or SolidityCompiler()
        self.__deployer_address = deployer_address or NO_DEPLOYER_CONFIGURED

    def connect(self, fetch_registry: bool = False, *args, **kwargs):
        super().connect(fetch_registry=fetch_registry, *args, **kwargs)
        self._setup_solidity(compiler=self.compiler)
        return self.is_connected

    @property
    def deployer_address(self):
        return self.__deployer_address

    @deployer_address.setter
    def deployer_address(self, checksum_address: str) -> None:
        self.__deployer_address = checksum_address

    def _setup_solidity(self, compiler: SolidityCompiler = None):

        # if a SolidityCompiler class instance was passed, compile from solidity source code
        self.__sol_compiler = compiler
        if compiler:
            # Execute the compilation if we're recompiling
            # Otherwise read compiled contract data from the registry
            interfaces = self.__sol_compiler.compile()
            __raw_contract_cache = interfaces
        else:
            __raw_contract_cache = NO_COMPILATION_PERFORMED
        self.__raw_contract_cache = __raw_contract_cache

    def deploy_contract(self,
                        contract_name: str,
                        *constructor_args,
                        enroll: bool = True,
                        gas_limit: int = None,
                        **kwargs
                        ) -> Tuple[Contract, dict]:
        """
        Retrieve compiled interface data from the cache and
        return an instantiated deployed contract
        """
        if self.__deployer_address is NO_DEPLOYER_CONFIGURED:
            raise self.NoDeployerAddress

        #
        # Build the deployment transaction #
        #

        deploy_transaction = dict()
        if gas_limit:
            deploy_transaction.update({'gas': gas_limit})

        pprint_args = str(tuple(constructor_args))
        pprint_args = pprint_args.replace("{", "{{").replace("}", "}}")  # See #724
        self.log.info(f"Deploying contract {contract_name} with "
                      f"deployer address {self.deployer_address} "
                      f"and parameters {pprint_args}")

        contract_factory = self.get_contract_factory(contract_name=contract_name)
        transaction_function = contract_factory.constructor(*constructor_args, **kwargs)

        #
        # Transmit the deployment tx #
        #

        receipt = self.send_transaction(contract_function=transaction_function,
                                        sender_address=self.deployer_address,
                                        payload=deploy_transaction)

        #
        # Verify deployment success
        #

        # Success
        address = receipt['contractAddress']
        self.log.info("Confirmed {} deployment: address {}".format(contract_name, address))

        #
        # Instantiate & Enroll contract
        #

        contract = self.client.w3.eth.contract(address=address, abi=contract_factory.abi)

        if enroll is True:
            self.registry.enroll(contract_name=contract_name,
                                 contract_address=contract.address,
                                 contract_abi=contract_factory.abi)

        return contract, receipt  # receipt

    def get_contract_factory(self, contract_name: str) -> Contract:
        """Retrieve compiled interface data from the cache and return web3 contract"""
        try:
            interface = self.__raw_contract_cache[contract_name]
        except KeyError:
            raise self.UnknownContract('{} is not a locally compiled contract.'.format(contract_name))
        except TypeError:
            if self.__raw_contract_cache is NO_COMPILATION_PERFORMED:
                message = "The local contract compiler cache is empty because no compilation was performed."
                raise self.InterfaceError(message)
            raise
        else:
            contract = self.client.w3.eth.contract(abi=interface['abi'],
                                                   bytecode=interface['bin'],
                                                   ContractFactoryClass=Contract)
            return contract

    def _wrap_contract(self, wrapper_contract: Contract, target_contract: Contract) -> Contract:
        """
        Used for upgradeable contracts; Returns a new contract object assembled
        with its own address but the abi of the other.
        """

        # Wrap the contract
        wrapped_contract = self.client.w3.eth.contract(abi=target_contract.abi,
                                                       address=wrapper_contract.address,
                                                       ContractFactoryClass=self._contract_factory)
        return wrapped_contract

    def get_proxy(self, target_address: str, proxy_name: str) -> Contract:

        # Lookup proxies; Search for a registered proxy that targets this contract record
        records = self.registry.search(contract_name=proxy_name)

        dispatchers = list()
        for name, addr, abi in records:
            proxy_contract = self.client.w3.eth.contract(abi=abi,
                                                         address=addr,
                                                         ContractFactoryClass=self._contract_factory)

            # Read this dispatchers target address from the blockchain
            proxy_live_target_address = proxy_contract.functions.target().call()

            if proxy_live_target_address == target_address:
                dispatchers.append(proxy_contract)

        if len(dispatchers) > 1:
            message = f"Multiple Dispatcher deployments are targeting {target_address}"
            raise self.InterfaceError(message)

        try:
            return dispatchers[0]
        except IndexError:
            raise self.UnknownContract(f"No registered Dispatcher deployments target {target_address}")
