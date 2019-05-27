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


from urllib.parse import urlparse

from eth_keys.datatypes import PublicKey, Signature
from eth_utils import to_canonical_address
from twisted.logger import Logger
from typing import Tuple, Union, List
from web3 import Web3, WebsocketProvider, HTTPProvider, IPCProvider
from web3.contract import Contract
from web3.providers.eth_tester.main import EthereumTesterProvider
import os
from typing import Tuple, Union
from urllib.parse import urlparse

from constant_sorrow.constants import (
    NO_BLOCKCHAIN_CONNECTION,
    NO_COMPILATION_PERFORMED,
    MANUAL_PROVIDERS_SET,
    NO_DEPLOYER_CONFIGURED,
    UNKNOWN_TX_STATUS
)
from eth_keys.datatypes import PublicKey, Signature
from eth_tester import EthereumTester
from eth_tester import PyEVMBackend
from eth_utils import to_canonical_address
from twisted.logger import Logger
from web3 import Web3, WebsocketProvider, HTTPProvider, IPCProvider
from web3.contract import Contract
from web3.providers.eth_tester.main import EthereumTesterProvider

from nucypher.blockchain.eth.clients import NuCypherGethDevProcess
from nucypher.blockchain.eth.registry import EthereumContractRegistry
from nucypher.blockchain.eth.sol.compile import SolidityCompiler
import pprint


Web3Providers = Union[IPCProvider, WebsocketProvider, HTTPProvider, EthereumTester]


class BlockchainInterface:
    """
    Interacts with a solidity compiler and a registry in order to instantiate compiled
    ethereum contracts with the given web3 provider backend.
    """
    __default_timeout = 180  # seconds
    __default_transaction_gas = 500_000  # TODO #842: determine sensible limit and validate transactions

    process = None  # TODO

    class InterfaceError(Exception):
        pass

    class NoProvider(InterfaceError):
        pass

    class ConnectionFailed(InterfaceError):
        pass

    class UnknownContract(InterfaceError):
        pass

    def __init__(self,
                 provider_uri: str = None,
                 provider=None,
                 auto_connect: bool = True,
                 timeout: int = None,
                 registry: EthereumContractRegistry = None,
                 compiler: SolidityCompiler = None) -> None:

        """
        A blockchain "network interface"; The circumflex wraps entirely around the bounds of
        contract operations including compilation, deployment, and execution.

         Filesystem          Configuration           Node              Client                  EVM
        ================ ====================== =============== =====================  ===========================

         Solidity Files -- SolidityCompiler ---                  --- HTTPProvider ------ ...
                                               |                |
                                               |                |

                                              *BlockchainInterface* -- IPCProvider ----- External EVM (geth, parity...)

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

         Key Files ------ NodeConfiguration -------- Agent ... (Contract API)

                        |                |             |
                        |                |
                        |                 ---------- Actor ... (Blockchain-Character API)
                        |
                        |                              |
                        |
         Config File ---                          Character ... (Public API)

                                                       |

                                                     Human


        The BlockchainInterface is the junction of the solidity compiler, a contract registry, and a collection of
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

        self.log = Logger("blockchain-interface")

        #
        # Providers
        #

        self.w3 = NO_BLOCKCHAIN_CONNECTION
        self.__provider = provider or NO_BLOCKCHAIN_CONNECTION
        self.provider_uri = NO_BLOCKCHAIN_CONNECTION
        self.timeout = timeout if timeout is not None else self.__default_timeout

        if provider_uri and provider:
            raise self.InterfaceError("Pass a provider URI string, or a list of provider instances.")
        elif provider_uri:
            self.provider_uri = provider_uri
            self.attach_provider(provider_uri=provider_uri)
        elif provider:
            self.provider_uri = MANUAL_PROVIDERS_SET
            self.attach_provider(provider)
        else:
            self.log.warn("No provider supplied for new blockchain interface; Using defaults")

        # Ethereum client metadata
        self._node_technology = NO_BLOCKCHAIN_CONNECTION
        self._node_version = NO_BLOCKCHAIN_CONNECTION
        self._platform = NO_BLOCKCHAIN_CONNECTION
        self._backend = NO_BLOCKCHAIN_CONNECTION

        # if a SolidityCompiler class instance was passed, compile from solidity source code
        recompile = True if compiler is not None else False
        self.__recompile = recompile
        self.__sol_compiler = compiler

        # Setup the registry and base contract factory cache
        registry = registry if registry is not None else EthereumContractRegistry()
        self.registry = registry
        self.log.info("Using contract registry {}".format(self.registry.filepath))

        if self.__recompile is True:
            # Execute the compilation if we're recompiling
            # Otherwise read compiled contract data from the registry
            interfaces = self.__sol_compiler.compile()
            __raw_contract_cache = interfaces
        else:
            __raw_contract_cache = NO_COMPILATION_PERFORMED
        self.__raw_contract_cache = __raw_contract_cache

        # Auto-connect
        self.autoconnect = auto_connect
        if self.autoconnect is True:
            self.connect()

    def __repr__(self):
        r = '{name}({uri})'.format(name=self.__class__.__name__, uri=self.provider_uri)
        return r

    @property
    def client_version(self) -> str:
        if self.__provider is NO_BLOCKCHAIN_CONNECTION:
            return "Unknown"

        if self.is_connected:
            node_info = self.w3.clientVersion.split(os.sep)
            node_technology, node_version, platform, go_version = node_info
        else:
            return str(NO_BLOCKCHAIN_CONNECTION)

        return node_technology.lower()

    def connect(self):
        self.log.info("Connecting to {}".format(self.provider_uri))

        if self.__provider is NO_BLOCKCHAIN_CONNECTION:
            raise self.NoProvider("There are no configured blockchain providers")

        # Connect
        web3_instance = Web3(provider=self.__provider)  # Instantiate Web3 object with provider
        self.w3 = web3_instance

        # Check connection
        if not self.is_connected:
            raise self.ConnectionFailed('Failed to connect to provider: {}'.format(self.__provider))

        if self.is_connected:
            self.log.info('ATTACHED WEB3 PROVIDER {}'.format(self.provider_uri))
            node_info = self.w3.clientVersion.split('/')

            try:
                self._node_technology, self._node_version, self._platform, self._backend = node_info

            # Gracefully degrade
            except ValueError:
                self._node_technology, self._node_version, self._platform = node_info
                self._backend = NotImplemented
                # Raises ValueError if the ethereum client does not support the nodeInfo endpoint

            return self.is_connected
        else:
            raise self.ConnectionFailed("Failed to connect to {}.".format(self.provider_uri))

    @property
    def provider(self) -> Union[IPCProvider, WebsocketProvider, HTTPProvider]:
        return self.__provider

    @property
    def is_connected(self) -> bool:
        """
        https://web3py.readthedocs.io/en/stable/__provider.html#examples-using-automated-detection
        """
        return self.w3.isConnected()

    @property
    def node_version(self) -> str:
        """Return node version information"""
        return self.w3.node_version.node

    def attach_provider(self,
                        provider: Web3Providers = None,
                        provider_uri: str = None) -> None:
        """
        https://web3py.readthedocs.io/en/latest/providers.html#providers
        """

        if not provider_uri and not provider:
            raise self.NoProvider("No URI or provider instances supplied.")

        if provider_uri and not provider:
            uri_breakdown = urlparse(provider_uri)

            #
            # Web3 Providers
            #

            # Test Endpoints

            if uri_breakdown.scheme == 'tester':

                if uri_breakdown.netloc == 'pyevm':
                    # https://web3py.readthedocs.io/en/latest/providers.html#httpprovider
                    from nucypher.utilities.sandbox.constants import PYEVM_GAS_LIMIT, NUMBER_OF_ETH_TEST_ACCOUNTS

                    # Initialize
                    genesis_params = PyEVMBackend._generate_genesis_params(overrides={'gas_limit': PYEVM_GAS_LIMIT})
                    pyevm_backend = PyEVMBackend(genesis_parameters=genesis_params)
                    pyevm_backend.reset_to_genesis(genesis_params=genesis_params, num_accounts=NUMBER_OF_ETH_TEST_ACCOUNTS)

                    # Test provider entry-point
                    eth_tester = EthereumTester(backend=pyevm_backend, auto_mine_transactions=True)
                    provider = EthereumTesterProvider(ethereum_tester=eth_tester)

                elif uri_breakdown.netloc == 'geth':

                    # geth --dev
                    geth_process = NuCypherGethDevProcess()
                    geth_process.start()
                    geth_process.wait_for_ipc(timeout=30)
                    provider = IPCProvider(ipc_path=geth_process.ipc_path, timeout=self.timeout)
                    BlockchainInterface.process = geth_process

                elif uri_breakdown.netloc == 'ganache':
                    provider = HTTPProvider(endpoint_uri='http://localhost:7545')  # Default Ganache "TestRPC" Endpoint

                else:
                    raise ValueError("{} is an invalid or unsupported blockchain provider URI".format(provider_uri))

            # Shortcuts

            # - Auto-Detect -
            elif uri_breakdown.scheme == 'auto':
                from web3.auto import w3
                # how-automated-detection-works: https://web3py.readthedocs.io/en/latest/providers.html
                connected = w3.isConnected()
                if not connected:
                    raise self.InterfaceError('Cannot auto-detect node.  Provide a full URI instead.')
                provider = w3.provider

            # - Infura -
            elif uri_breakdown.scheme == 'infura':
                # https://web3py.readthedocs.io/en/latest/providers.html#infura-mainnet
                infura_envvar = 'WEB3_INFURA_API_SECRET'
                if infura_envvar not in os.environ:
                    raise self.InterfaceError(f'{infura_envvar} must be set in order to use an Infura Web3 provider.')
                from web3.auto.infura import w3
                connected = w3.isConnected()
                if not connected:
                    raise self.InterfaceError('Cannot auto-detect node.  Provide a full URI instead.')
                provider = w3.provider

            # Built-In

            # - IPC -
            elif uri_breakdown.scheme in ('ipc', 'file'):
                # https://web3py.readthedocs.io/en/latest/providers.html#ipcprovider
                provider = IPCProvider(ipc_path=uri_breakdown.path, timeout=self.timeout)

            # - Websocket -
            elif uri_breakdown.scheme == 'ws':
                # https://web3py.readthedocs.io/en/latest/providers.html#websocketprovider
                provider = WebsocketProvider(endpoint_uri=provider_uri)

            # - HTTP -
            elif uri_breakdown.scheme in ('http', 'https'):
                # https://web3py.readthedocs.io/en/latest/providers.html#httpprovider
                provider = HTTPProvider(endpoint_uri=provider_uri)

            else:
                raise self.InterfaceError(f"'{uri_breakdown.scheme}' is not a supported Web3 provider "
                                          f"protocol scheme or shortcut.")

            self.__provider = provider

    @classmethod
    def disconnect(cls):
        if BlockchainInterface.process:
            if BlockchainInterface.process.is_running:
                BlockchainInterface.process.stop()

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
            contract = self.w3.eth.contract(abi=interface['abi'],
                                            bytecode=interface['bin'],
                                            ContractFactoryClass=Contract)
            return contract

    def _wrap_contract(self,
                       wrapper_contract: Contract,
                       target_contract: Contract,
                       factory=Contract) -> Contract:
        """
        Used for upgradeable contracts; Returns a new contract object assembled
        with its own address but the abi of the other.
        """

        # Wrap the contract
        wrapped_contract = self.w3.eth.contract(abi=target_contract.abi,
                                                address=wrapper_contract.address,
                                                ContractFactoryClass=factory)
        return wrapped_contract

    def get_contract_by_address(self, address: str):
        """Read a single contract's data from the registrar and return it."""
        try:
            contract_records = self.registry.search(contract_address=address)
        except RuntimeError:
            # TODO #461: Integrate with Registry
            raise self.InterfaceError(f'Corrupted contract registry: {self.registry.filepath}.')
        else:
            if not contract_records:
                raise self.UnknownContract(f"No such contract with address: {address}.")
            return contract_records[0]

    def get_proxy(self, target_address: str, proxy_name: str, factory: Contract = Contract):

        # Lookup proxies; Search for a registered proxy that targets this contract record
        records = self.registry.search(contract_name=proxy_name)

        dispatchers = list()
        for name, addr, abi in records:
            proxy_contract = self.w3.eth.contract(abi=abi,
                                                  address=addr,
                                                  ContractFactoryClass=factory)

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

    def get_contract_by_name(self,
                             name: str,
                             proxy_name: str = None,
                             use_proxy_address: bool = True,
                             factory: Contract = Contract) -> Union[Contract, List[tuple]]:
        """
        Instantiate a deployed contract from registry data,
        and assimilate it with it's proxy if it is upgradeable,
        or return all registered records if use_proxy_address is False.
        """

        target_contract_records = self.registry.search(contract_name=name)

        if not target_contract_records:
            raise self.UnknownContract(f"No such contract records with name {name}.")

        if proxy_name:  # It's upgradeable
            # Lookup proxies; Search fot a published proxy that targets this contract record

            proxy_records = self.registry.search(contract_name=proxy_name)

            results = list()
            for proxy_name, proxy_addr, proxy_abi in proxy_records:
                proxy_contract = self.w3.eth.contract(abi=proxy_abi,
                                                      address=proxy_addr,
                                                      ContractFactoryClass=factory)

                # Read this dispatchers target address from the blockchain
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
        unified_contract = self.w3.eth.contract(abi=selected_abi,
                                                address=selected_address,
                                                ContractFactoryClass=factory)

        return unified_contract

    def call_backend_sign(self, account: str, message: bytes) -> str:
        """
        Calls the appropriate signing function for the specified account on the
        backend. If the backend is based on eth-tester, then it uses the
        eth-tester signing interface to do so.
        """

        if isinstance(self.provider, EthereumTesterProvider):
            # Tests only
            address = to_canonical_address(account)
            sig_key = self.provider.ethereum_tester.backend._key_lookup[address]
            signed_message = sig_key.sign_msg(message)
            return signed_message

        else:
            return self.w3.eth.sign(account, data=message)  # TODO: Use node signing APIs?

    def call_backend_verify(self, pubkey: PublicKey, signature: Signature, msg_hash: bytes) -> bool:
        """
        Verifies a hex string signature and message hash are from the provided
        public key.
        """
        is_valid_sig = signature.verify_msg_hash(msg_hash, pubkey)
        sig_pubkey = signature.recover_public_key_from_msg_hash(msg_hash)
        return is_valid_sig and (sig_pubkey == pubkey)

    def unlock_account(self, address, password, duration=60*30):
        # TODO: Parity
        # TODO: Duration

        if 'tester' in self.provider_uri:
            return True  # Test accounts are unlocked by default.

        elif self.client_version == 'geth':
            return self.w3.geth.personal.unlockAccount(address, password, duration)

        else:
            raise self.InterfaceError(f'{self.client_version} is not a supported ETH node backend.')


class BlockchainDeployerInterface(BlockchainInterface):

    class NoDeployerAddress(RuntimeError):
        pass

    class DeploymentFailed(RuntimeError):
        pass

    def __init__(self, deployer_address: str=None, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)  # Depends on web3 instance
        self.__deployer_address = deployer_address if deployer_address is not None else NO_DEPLOYER_CONFIGURED

    @property
    def deployer_address(self):
        return self.__deployer_address

    @deployer_address.setter
    def deployer_address(self, checksum_address: str) -> None:
        self.__deployer_address = checksum_address

    def deploy_contract(self,
                        contract_name: str,
                        *constructor_args,
                        enroll: bool = True,
                        gas_limit: int = None,
                        **kwargs
                        ) -> Tuple[Contract, str]:
        """
        Retrieve compiled interface data from the cache and
        return an instantiated deployed contract
        """
        if self.__deployer_address is NO_DEPLOYER_CONFIGURED:
            raise self.NoDeployerAddress

        #
        # Build the deployment transaction #
        #

        deploy_transaction = {'from': self.deployer_address, 'gasPrice': self.w3.eth.gasPrice}
        if gas_limit:
            deploy_transaction.update({'gas': gas_limit})

        self.log.info("Deployer address is {}".format(deploy_transaction['from']))

        contract_factory = self.get_contract_factory(contract_name=contract_name)
        transaction = contract_factory.constructor(*constructor_args, **kwargs).buildTransaction(deploy_transaction)
        self.log.info("Deploying contract: {}: {} bytes".format(contract_name, len(transaction['data'])))

        #
        # Transmit the deployment tx #
        #

        txhash = self.w3.eth.sendTransaction(transaction=transaction)
        self.log.info("{} Deployment TX sent : txhash {}".format(contract_name, txhash.hex()))

        # Wait for receipt
        self.log.info(f"Waiting for deployment receipt for {contract_name}")
        receipt = self.w3.eth.waitForTransactionReceipt(txhash, timeout=240)

        #
        # Verify deployment success
        #

        # Primary check
        deployment_status = receipt.get('status', UNKNOWN_TX_STATUS)
        if deployment_status is 0:
            failure = f"{contract_name.upper()} Deployment transaction transmitted, but receipt returned status code 0. " \
                      f"Full receipt: \n {pprint.pformat(receipt, indent=2)}"
            raise self.DeploymentFailed(failure)

        if deployment_status is UNKNOWN_TX_STATUS:
            self.log.info(f"Unknown transaction status for {txhash} (receipt did not contain a status field)")

            # Secondary check TODO: Is this a sensible check?
            tx = self.w3.eth.getTransaction(txhash)
            if tx["gas"] == receipt["gasUsed"]:
                raise self.DeploymentFailed(f"Deployment transaction consumed 100% of transaction gas."
                                            f"Full receipt: \n {pprint.pformat(receipt, indent=2)}")

        # Success
        address = receipt['contractAddress']
        self.log.info("Confirmed {} deployment: address {}".format(contract_name, address))

        #
        # Instantiate & Enroll contract
        #

        contract = self.w3.eth.contract(address=address, abi=contract_factory.abi)

        if enroll is True:
            self.registry.enroll(contract_name=contract_name,
                                 contract_address=contract.address,
                                 contract_abi=contract_factory.abi)

        return contract, txhash  # receipt
