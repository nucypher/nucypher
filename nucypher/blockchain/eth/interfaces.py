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


import click
import os
import pprint
import requests
import time
from constant_sorrow.constants import (
    INSUFFICIENT_ETH,
    NO_BLOCKCHAIN_CONNECTION,
    NO_COMPILATION_PERFORMED,
    NO_PROVIDER_PROCESS,
    READ_ONLY_INTERFACE,
    UNKNOWN_TX_STATUS
)
from eth_tester import EthereumTester
from eth_tester.exceptions import TransactionFailed as TestTransactionFailed
from eth_utils import to_checksum_address
from typing import Callable, NamedTuple, Tuple, Union
from urllib.parse import urlparse
from web3 import HTTPProvider, IPCProvider, Web3, WebsocketProvider, middleware
from web3.contract import Contract, ContractConstructor, ContractFunction
from web3.exceptions import TimeExhausted, ValidationError
from web3.gas_strategies import time_based
from web3.middleware import geth_poa_middleware

from nucypher.blockchain.eth.clients import EthereumClient, POA_CHAINS
from nucypher.blockchain.eth.decorators import validate_checksum_address
from nucypher.blockchain.eth.providers import (
    _get_auto_provider,
    _get_HTTP_provider,
    _get_infura_provider,
    _get_IPC_provider,
    _get_mock_test_provider,
    _get_pyevm_test_provider,
    _get_test_geth_parity_provider,
    _get_websocket_provider
)
from nucypher.blockchain.eth.registry import BaseContractRegistry
from nucypher.blockchain.eth.sol.compile import SolidityCompiler
from nucypher.blockchain.eth.utils import get_transaction_name, prettify_eth_amount
from nucypher.characters.control.emitters import JSONRPCStdoutEmitter, StdoutEmitter
from nucypher.utilities.logging import GlobalLoggerSettings, Logger

Web3Providers = Union[IPCProvider, WebsocketProvider, HTTPProvider, EthereumTester]


class VersionedContract(Contract):
    version = None


class BlockchainInterface:
    """
    Interacts with a solidity compiler and a registry in order to instantiate compiled
    ethereum contracts with the given web3 provider backend.
    """

    TIMEOUT = 600  # seconds  # TODO: Correlate with the gas strategy - #2070

    DEFAULT_GAS_STRATEGY = 'medium'
    GAS_STRATEGIES = {'glacial': time_based.glacial_gas_price_strategy,     # 24h
                      'slow': time_based.slow_gas_price_strategy,           # 1h
                      'medium': time_based.medium_gas_price_strategy,       # 5m
                      'fast': time_based.fast_gas_price_strategy            # 60s
                      }

    process = NO_PROVIDER_PROCESS.bool_value(False)
    Web3 = Web3

    _contract_factory = VersionedContract

    class InterfaceError(Exception):
        pass

    class NoProvider(InterfaceError):
        pass

    class UnsupportedProvider(InterfaceError):
        pass

    class ConnectionFailed(InterfaceError):
        pass

    class UnknownContract(InterfaceError):
        pass

    REASONS = {
        INSUFFICIENT_ETH: 'insufficient funds for gas * price + value',
    }

    class TransactionFailed(InterfaceError):

        IPC_CODE = -32000  # (geth)

        def __init__(self,
                     message: str,
                     transaction_dict: dict,
                     contract_function: Union[ContractFunction, ContractConstructor],
                     *args):

            self.base_message = message
            self.name = get_transaction_name(contract_function=contract_function)
            self.payload = transaction_dict
            self.contract_function = contract_function
            self.failures = {
                BlockchainInterface.REASONS[INSUFFICIENT_ETH]: self.insufficient_eth
            }
            self.message = self.failures.get(self.base_message, self.default)
            super().__init__(self.message, *args)

        @property
        def default(self) -> str:
            sender = self.payload["from"]
            message = f'{self.name} from {sender[:6]}... \n' \
                      f'Sender balance: {self.get_balance()} ETH \n' \
                      f'Reason: {self.base_message} \n' \
                      f'Transaction: {self.payload}'
            return message

        def get_balance(self):
            blockchain = BlockchainInterfaceFactory.get_interface()
            balance = blockchain.client.get_balance(account=self.payload['from'])
            return balance

        @property
        def insufficient_eth(self) -> str:
            gas = (self.payload.get('gas', 1) * self.payload['gasPrice'])  # FIXME: If gas is not included...
            cost = gas + self.payload.get('value', 0)
            message = f'{self.payload} from {self.payload["from"][:8]} - {self.base_message}.' \
                      f'Calculated cost is {cost} but sender only has {self.get_balance()}.'
            return message

    def __init__(self,
                 emitter = None,  # TODO # 1754
                 poa: bool = None,
                 light: bool = False,
                 provider_process=NO_PROVIDER_PROCESS,
                 provider_uri: str = NO_BLOCKCHAIN_CONNECTION,
                 provider: Web3Providers = NO_BLOCKCHAIN_CONNECTION,
                 gas_strategy: Union[str, Callable] = DEFAULT_GAS_STRATEGY):

        """
        TODO: #1502 - Move to API docs.

         Filesystem          Configuration           Node              Client                  EVM
        ================ ====================== =============== =====================  ===========================

         Solidity Files -- SolidityCompiler -                      --- HTTPProvider ------ ...
                                            |                    |
                                            |                    |
                                            |                    |
                                            - *BlockchainInterface* -- IPCProvider ----- External EVM (geth, parity...)
                                                       |         |
                                                       |         |
                                                 TestProvider ----- EthereumTester -------------
                                                                                                |
                                                                                                |
                                                                                        PyEVM (Development Chain)

         ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

         Runtime Files --                 --BlockchainInterface ----> Registry
                        |                |             ^
                        |                |             |
                        |                |             |
         Key Files ------ CharacterConfiguration     Agent                          ... (Contract API)
                        |                |             ^
                        |                |             |
                        |                |             |
                        |                |           Actor                          ...Blockchain-Character API)
                        |                |             ^
                        |                |             |
                        |                |             |
         Config File ---                  --------- Character                       ... (Public API)
                                                       ^
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
        self.w3 = NO_BLOCKCHAIN_CONNECTION
        self.client = NO_BLOCKCHAIN_CONNECTION         # type: EthereumClient
        self.transacting_power = READ_ONLY_INTERFACE
        self.is_light = light
        self.gas_strategy = self.get_gas_strategy(gas_strategy)

    def __repr__(self):
        r = '{name}({uri})'.format(name=self.__class__.__name__, uri=self.provider_uri)
        return r

    @classmethod
    def from_dict(cls, payload: dict, **overrides) -> 'BlockchainInterface':
        payload.update({k: v for k, v in overrides.items() if v is not None})
        blockchain = cls(**payload)
        return blockchain

    def to_dict(self) -> dict:
        payload = dict(provider_uri=self.provider_uri, poa=self.poa, light=self.is_light)
        return payload

    @property
    def is_connected(self) -> bool:
        """
        https://web3py.readthedocs.io/en/stable/__provider.html#examples-using-automated-detection
        """
        if self.client is NO_BLOCKCHAIN_CONNECTION:
            return False
        return self.client.is_connected

    @classmethod
    def get_gas_strategy(cls, gas_strategy: Union[str, Callable]) -> Callable:
        try:
            gas_strategy = cls.GAS_STRATEGIES[gas_strategy]
        except KeyError:
            if gas_strategy and not callable(gas_strategy):
                raise ValueError(f"{gas_strategy} must be callable to be a valid gas strategy.")
            else:
                gas_strategy = cls.GAS_STRATEGIES[cls.DEFAULT_GAS_STRATEGY]
        return gas_strategy

    def attach_middleware(self):
        if self.poa is None:  # If POA is not set explicitly, try to autodetect from chain id
            chain_id = int(self.client.chain_id)
            self.poa = chain_id in POA_CHAINS
            self.log.debug(f'Autodetecting POA chain ({self.client.chain_name})')

        # For use with Proof-Of-Authority test-blockchains
        if self.poa is True:
            self.log.debug('Injecting POA middleware at layer 0')
            self.client.inject_middleware(geth_poa_middleware, layer=0)

        # Gas Price Strategy
        self.client.w3.eth.setGasPriceStrategy(self.gas_strategy)
        self.client.w3.middleware_onion.add(middleware.time_based_cache_middleware)
        self.client.w3.middleware_onion.add(middleware.latest_block_based_cache_middleware)
        self.client.w3.middleware_onion.add(middleware.simple_cache_middleware)

    def connect(self):

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

        # Connect if not connected
        try:
            self.w3 = self.Web3(provider=self._provider)
            self.client = EthereumClient.from_w3(w3=self.w3)
        except requests.ConnectionError:  # RPC
            raise self.ConnectionFailed(f'Connection Failed - {str(self.provider_uri)} - is RPC enabled?')
        except FileNotFoundError:         # IPC File Protocol
            raise self.ConnectionFailed(f'Connection Failed - {str(self.provider_uri)} - is IPC enabled?')
        else:
            self.attach_middleware()

        return self.is_connected

    def sync(self, emitter=None) -> None:

        sync_state = self.client.sync()
        if emitter is not None:

            emitter.echo(f"Syncing: {self.client.chain_name.capitalize()}. Waiting for sync to begin.", verbosity=1)

            while not len(self.client.peers):
                emitter.echo("waiting for peers...", verbosity=1)
                time.sleep(5)

            peer_count = len(self.client.peers)
            emitter.echo(
                f"Found {'an' if peer_count == 1 else peer_count} Ethereum peer{('s' if peer_count > 1 else '')}.",
                verbosity=1)

            try:
                emitter.echo("Beginning sync...", verbosity=1)
                initial_state = next(sync_state)
            except StopIteration:  # will occur if no syncing needs to happen
                emitter.echo("Local blockchain data is already synced.", verbosity=1)
                return

            prior_state = initial_state
            total_blocks_to_sync = int(initial_state.get('highestBlock', 0)) - int(
                initial_state.get('currentBlock', 0))
            with click.progressbar(
                    length=total_blocks_to_sync,
                    label="sync progress",
                    file=emitter.get_stream(verbosity=1)
            ) as bar:
                for syncdata in sync_state:
                    if syncdata:
                        blocks_accomplished = int(syncdata['currentBlock']) - int(
                            prior_state.get('currentBlock', 0))
                        bar.update(blocks_accomplished)
                        prior_state = syncdata
        else:
            try:
                for syncdata in sync_state:
                    self.client.log.info(f"Syncing {syncdata['currentBlock']}/{syncdata['highestBlock']}")
            except TypeError:  # it's already synced
                return
        return

    @property
    def provider(self) -> Union[IPCProvider, WebsocketProvider, HTTPProvider]:
        return self._provider

    def _attach_provider(self,
                         provider: Web3Providers = None,
                         provider_uri: str = None) -> None:
        """
        https://web3py.readthedocs.io/en/latest/providers.html#providers
        """

        if not provider_uri and not provider:
            raise self.NoProvider("No URI or provider instances supplied.")

        if provider_uri and not provider:
            uri_breakdown = urlparse(provider_uri)

            if uri_breakdown.scheme == 'tester':
                providers = {
                    'pyevm': _get_pyevm_test_provider,
                    'geth': _get_test_geth_parity_provider,
                    'parity-ethereum': _get_test_geth_parity_provider,
                    'mock': _get_mock_test_provider
                }
                provider_scheme = uri_breakdown.netloc

            else:
                providers = {
                    'auto': _get_auto_provider,
                    'infura': _get_infura_provider,
                    'ipc': _get_IPC_provider,
                    'file': _get_IPC_provider,
                    'ws': _get_websocket_provider,
                    'wss': _get_websocket_provider,
                    'http': _get_HTTP_provider,
                    'https': _get_HTTP_provider,
                }
                provider_scheme = uri_breakdown.scheme

            # auto-detect for file based ipc
            if not provider_scheme:
                if os.path.exists(provider_uri):
                    # file is available - assume ipc/file scheme
                    provider_scheme = 'file'
                    self.log.info(f"Auto-detected provider scheme as 'file://' for provider {provider_uri}")

            try:
                self._provider = providers[provider_scheme](provider_uri)
            except KeyError:
                raise self.UnsupportedProvider(f"{provider_uri} is an invalid or unsupported blockchain provider URI")
            else:
                self.provider_uri = provider_uri or NO_BLOCKCHAIN_CONNECTION
        else:
            self._provider = provider

    def __transaction_failed(self,
                             exception: Exception,
                             transaction_dict: dict,
                             contract_function: Union[ContractFunction, ContractConstructor]
                             ) -> None:
        """
        Re-raising error handler and context manager for transaction broadcast or
        build failure events at the interface layer. This method is a last line of defense
        against unhandled exceptions caused by transaction failures and must raise an exception.
        # TODO: #1504 - Additional Handling of validation failures (gas limits, invalid fields, etc.)
        """

        try:
            # Assume this error is formatted as an IPC response
            code, message = exception.args[0].values()

        except (ValueError, IndexError, AttributeError):
            # TODO: #1504 - Try even harder to determine if this is insufficient funds causing the issue,
            #               This may be best handled at the agent or actor layer for registry and token interactions.
            # Worst case scenario - raise the exception held in context implicitly
            raise exception

        else:
            if int(code) != self.TransactionFailed.IPC_CODE:
                # Only handle client-specific exceptions
                # https://www.jsonrpc.org/specification Section 5.1
                raise exception
            self.log.critical(message)                     # simple context
            transaction_failed = self.TransactionFailed(message=message,  # rich error (best case)
                                                        contract_function=contract_function,
                                                        transaction_dict=transaction_dict)
            raise transaction_failed from exception

    def __log_transaction(self, transaction_dict: dict, contract_function: ContractFunction):
        """
        Format and log a transaction dict and return the transaction name string.
        This method *must not* mutate the original transaction dict.
        """
        # Do not mutate the original transaction dict
        tx = dict(transaction_dict).copy()

        # Format
        if tx.get('to'):
            tx['to'] = to_checksum_address(contract_function.address)
        try:
            tx['selector'] = contract_function.selector
        except AttributeError:
            pass
        tx['from'] = to_checksum_address(tx['from'])
        tx.update({f: prettify_eth_amount(v) for f, v in tx.items() if f in ('gasPrice', 'value')})
        payload_pprint = ', '.join("{}: {}".format(k, v) for k, v in tx.items())

        # Log
        transaction_name = get_transaction_name(contract_function=contract_function)
        self.log.debug(f"[TX-{transaction_name}] | {payload_pprint}")

    @validate_checksum_address
    def build_transaction(self,
                          contract_function: ContractFunction,
                          sender_address: str,
                          payload: dict = None,
                          transaction_gas_limit: int = None,
                          ) -> dict:

        #
        # Build Payload
        #

        base_payload = {'chainId': int(self.client.chain_id),
                        'nonce': self.client.w3.eth.getTransactionCount(sender_address, 'pending'),
                        'from': sender_address,
                        'gasPrice': self.client.gas_price}

        # Aggregate
        if not payload:
            payload = {}
        payload.update(base_payload)
        # Explicit gas override - will skip gas estimation in next operation.
        if transaction_gas_limit:
            payload['gas'] = int(transaction_gas_limit)

        #
        # Build Transaction
        #

        self.__log_transaction(transaction_dict=payload, contract_function=contract_function)
        try:
            transaction_dict = contract_function.buildTransaction(payload)  # Gas estimation occurs here
        except (TestTransactionFailed, ValidationError, ValueError) as error:
            # Note: Geth raises ValueError in the same condition that pyevm raises ValidationError here.
            # Treat this condition as "Transaction Failed" during gas estimation.
            raise self.__transaction_failed(exception=error, transaction_dict=payload, contract_function=contract_function)
        return transaction_dict

    def sign_and_broadcast_transaction(self,
                                       transaction_dict,
                                       transaction_name: str = "",
                                       confirmations: int = 0
                                       ) -> dict:

        #
        # Setup
        #

        # TODO # 1754 - Move this to singleton - I do not approve... nor does Bogdan?
        if GlobalLoggerSettings._json_ipc:
            emitter = JSONRPCStdoutEmitter()
        else:
            emitter = StdoutEmitter()

        if self.transacting_power is READ_ONLY_INTERFACE:
            raise self.InterfaceError(str(READ_ONLY_INTERFACE))

        #
        # Sign
        #

        # TODO: Show the USD Price:  https://api.coinmarketcap.com/v1/ticker/ethereum/
        price = transaction_dict['gasPrice']
        cost_wei = price * transaction_dict['gas']
        cost = Web3.fromWei(cost_wei, 'gwei')
        if self.transacting_power.is_device:
            emitter.message(f'Confirm transaction {transaction_name} on hardware wallet... ({cost} gwei @ {price})', color='yellow')
        signed_raw_transaction = self.transacting_power.sign_transaction(transaction_dict)

        #
        # Broadcast
        #

        emitter.message(f'Broadcasting {transaction_name} Transaction ({cost} gwei @ {price})...', color='yellow')
        try:
            txhash = self.client.send_raw_transaction(signed_raw_transaction)  # <--- BROADCAST
        except (TestTransactionFailed, ValueError) as error:
            raise  # TODO: Unify with Transaction failed handling

        #
        # Receipt
        #

        try:  # TODO: Handle block confirmation exceptions
            receipt = self.client.wait_for_receipt(txhash, timeout=self.TIMEOUT, confirmations=confirmations)
        except TimeExhausted:
            # TODO: #1504 - Handle transaction timeout
            raise
        else:
            self.log.debug(f"[RECEIPT-{transaction_name}] | txhash: {receipt['transactionHash'].hex()}")

        #
        # Confirmations
        #

        # Primary check
        transaction_status = receipt.get('status', UNKNOWN_TX_STATUS)
        if transaction_status == 0:
            failure = f"Transaction transmitted, but receipt returned status code 0. " \
                      f"Full receipt: \n {pprint.pformat(receipt, indent=2)}"
            raise self.InterfaceError(failure)

        if transaction_status is UNKNOWN_TX_STATUS:
            self.log.info(f"Unknown transaction status for {txhash} (receipt did not contain a status field)")

            # Secondary check
            tx = self.client.get_transaction(txhash)
            if tx["gas"] == receipt["gasUsed"]:
                raise self.InterfaceError(f"Transaction consumed 100% of transaction gas."
                                          f"Full receipt: \n {pprint.pformat(receipt, indent=2)}")

        return receipt

    def get_blocktime(self):
        return self.client.get_blocktime()

    @validate_checksum_address
    def send_transaction(self,
                         contract_function: Union[ContractFunction, ContractConstructor],
                         sender_address: str,
                         payload: dict = None,
                         transaction_gas_limit: int = None,
                         confirmations: int = 0
                         ) -> dict:

        transaction = self.build_transaction(contract_function=contract_function,
                                             sender_address=sender_address,
                                             payload=payload,
                                             transaction_gas_limit=transaction_gas_limit)

        # Get transaction name
        try:
            transaction_name = contract_function.fn_name.upper()
        except AttributeError:
            transaction_name = 'DEPLOY' if isinstance(contract_function, ContractConstructor) else 'UNKNOWN'

        receipt = self.sign_and_broadcast_transaction(transaction_dict=transaction,
                                                      transaction_name=transaction_name,
                                                      confirmations=confirmations)
        return receipt

    def get_contract_by_name(self,
                             registry: BaseContractRegistry,
                             contract_name: str,
                             contract_version: str = None,
                             enrollment_version: Union[int, str] = None,
                             proxy_name: str = None,
                             use_proxy_address: bool = True
                             ) -> VersionedContract:
        """
        Instantiate a deployed contract from registry data,
        and assimilate it with its proxy if it is upgradeable.
        """
        target_contract_records = registry.search(contract_name=contract_name, contract_version=contract_version)

        if not target_contract_records:
            raise self.UnknownContract(f"No such contract records with name {contract_name}:{contract_version}.")

        if proxy_name:

            # Lookup proxies; Search for a published proxy that targets this contract record
            proxy_records = registry.search(contract_name=proxy_name)

            results = list()
            for proxy_name, proxy_version, proxy_address, proxy_abi in proxy_records:
                proxy_contract = self.client.w3.eth.contract(abi=proxy_abi,
                                                             address=proxy_address,
                                                             version=proxy_version,
                                                             ContractFactoryClass=self._contract_factory)

                # Read this dispatcher's target address from the blockchain
                proxy_live_target_address = proxy_contract.functions.target().call()
                for target_name, target_version, target_address, target_abi in target_contract_records:

                    if target_address == proxy_live_target_address:
                        if use_proxy_address:
                            triplet = (proxy_address, target_version, target_abi)
                        else:
                            triplet = (target_address, target_version, target_abi)
                    else:
                        continue

                    results.append(triplet)

            if len(results) > 1:
                address, _version, _abi = results[0]
                message = "Multiple {} deployments are targeting {}".format(proxy_name, address)
                raise self.InterfaceError(message.format(contract_name))

            else:
                try:
                    selected_address, selected_version, selected_abi = results[0]
                except IndexError:
                    raise self.UnknownContract(
                        f"There are no Dispatcher records targeting '{contract_name}':{contract_version}")

        else:
            # TODO: use_proxy_address doesnt' work in this case. Should we raise if used?

            # NOTE: 0 must be allowed as a valid version number
            if len(target_contract_records) != 1:
                if enrollment_version is None:
                    m = f"{len(target_contract_records)} records enrolled " \
                        f"for contract {contract_name}:{contract_version} " \
                        f"and no version index was supplied."
                    raise self.InterfaceError(m)
                enrollment_version = self.__get_enrollment_version_index(name=contract_name,
                                                                         contract_version=contract_version,
                                                                         version_index=enrollment_version,
                                                                         enrollments=len(target_contract_records))

            else:
                enrollment_version = -1  # default

            _contract_name, selected_version, selected_address, selected_abi = target_contract_records[enrollment_version]

        # Create the contract from selected sources
        unified_contract = self.client.w3.eth.contract(abi=selected_abi,
                                                       address=selected_address,
                                                       version=selected_version,
                                                       ContractFactoryClass=self._contract_factory)

        return unified_contract

    @staticmethod
    def __get_enrollment_version_index(version_index: Union[int, str],
                                       enrollments: int,
                                       name: str,
                                       contract_version: str):
        version_names = {'latest': -1, 'earliest': 0}
        try:
            version = version_names[version_index]
        except KeyError:
            try:
                version = int(version_index)
            except ValueError:
                what_is_this = version_index
                raise ValueError(f"'{what_is_this}' is not a valid enrollment version number")
            else:
                if version > enrollments - 1:
                    message = f"Version index '{version}' is larger than the number of enrollments " \
                              f"for {name}:{contract_version}."
                    raise ValueError(message)
        return version


class BlockchainDeployerInterface(BlockchainInterface):

    TIMEOUT = 600  # seconds
    _contract_factory = VersionedContract

    class NoDeployerAddress(RuntimeError):
        pass

    class DeploymentFailed(RuntimeError):
        pass

    def __init__(self,
                 compiler: SolidityCompiler = None,
                 ignore_solidity_check: bool = False,
                 dry_run: bool = False,
                 *args, **kwargs):

        super().__init__(*args, **kwargs)
        self.dry_run = dry_run
        self.compiler = compiler or SolidityCompiler(ignore_solidity_check=ignore_solidity_check)

    def connect(self):
        super().connect()
        self._setup_solidity(compiler=self.compiler)
        return self.is_connected

    def _setup_solidity(self, compiler: SolidityCompiler = None) -> None:
        if self.dry_run:
            self.log.info("Dry run is active, skipping solidity compile steps.")
            return
        if compiler:
            # Execute the compilation if we're recompiling
            # Otherwise read compiled contract data from the registry.
            _raw_contract_cache = compiler.compile()
        else:
            _raw_contract_cache = NO_COMPILATION_PERFORMED
        self._raw_contract_cache = _raw_contract_cache

    @validate_checksum_address
    def deploy_contract(self,
                        deployer_address: str,
                        registry: BaseContractRegistry,
                        contract_name: str,
                        *constructor_args,
                        enroll: bool = True,
                        gas_limit: int = None,
                        confirmations: int = 0,
                        contract_version: str = 'latest',
                        **constructor_kwargs
                        ) -> Tuple[VersionedContract, dict]:
        """
        Retrieve compiled interface data from the cache and
        return an instantiated deployed contract
        """

        #
        # Build the deployment transaction #
        #

        deploy_transaction = dict()
        if gas_limit:
            deploy_transaction.update({'gas': gas_limit})

        pprint_args = ', '.join(list(map(str, constructor_args)) + list(f"{k}={v}" for k, v in constructor_kwargs.items()))

        contract_factory = self.get_contract_factory(contract_name=contract_name, version=contract_version)
        self.log.info(f"Deploying contract {contract_name}:{contract_factory.version} with "
                      f"deployer address {deployer_address} "
                      f"and parameters {pprint_args}")

        transaction_function = contract_factory.constructor(*constructor_args, **constructor_kwargs)

        #
        # Transmit the deployment tx #
        #

        receipt = self.send_transaction(contract_function=transaction_function,
                                        sender_address=deployer_address,
                                        payload=deploy_transaction,
                                        confirmations=confirmations)

        # Success
        address = receipt['contractAddress']
        self.log.info(f"Confirmed {contract_name}:{contract_factory.version} deployment: new address {address}")

        #
        # Instantiate & Enroll contract
        #

        contract = self.client.w3.eth.contract(address=address,
                                               abi=contract_factory.abi,
                                               version=contract_factory.version,
                                               ContractFactoryClass=self._contract_factory)

        if enroll is True:
            registry.enroll(contract_name=contract_name,
                            contract_address=contract.address,
                            contract_abi=contract.abi,
                            contract_version=contract.version)

        return contract, receipt  # receipt

    def find_raw_contract_data(self, contract_name: str, requested_version: str = 'latest') -> Tuple[str, dict]:
        try:
            contract_data = self._raw_contract_cache[contract_name]
        except KeyError:
            raise self.UnknownContract('{} is not a locally compiled contract.'.format(contract_name))
        except TypeError:
            if self._raw_contract_cache is NO_COMPILATION_PERFORMED:
                message = "The local contract compiler cache is empty because no compilation was performed."
                raise self.InterfaceError(message)
            raise

        try:
            return requested_version, contract_data[requested_version]
        except KeyError:
            if requested_version != 'latest' and requested_version != 'earliest':
                raise self.UnknownContract('Version {} of contract {} is not a locally compiled. '
                                           'Available versions: {}'
                                           .format(requested_version, contract_name, contract_data.keys()))

        if len(contract_data.keys()) == 1:
            return next(iter(contract_data.items()))

        # Get the latest or the earliest versions
        current_version_parsed = (-1, -1, -1)
        current_version = None
        current_data = None
        for version, data in contract_data.items():
            major, minor, patch = [int(v) for v in version[1:].split(".", 3)]
            if current_version_parsed[0] == -1 or \
               requested_version == 'latest' and (major, minor, patch) > current_version_parsed or \
               requested_version == 'earliest' and (major, minor, patch) < current_version_parsed:
                current_version_parsed = (major, minor, patch)
                current_data = data
                current_version = version
        return current_version, current_data

    def get_contract_factory(self, contract_name: str, version: str = 'latest') -> VersionedContract:
        """Retrieve compiled interface data from the cache and return web3 contract"""
        version, interface = self.find_raw_contract_data(contract_name, version)
        contract = self.client.w3.eth.contract(abi=interface['abi'],
                                               bytecode=interface['bin'],
                                               version=version,
                                               ContractFactoryClass=self._contract_factory)
        return contract

    def _wrap_contract(self,
                       wrapper_contract: VersionedContract,
                       target_contract: VersionedContract
                       ) -> VersionedContract:
        """
        Used for upgradeable contracts; Returns a new contract object assembled
        with its own address but the abi of the other.
        """

        # Wrap the contract
        wrapped_contract = self.client.w3.eth.contract(abi=target_contract.abi,
                                                       address=wrapper_contract.address,
                                                       version=target_contract.version,
                                                       ContractFactoryClass=self._contract_factory)
        return wrapped_contract

    @validate_checksum_address
    def get_proxy_contract(self,
                           registry: BaseContractRegistry,
                           target_address: str,
                           proxy_name: str) -> VersionedContract:

        # Lookup proxies; Search for a registered proxy that targets this contract record
        records = registry.search(contract_name=proxy_name)

        dispatchers = list()
        for name, version, address, abi in records:
            proxy_contract = self.client.w3.eth.contract(abi=abi,
                                                         address=address,
                                                         version=version,
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


Interfaces = Union[BlockchainInterface, BlockchainDeployerInterface]


class BlockchainInterfaceFactory:
    """
    Canonical source of bound blockchain interfaces.
    """

    _instance = None
    _interfaces = dict()
    _default_interface_class = BlockchainInterface

    class CachedInterface(NamedTuple):
        interface: BlockchainInterface
        sync: bool
        emitter: StdoutEmitter

    class FactoryError(Exception):
        pass

    class NoRegisteredInterfaces(FactoryError):
        pass

    class InterfaceNotInitialized(FactoryError):
        pass

    class InterfaceAlreadyInitialized(FactoryError):
        pass

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super().__new__(cls, *args, **kwargs)
        return cls._instance

    @classmethod
    def is_interface_initialized(cls, provider_uri: str) -> bool:
        """
        Returns True if there is an existing connection with an equal provider_uri.
        """
        return bool(cls._interfaces.get(provider_uri, False))

    @classmethod
    def register_interface(cls,
                           interface: BlockchainInterface,
                           sync: bool = False,
                           emitter=None,
                           force: bool = False
                           ) -> None:

        provider_uri = interface.provider_uri
        if (provider_uri in cls._interfaces) and not force:
            raise cls.InterfaceAlreadyInitialized(f"A connection already exists for {provider_uri}. "
                                                  "Use .get_interface instead.")
        cached = cls.CachedInterface(interface=interface, sync=sync, emitter=emitter)
        cls._interfaces[provider_uri] = cached

    @classmethod
    def initialize_interface(cls,
                             provider_uri: str,
                             sync: bool = False,
                             emitter=None,
                             interface_class: Interfaces = None,
                             *interface_args,
                             **interface_kwargs
                             ) -> None:
        if not provider_uri:
            # Prevent empty strings and Falsy
            raise BlockchainInterface.UnsupportedProvider(f"'{provider_uri}' is not a valid provider URI")

        if provider_uri in cls._interfaces:
            raise cls.InterfaceAlreadyInitialized(f"A connection already exists for {provider_uri}.  "
                                                  f"Use .get_interface instead.")

        # Interface does not exist, initialize a new one.
        if not interface_class:
            interface_class = cls._default_interface_class
        interface = interface_class(provider_uri=provider_uri,
                                    *interface_args,
                                    **interface_kwargs)

        cls._interfaces[provider_uri] = cls.CachedInterface(interface=interface, sync=sync,  emitter=emitter)

    @classmethod
    def get_interface(cls, provider_uri: str = None) -> Interfaces:

        # Try to get an existing cached interface.
        if provider_uri:
            try:
                cached_interface = cls._interfaces[provider_uri]
            except KeyError:
                raise cls.InterfaceNotInitialized(f"There is no connection for {provider_uri}. "
                                                  f"Call .initialize_connection, then try again.")

        # Try to use the most recently created interface by default.
        else:
            try:
                cached_interface = list(cls._interfaces.values())[-1]
            except IndexError:
                raise cls.NoRegisteredInterfaces(f"There is no existing blockchain connection.")

        # Connect and Sync
        interface, sync, emitter = cached_interface
        if not interface.is_connected:
            interface.connect()
            if sync:
                interface.sync(emitter=emitter)
        return interface

    @classmethod
    def get_or_create_interface(cls,
                                provider_uri: str,
                                *interface_args,
                                **interface_kwargs
                                ) -> BlockchainInterface:
        try:
            interface = cls.get_interface(provider_uri=provider_uri)
        except (cls.InterfaceNotInitialized, cls.NoRegisteredInterfaces):
            cls.initialize_interface(provider_uri=provider_uri, *interface_args, **interface_kwargs)
            interface = cls.get_interface(provider_uri=provider_uri)
        return interface
