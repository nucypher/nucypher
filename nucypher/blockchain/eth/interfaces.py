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


import collections
import os
import pprint
import time
from typing import List
from typing import Tuple
from typing import Union
from urllib.parse import urlparse

import requests
from constant_sorrow.constants import (
    NO_BLOCKCHAIN_CONNECTION,
    NO_COMPILATION_PERFORMED,
    UNKNOWN_TX_STATUS,
    NO_PROVIDER_PROCESS,
    READ_ONLY_INTERFACE
)
from eth_tester import EthereumTester
from eth_utils import to_checksum_address, is_checksum_address
from twisted.logger import Logger
from web3 import Web3, WebsocketProvider, HTTPProvider, IPCProvider
from web3.contract import Contract
from web3.contract import ContractConstructor
from web3.contract import ContractFunction
from web3.exceptions import TimeExhausted
from web3.exceptions import ValidationError
from web3.middleware import geth_poa_middleware

from nucypher.blockchain.eth.clients import NuCypherGethProcess
from nucypher.blockchain.eth.clients import Web3Client
from nucypher.blockchain.eth.providers import (
    _get_tester_pyevm,
    _get_test_geth_parity_provider,
    _get_auto_provider,
    _get_infura_provider,
    _get_IPC_provider,
    _get_websocket_provider,
    _get_HTTP_provider
)
from nucypher.blockchain.eth.registry import BaseContractRegistry
from nucypher.blockchain.eth.sol.compile import SolidityCompiler
from nucypher.characters.control.emitters import StdoutEmitter
from nucypher.utilities.logging import console_observer, GlobalLoggerSettings

Web3Providers = Union[IPCProvider, WebsocketProvider, HTTPProvider, EthereumTester]


class BlockchainInterface:
    """
    Interacts with a solidity compiler and a registry in order to instantiate compiled
    ethereum contracts with the given web3 provider backend.
    """

    TIMEOUT = 180  # seconds
    NULL_ADDRESS = '0x' + '0' * 40

    process = NO_PROVIDER_PROCESS.bool_value(False)
    Web3 = Web3

    _contract_factory = Contract

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

    def __init__(self,
                 poa: bool = True,
                 provider_process: NuCypherGethProcess = NO_PROVIDER_PROCESS,
                 provider_uri: str = NO_BLOCKCHAIN_CONNECTION,
                 provider: Web3Providers = NO_BLOCKCHAIN_CONNECTION):

        """
        A blockchain "network interface"; The circumflex wraps entirely around the bounds of
        contract operations including compilation, deployment, and execution.

        TODO: Move me to docs.

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
        self.client = NO_BLOCKCHAIN_CONNECTION
        self.transacting_power = READ_ONLY_INTERFACE

    def __repr__(self):
        r = '{name}({uri})'.format(name=self.__class__.__name__, uri=self.provider_uri)
        return r

    @classmethod
    def from_dict(cls, payload: dict, **overrides) -> 'BlockchainInterface':
        payload.update({k: v for k, v in overrides.items() if v is not None})
        blockchain = cls(**payload)
        return blockchain

    def to_dict(self) -> dict:
        payload = dict(provider_uri=self.provider_uri, poa=self.poa)
        return payload

    @property
    def is_connected(self) -> bool:
        """
        https://web3py.readthedocs.io/en/stable/__provider.html#examples-using-automated-detection
        """
        if self.client is NO_BLOCKCHAIN_CONNECTION:
            return False
        return self.client.is_connected

    def attach_middleware(self):

        # For use with Proof-Of-Authority test-blockchains
        if self.poa is True:
            self.log.debug('Injecting POA middleware at layer 0')
            self.client.inject_middleware(geth_poa_middleware, layer=0)

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
            self.client = Web3Client.from_w3(w3=self.w3)
        except requests.ConnectionError:  # RPC
            raise self.ConnectionFailed(f'Connection Failed - {str(self.provider_uri)} - is RPC enabled?')
        except FileNotFoundError:         # IPC File Protocol
            raise self.ConnectionFailed(f'Connection Failed - {str(self.provider_uri)} - is IPC enabled?')
        else:
            self.attach_middleware()

        return self.is_connected

    def sync(self, show_progress: bool = False) -> None:

        sync_state = self.client.sync()
        if show_progress:
            import click
            # TODO: It is possible that output has been redirected from a higher-level emitter.
            # TODO: Use console logging instead of StdOutEmitter here.
            emitter = StdoutEmitter()

            emitter.echo(f"Syncing: {self.client.chain_name.capitalize()}. Waiting for sync to begin.")

            while not len(self.client.peers):
                emitter.echo("waiting for peers...")
                time.sleep(5)

            peer_count = len(self.client.peers)
            emitter.echo(
                f"Found {'an' if peer_count == 1 else peer_count} Ethereum peer{('s' if peer_count > 1 else '')}.")

            try:
                emitter.echo("Beginning sync...")
                initial_state = next(sync_state)
            except StopIteration:  # will occur if no syncing needs to happen
                emitter.echo("Local blockchain data is already synced.")
                return

            prior_state = initial_state
            total_blocks_to_sync = int(initial_state.get('highestBlock', 0)) - int(
                initial_state.get('currentBlock', 0))
            with click.progressbar(
                    length=total_blocks_to_sync,
                    label="sync progress"
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

    def send_transaction(self,
                         contract_function: ContractFunction,
                         sender_address: str,
                         payload: dict = None,
                         transaction_gas_limit: int = None,
                         ) -> dict:

        if self.transacting_power is READ_ONLY_INTERFACE:
            raise self.InterfaceError(str(READ_ONLY_INTERFACE))

        #
        # Build
        #

        if not payload:
            payload = {}

        nonce = self.client.w3.eth.getTransactionCount(sender_address)
        payload.update({'chainId': int(self.client.chain_id),
                        'nonce': nonce,
                        'from': sender_address,
                        'gasPrice': self.client.gas_price})

        if transaction_gas_limit:
            payload['gas'] = int(transaction_gas_limit)

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
        except (ValidationError, ValueError) as e:
            # TODO: Handle validation failures for gas limits, invalid fields, etc.
            # Note: Geth raises ValueError in the same condition that pyevm raises ValidationError here.
            # Treat this condition as "Transaction Failed".
            self.log.critical(f"Validation error: {e}")
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
                             registry: BaseContractRegistry,
                             name: str,
                             version: int = None,
                             proxy_name: str = None,
                             use_proxy_address: bool = True
                             ) -> Union[Contract, List[tuple]]:
        """
        Instantiate a deployed contract from registry data,
        and assimilate it with its proxy if it is upgradeable,
        or return all registered records if use_proxy_address is False.
        """
        target_contract_records = registry.search(contract_name=name)

        if not target_contract_records:
            raise self.UnknownContract(f"No such contract records with name {name}.")

        if proxy_name:

            # Lookup proxies; Search for a published proxy that targets this contract record
            proxy_records = registry.search(contract_name=proxy_name)

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
                            pair = (target_addr, target_abi)
                    else:
                        continue

                    results.append(pair)

            if len(results) > 1:
                address, abi = results[0]
                message = "Multiple {} deployments are targeting {}".format(proxy_name, address)
                raise self.InterfaceError(message.format(name))

            else:
                try:
                    selected_address, selected_abi = results[0]
                except IndexError:
                    raise self.UnknownContract(f"There are no Dispatcher records targeting '{name}'")

        else:
            # NOTE: 0 must be allowed as a valid version number
            if len(target_contract_records) != 1:
                if version is None:
                    m = f"{len(target_contract_records)} records enrolled for contract {name} " \
                        f"and no version index was supplied."
                    raise self.InterfaceError(m)
                version = self.__get_version_index(name=name,
                                                   version_index=version,
                                                   enrollments=len(target_contract_records))

            else:
                version = -1  # default

            _target_contract_name, selected_address, selected_abi = target_contract_records[version]

        # Create the contract from selected sources
        unified_contract = self.client.w3.eth.contract(abi=selected_abi,
                                                       address=selected_address,
                                                       ContractFactoryClass=self._contract_factory)

        return unified_contract

    @staticmethod
    def __get_version_index(version_index: Union[int, str], enrollments: int, name: str):
        version_names = {'latest': -1, 'earliest': 0}
        try:
            version = version_names[version_index]
        except KeyError:
            try:
                version = int(version_index)
            except ValueError:
                what_is_this = version_index
                raise ValueError(f"'{what_is_this}' is not a valid version number")
            else:
                if version > enrollments - 1:
                    message = f"Version index '{version}' is larger than the number of enrollments for {name}."
                    raise ValueError(message)
        return version


class BlockchainDeployerInterface(BlockchainInterface):

    TIMEOUT = 600  # seconds
    _contract_factory = Contract

    class NoDeployerAddress(RuntimeError):
        pass

    class DeploymentFailed(RuntimeError):
        pass

    def __init__(self, compiler: SolidityCompiler = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.compiler = compiler or SolidityCompiler()

    def connect(self):
        super().connect()
        self._setup_solidity(compiler=self.compiler)
        return self.is_connected

    def _setup_solidity(self, compiler: SolidityCompiler = None):

        # if a SolidityCompiler class instance was passed,
        # compile from solidity source code.
        self.__sol_compiler = compiler
        if compiler:
            # Execute the compilation if we're recompiling
            # Otherwise read compiled contract data from the registry.
            interfaces = self.__sol_compiler.compile()
            __raw_contract_cache = interfaces
        else:
            __raw_contract_cache = NO_COMPILATION_PERFORMED
        self.__raw_contract_cache = __raw_contract_cache

    def deploy_contract(self,
                        deployer_address: str,
                        registry: BaseContractRegistry,
                        contract_name: str,
                        *constructor_args,
                        enroll: bool = True,
                        gas_limit: int = None,
                        **constructor_kwargs
                        ) -> Tuple[Contract, dict]:
        """
        Retrieve compiled interface data from the cache and
        return an instantiated deployed contract
        """

        if not is_checksum_address(deployer_address):
            raise ValueError(f"{deployer_address} is not a valid EIP-55 checksum address.")

        #
        # Build the deployment transaction #
        #

        deploy_transaction = dict()
        if gas_limit:
            deploy_transaction.update({'gas': gas_limit})

        pprint_args = str(tuple(constructor_args))
        pprint_args = pprint_args.replace("{", "{{").replace("}", "}}")  # See #724
        self.log.info(f"Deploying contract {contract_name} with "
                      f"deployer address {deployer_address} "
                      f"and parameters {pprint_args}")

        contract_factory = self.get_contract_factory(contract_name=contract_name)
        transaction_function = contract_factory.constructor(*constructor_args, **constructor_kwargs)

        #
        # Transmit the deployment tx #
        #

        receipt = self.send_transaction(contract_function=transaction_function,
                                        sender_address=deployer_address,
                                        payload=deploy_transaction)

        #
        # Verify deployment success
        #

        # Success
        address = receipt['contractAddress']
        self.log.info(f"Confirmed {contract_name} deployment: new address {address}")

        #
        # Instantiate & Enroll contract
        #

        contract = self.client.w3.eth.contract(address=address, abi=contract_factory.abi)

        if enroll is True:
            registry.enroll(contract_name=contract_name,
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

    def get_proxy_contract(self,
                           registry: BaseContractRegistry,
                           target_address: str,
                           proxy_name: str) -> Contract:

        # Lookup proxies; Search for a registered proxy that targets this contract record
        records = registry.search(contract_name=proxy_name)

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


Interfaces = Union[BlockchainInterface, BlockchainDeployerInterface]


class BlockchainInterfaceFactory:
    """
    Canonical source of bound blockchain interfaces.
    """

    _instance = None
    _interfaces = dict()
    _default_interface_class = BlockchainInterface

    CachedInterface = collections.namedtuple('CachedInterface', ['interface',    # type: BlockchainInterface
                                                                 'sync',
                                                                 'show_sync_progress'])

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
                           show_sync_progress: bool = False
                           ) -> None:

        provider_uri = interface.provider_uri
        if provider_uri in cls._interfaces:
            raise cls.InterfaceAlreadyInitialized(f"A connection already exists for {provider_uri}. "
                                                  "Use .get_interface instead.")
        cached = cls.CachedInterface(interface=interface, sync=sync, show_sync_progress=show_sync_progress)
        cls._interfaces[provider_uri] = cached

    @classmethod
    def initialize_interface(cls,
                             provider_uri: str,
                             sync: bool = False,
                             show_sync_progress: bool = False,
                             interface_class: Interfaces = None,
                             *interface_args,
                             **interface_kwargs
                             ) -> None:

        if provider_uri in cls._interfaces:
            raise cls.InterfaceAlreadyInitialized(f"A connection already exists for {provider_uri}.  "
                                                  f"Use .get_interface instead.")

        # Interface does not exist, initialize a new one.
        if not interface_class:
            interface_class = cls._default_interface_class
        interface = interface_class(provider_uri=provider_uri, *interface_args, **interface_kwargs)
        cls._interfaces[provider_uri] = cls.CachedInterface(interface=interface,
                                                            sync=sync,
                                                            show_sync_progress=show_sync_progress)

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
        interface, sync, show_sync_progress = cached_interface
        if not interface.is_connected:
            interface.connect()
            if sync:
                interface.sync(show_progress=show_sync_progress)
        return interface

    @classmethod
    def get_or_create_interface(cls, provider_uri: str) -> BlockchainInterface:
        try:
            interface = cls.get_interface(provider_uri=provider_uri)
        except (cls.InterfaceNotInitialized, cls.NoRegisteredInterfaces):
            cls.initialize_interface(provider_uri=provider_uri)
            interface = cls.get_interface(provider_uri=provider_uri)
        return interface
