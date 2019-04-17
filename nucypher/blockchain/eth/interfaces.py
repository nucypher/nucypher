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
from typing import Tuple, Union
from web3 import Web3, WebsocketProvider, HTTPProvider, IPCProvider
from web3.contract import Contract
from web3.providers.eth_tester.main import EthereumTesterProvider

from constant_sorrow.constants import (
    NO_BLOCKCHAIN_CONNECTION,
    NO_COMPILATION_PERFORMED,
    MANUAL_PROVIDERS_SET,
    NO_DEPLOYER_CONFIGURED
)
from eth_tester import EthereumTester
from eth_tester import PyEVMBackend
from nucypher.blockchain.eth.registry import EthereumContractRegistry
from nucypher.blockchain.eth.sol.compile import SolidityCompiler
from nucypher.blockchain.eth.constants import NUMBER_OF_ETH_TEST_ACCOUNTS


class BlockchainInterface:
    """
    Interacts with a solidity compiler and a registry in order to instantiate compiled
    ethereum contracts with the given web3 provider backend.
    """
    __default_timeout = 10  # seconds
    # __default_transaction_gas_limit = 500000  # TODO #842: determine sensible limit and validate transactions

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


        * HTTP Provider - supply endpiont_uri
        * Websocket Provider - supply endpoint uri and websocket=True
        * IPC Provider - supply IPC path
        * Custom Provider - supply an iterable of web3.py provider instances

        """

        self.log = Logger("blockchain-interface")                       # type: Logger

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
            self.add_provider(provider_uri=provider_uri)
        elif provider:
            self.provider_uri = MANUAL_PROVIDERS_SET
            self.add_provider(provider)
        else:
            self.log.warn("No provider supplied for new blockchain interface; Using defaults")

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
            self.log.info('Successfully Connected to {}'.format(self.provider_uri))
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

    def add_provider(self,
                     provider: Union[IPCProvider, WebsocketProvider, HTTPProvider] = None,
                     provider_uri: str = None,
                     timeout: int = None) -> None:

        if not provider_uri and not provider:
            raise self.NoProvider("No URI or provider instances supplied.")

        if provider_uri and not provider:
            uri_breakdown = urlparse(provider_uri)

            # PyEVM
            if uri_breakdown.scheme == 'tester':

                if uri_breakdown.netloc == 'pyevm':
                    from nucypher.utilities.sandbox.constants import PYEVM_GAS_LIMIT
                    genesis_params = PyEVMBackend._generate_genesis_params(overrides={'gas_limit': PYEVM_GAS_LIMIT})
                    pyevm_backend = PyEVMBackend(genesis_parameters=genesis_params)
                    pyevm_backend.reset_to_genesis(genesis_params=genesis_params,
                                                   num_accounts=NUMBER_OF_ETH_TEST_ACCOUNTS)
                    eth_tester = EthereumTester(backend=pyevm_backend, auto_mine_transactions=True)
                    provider = EthereumTesterProvider(ethereum_tester=eth_tester)
                elif uri_breakdown.netloc == 'geth':
                    # Hardcoded gethdev IPC provider
                    provider = IPCProvider(ipc_path='/tmp/geth.ipc', timeout=timeout)

                else:
                    raise ValueError("{} is an invalid or unsupported blockchain provider URI".format(provider_uri))

            # IPC
            elif uri_breakdown.scheme == 'ipc':
                provider = IPCProvider(ipc_path=uri_breakdown.path, timeout=timeout)

            # Websocket
            elif uri_breakdown.scheme == 'ws':
                provider = WebsocketProvider(endpoint_uri=provider_uri)

            # HTTP
            elif uri_breakdown.scheme in ('http', 'https'):
                provider = HTTPProvider(endpoint_uri=provider_uri)

            else:
                raise self.InterfaceError("'{}' is not a blockchain provider protocol".format(uri_breakdown.scheme))

            self.__provider = provider

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

    def _wrap_contract(self, wrapper_contract: Contract,
                       target_contract: Contract, factory=Contract) -> Contract:
        """
        Used for upgradeable contracts;
        Returns a new contract object assembled with the address of one contract but the abi or another.
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
            raise self.InterfaceError('Corrupted Registrar')  # TODO #461: Integrate with Registry
        else:
            if not contract_records:
                raise self.UnknownContract("No such contract with address {}".format(address))
            return contract_records[0]

    def get_contract_by_name(self,
                             name: str,
                             proxy_name: str = None,
                             use_proxy_address: bool = True,
                             factory: Contract = Contract) -> Contract:
        """
        Instantiate a deployed contract from registry data,
        and assimilate it with it's proxy if it is upgradeable.
        """

        target_contract_records = self.registry.search(contract_name=name)

        if not target_contract_records:
            raise self.UnknownContract("No such contract records with name {}".format(name))

        if proxy_name:  # It's upgradeable
            # Lookup proxies; Search fot a published proxy that targets this contract record

            proxy_records = self.registry.search(contract_name=proxy_name)

            unified_pairs = list()
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

                    unified_pairs.append(pair)

            if len(unified_pairs) > 1:
                address, abi = unified_pairs[0]
                message = "Multiple {} deployments are targeting {}".format(proxy_name, address)
                raise self.InterfaceError(message.format(name))

            else:
                selected_address, selected_abi = unified_pairs[0]

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
        provider = self.provider
        if isinstance(provider, EthereumTesterProvider):
            address = to_canonical_address(account)
            sig_key = provider.ethereum_tester.backend._key_lookup[address]
            signed_message = sig_key.sign_msg(message)
            return signed_message
        else:
            return self.w3.eth.sign(account, data=message)  # TODO: Technically deprecated...

    def call_backend_verify(self, pubkey: PublicKey, signature: Signature, msg_hash: bytes):
        """
        Verifies a hex string signature and message hash are from the provided
        public key.
        """
        is_valid_sig = signature.verify_msg_hash(msg_hash, pubkey)
        sig_pubkey = signature.recover_public_key_from_msg_hash(msg_hash)

        return is_valid_sig and (sig_pubkey == pubkey)

    def unlock_account(self, address, password, duration):
        if 'tester' in self.provider_uri:
            return True  # Test accounts are unlocked by default.
        return self.w3.geth.personal.unlockAccount(address, password, duration)


class BlockchainDeployerInterface(BlockchainInterface):

    class NoDeployerAddress(RuntimeError):
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

    def deploy_contract(self, contract_name: str, *constructor_args, enroll: bool = True, **kwargs) -> Tuple[Contract, str]:
        """
        Retrieve compiled interface data from the cache and
        return an instantiated deployed contract
        """
        if self.__deployer_address is NO_DEPLOYER_CONFIGURED:
            raise self.NoDeployerAddress

        #
        # Build the deployment tx #
        #
        deploy_transaction = {'from': self.deployer_address, 'gasPrice': self.w3.eth.gasPrice}
        self.log.info("Deployer address is {}".format(deploy_transaction['from']))

        contract_factory = self.get_contract_factory(contract_name=contract_name)
        deploy_bytecode = contract_factory.constructor(*constructor_args).buildTransaction(deploy_transaction)
        self.log.info("Deploying contract: {}: {} bytes".format(contract_name, len(deploy_bytecode['data'])))

        #
        # Transmit the deployment tx #
        #
        txhash = contract_factory.constructor(*constructor_args, **kwargs).transact(transaction=deploy_transaction)
        self.log.info("{} Deployment TX sent : txhash {}".format(contract_name, txhash.hex()))

        # Wait for receipt
        receipt = self.w3.eth.waitForTransactionReceipt(txhash)
        address = receipt['contractAddress']
        self.log.info("Confirmed {} deployment: address {}".format(contract_name, address))

        #
        # Instantiate & Enroll contract
        #
        contract = contract_factory(address=address)

        if enroll is True:
            self.registry.enroll(contract_name=contract_name,
                                 contract_address=contract.address,
                                 contract_abi=contract_factory.abi)
        return contract, txhash
