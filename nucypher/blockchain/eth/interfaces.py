import math
import pprint
from pathlib import Path
from typing import Callable, NamedTuple, Optional, Union
from urllib.parse import urlparse

import requests
from constant_sorrow.constants import (
    INSUFFICIENT_FUNDS,
    NO_BLOCKCHAIN_CONNECTION,
    UNKNOWN_TX_STATUS,
)
from eth.typing import TransactionDict
from eth_tester import EthereumTester
from eth_tester.exceptions import (
    TransactionFailed as TestTransactionFailed,
)
from eth_tester.exceptions import (
    ValidationError,
)
from eth_utils import to_checksum_address
from hexbytes.main import HexBytes
from web3 import HTTPProvider, IPCProvider, Web3, WebsocketProvider
from web3.contract.contract import Contract, ContractConstructor, ContractFunction
from web3.exceptions import TimeExhausted
from web3.middleware import geth_poa_middleware
from web3.providers import BaseProvider
from web3.types import TxReceipt

from nucypher.blockchain.eth.clients import POA_CHAINS, EthereumClient, InfuraClient
from nucypher.blockchain.eth.decorators import validate_checksum_address
from nucypher.blockchain.eth.providers import (
    _get_auto_provider,
    _get_HTTP_provider,
    _get_IPC_provider,
    _get_mock_test_provider,
    _get_pyevm_test_provider,
    _get_websocket_provider,
)
from nucypher.blockchain.eth.registry import ContractRegistry
from nucypher.blockchain.eth.utils import get_transaction_name, prettify_eth_amount
from nucypher.crypto.powers import TransactingPower
from nucypher.utilities.emitters import StdoutEmitter
from nucypher.utilities.gas_strategies import (
    WEB3_GAS_STRATEGIES,
    construct_datafeed_median_strategy,
    max_price_gas_strategy_wrapper,
)
from nucypher.utilities.logging import Logger

Web3Providers = Union[IPCProvider, WebsocketProvider, HTTPProvider, EthereumTester]  # TODO: Move to types.py


class BlockchainInterface:
    """
    Interacts with a solidity compiler and a registry in order to instantiate compiled
    ethereum contracts with the given web3 provider backend.
    """

    TIMEOUT = 600  # seconds  # TODO: Correlate with the gas strategy - #2070

    DEFAULT_GAS_STRATEGY = 'fast'
    GAS_STRATEGIES = WEB3_GAS_STRATEGIES

    Web3 = Web3  # TODO: This is name-shadowing the actual Web3. Is this intentional?

    _CONTRACT_FACTORY = Contract

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
        INSUFFICIENT_FUNDS: "insufficient funds for gas * price + value",
    }

    class TransactionFailed(InterfaceError):

        IPC_CODE = -32000

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
                BlockchainInterface.REASONS[INSUFFICIENT_FUNDS]: self.insufficient_funds
            }
            self.message = self.failures.get(self.base_message, self.default)
            super().__init__(self.message, *args)

        @property
        def default(self) -> str:
            sender = self.payload["from"]
            message = f'{self.name} from {sender[:6]}... \n' \
                      f'Sender balance: {prettify_eth_amount(self.get_balance())} \n' \
                      f'Reason: {self.base_message} \n' \
                      f'Transaction: {self.payload}'
            return message

        def get_balance(self):
            blockchain = BlockchainInterfaceFactory.get_interface()
            balance = blockchain.client.get_balance(account=self.payload['from'])
            return balance

        @property
        def insufficient_funds(self) -> str:
            try:
                transaction_fee = self.payload['gas'] * self.payload['gasPrice']
            except KeyError:
                return self.default
            else:
                cost = transaction_fee + self.payload.get('value', 0)
                message = f'{self.name} from {self.payload["from"][:8]} - {self.base_message}.' \
                          f'Calculated cost is {prettify_eth_amount(cost)},' \
                          f'but sender only has {prettify_eth_amount(self.get_balance())}.'
            return message

    def __init__(
        self,
        emitter=None,  # TODO # 1754
        poa: bool = None,
        light: bool = False,
        blockchain_endpoint: str = NO_BLOCKCHAIN_CONNECTION,
        blockchain_provider: BaseProvider = NO_BLOCKCHAIN_CONNECTION,
        gas_strategy: Optional[Union[str, Callable]] = None,
        max_gas_price: Optional[int] = None,
    ):
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
        self.blockchain_endpoint = blockchain_endpoint
        self._blockchain_provider = blockchain_provider
        self.w3 = NO_BLOCKCHAIN_CONNECTION
        self.client = NO_BLOCKCHAIN_CONNECTION
        self.is_light = light

        # TODO: Not ready to give users total flexibility. Let's stick for the moment to known values. See #2447
        if gas_strategy not in ('slow', 'medium', 'fast', 'free', None):  # FIXME: What is 'None' doing here?
            raise ValueError(f"'{gas_strategy}' is an invalid gas strategy")
        self.gas_strategy = gas_strategy or self.DEFAULT_GAS_STRATEGY
        self.max_gas_price = max_gas_price

    def __repr__(self):
        r = "{name}({uri})".format(
            name=self.__class__.__name__, uri=self.blockchain_endpoint
        )
        return r

    def get_blocktime(self):
        return self.client.get_blocktime()

    @property
    def is_connected(self) -> bool:
        """
        https://web3py.readthedocs.io/en/stable/__provider.html#examples-using-automated-detection
        """
        if self.client is NO_BLOCKCHAIN_CONNECTION:
            return False
        return self.client.is_connected

    @classmethod
    def get_gas_strategy(cls, gas_strategy: Union[str, Callable] = None) -> Callable:
        try:
            gas_strategy = cls.GAS_STRATEGIES[gas_strategy]
        except KeyError:
            if gas_strategy:
                if not callable(gas_strategy):
                    raise ValueError(f"{gas_strategy} must be callable to be a valid gas strategy.")
            else:
                gas_strategy = cls.GAS_STRATEGIES[cls.DEFAULT_GAS_STRATEGY]
        return gas_strategy

    def attach_middleware(self):
        chain_id = int(self.client.chain_id)
        self.poa = chain_id in POA_CHAINS

        self.log.debug(
            f"Blockchain: {self.client.chain_name} (chain_id={chain_id}, poa={self.poa})"
        )

        # For use with Proof-Of-Authority test-blockchains
        if self.poa is True:
            self.log.debug('Injecting POA middleware at layer 0')
            self.client.inject_middleware(geth_poa_middleware, layer=0)

        self.configure_gas_strategy()

    def configure_gas_strategy(self, gas_strategy: Optional[Callable] = None) -> None:

        if gas_strategy:
            reported_gas_strategy = f"fixed/{gas_strategy.name}"

        elif isinstance(self.client, InfuraClient):
            gas_strategy = construct_datafeed_median_strategy(speed=self.gas_strategy)
            reported_gas_strategy = f"datafeed/{self.gas_strategy}"

        else:
            reported_gas_strategy = f"web3/{self.gas_strategy}"
            gas_strategy = self.get_gas_strategy(self.gas_strategy)

        configuration_message = f"Using gas strategy '{reported_gas_strategy}'"

        if self.max_gas_price:
            __price = Web3.to_wei(self.max_gas_price, 'gwei')  # from gwei to wei
            gas_strategy = max_price_gas_strategy_wrapper(gas_strategy=gas_strategy, max_gas_price_wei=__price)
            configuration_message += f", with a max price of {self.max_gas_price} gwei."

        self.client.set_gas_strategy(gas_strategy=gas_strategy)

        # TODO: This line must not be called prior to establishing a connection
        #        Move it down to a lower layer, near the client.
        # gwei_gas_price = Web3.from_wei(self.client.gas_price_for_transaction(), 'gwei')

        self.log.info(configuration_message)
        # self.log.debug(f"Gas strategy currently reports a gas price of {gwei_gas_price} gwei.")

    def connect(self):

        blockchain_endpoint = self.blockchain_endpoint
        self.log.info(f"Using external Web3 Provider '{self.blockchain_endpoint}'")

        # Attach Provider
        self._attach_blockchain_provider(
            blockchain_provider=self._blockchain_provider,
            blockchain_endpoint=blockchain_endpoint,
        )
        self.log.info("Connecting to {}".format(self.blockchain_endpoint))
        if self._blockchain_provider is NO_BLOCKCHAIN_CONNECTION:
            raise self.NoProvider("There are no configured blockchain providers")

        # Connect if not connected
        try:
            self.w3 = self.Web3(provider=self._blockchain_provider)
            self.client = EthereumClient.from_w3(w3=self.w3)
        except requests.ConnectionError:  # RPC
            raise self.ConnectionFailed(
                f"Connection Failed - {str(self.blockchain_endpoint)} - is RPC enabled?"
            )
        except FileNotFoundError:  # IPC File Protocol
            raise self.ConnectionFailed(
                f"Connection Failed - {str(self.blockchain_endpoint)} - is IPC enabled?"
            )
        else:
            self.attach_middleware()

        return self.is_connected

    @property
    def provider(self) -> BaseProvider:
        return self._blockchain_provider

    def _attach_blockchain_provider(
        self,
        blockchain_provider: Optional[BaseProvider] = None,
        blockchain_endpoint: str = None,
    ) -> None:
        """
        https://web3py.readthedocs.io/en/latest/providers.html#providers
        """

        if not blockchain_endpoint and not blockchain_provider:
            raise self.NoProvider("No URI or provider instances supplied.")

        if blockchain_endpoint and not blockchain_provider:
            uri_breakdown = urlparse(blockchain_endpoint)

            if uri_breakdown.scheme == 'tester':
                providers = {
                    'pyevm': _get_pyevm_test_provider,
                    'mock': _get_mock_test_provider
                }
                provider_scheme = uri_breakdown.netloc

            else:
                providers = {
                    'auto': _get_auto_provider,
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
                if Path(blockchain_endpoint).is_file():
                    # file is available - assume ipc/file scheme
                    provider_scheme = "file"
                    self.log.info(
                        f"Auto-detected provider scheme as 'file://' for provider {blockchain_endpoint}"
                    )

            try:
                self._blockchain_provider = providers[provider_scheme](
                    blockchain_endpoint
                )
            except KeyError:
                raise self.UnsupportedProvider(
                    f"{blockchain_endpoint} is an invalid or unsupported blockchain provider URI"
                )
            else:
                self.blockchain_endpoint = (
                    blockchain_endpoint or NO_BLOCKCHAIN_CONNECTION
                )
        else:
            self._blockchain_provider = blockchain_provider

    @classmethod
    def _handle_failed_transaction(cls,
                                   exception: Exception,
                                   transaction_dict: dict,
                                   contract_function: Union[ContractFunction, ContractConstructor],
                                   logger: Logger = None
                                   ) -> None:
        """
        Re-raising error handler and context manager for transaction broadcast or
        build failure events at the interface layer. This method is a last line of defense
        against unhandled exceptions caused by transaction failures and must raise an exception.
        # TODO: #1504 - Additional Handling of validation failures (gas limits, invalid fields, etc.)
        """

        response = exception.args[0]

        # Assume this error is formatted as an RPC response
        try:
            code = int(response['code'])
            message = response['message']
        except Exception:
            # TODO: #1504 - Try even harder to determine if this is insufficient funds causing the issue,
            #               This may be best handled at the agent or actor layer for registry and token interactions.
            # Worst case scenario - raise the exception held in context implicitly
            raise exception

        if code != cls.TransactionFailed.IPC_CODE:
            # Only handle client-specific exceptions
            # https://www.jsonrpc.org/specification Section 5.1
            raise exception

        if logger:
            logger.critical(message)  # simple context

        transaction_failed = cls.TransactionFailed(message=message,  # rich error (best case)
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
    def build_payload(self,
                      sender_address: str,
                      payload: dict = None,
                      transaction_gas_limit: int = None,
                      use_pending_nonce: bool = True,
                      ) -> dict:

        nonce = self.client.get_transaction_count(account=sender_address, pending=use_pending_nonce)
        base_payload = {'nonce': nonce, 'from': sender_address}

        # Aggregate
        if not payload:
            payload = {}
        payload.update(base_payload)
        # Explicit gas override - will skip gas estimation in next operation.
        if transaction_gas_limit:
            payload['gas'] = int(transaction_gas_limit)
        return payload

    @validate_checksum_address
    def build_contract_transaction(self,
                                   contract_function: ContractFunction,
                                   sender_address: str,
                                   payload: dict = None,
                                   transaction_gas_limit: Optional[int] = None,
                                   gas_estimation_multiplier: Optional[float] = None,
                                   use_pending_nonce: Optional[bool] = None,
                                   ) -> dict:

        if transaction_gas_limit is not None:
            self.log.warn("The transaction gas limit of {transaction_gas_limit} will override gas estimation attempts")

        # Sanity checks for the gas estimation multiplier
        if gas_estimation_multiplier is not None:
            if not 1 <= gas_estimation_multiplier <= 3:  # Arbitrary upper bound.
                raise ValueError(f"The gas estimation multiplier should be a float between 1 and 3, "
                                 f"but we received {gas_estimation_multiplier}.")

        payload = self.build_payload(sender_address=sender_address,
                                     payload=payload,
                                     transaction_gas_limit=transaction_gas_limit,
                                     use_pending_nonce=use_pending_nonce)
        self.__log_transaction(transaction_dict=payload, contract_function=contract_function)
        try:
            if 'gas' not in payload:  # i.e., transaction_gas_limit is not None
                # As web3 build_transaction() will estimate gas with block identifier "pending" by default,
                # explicitly estimate gas here with block identifier 'latest' if not otherwise specified
                # as a pending transaction can cause gas estimation to fail, notably in case of worklock refunds.
                payload['gas'] = contract_function.estimate_gas(payload, block_identifier='latest')
            transaction_dict = contract_function.build_transaction(payload)
        except (TestTransactionFailed, ValidationError, ValueError) as error:
            # Note: Geth (1.9.15) raises ValueError in the same condition that pyevm raises ValidationError here.
            # Treat this condition as "Transaction Failed" during gas estimation.
            raise self._handle_failed_transaction(exception=error,
                                                  transaction_dict=payload,
                                                  contract_function=contract_function,
                                                  logger=self.log)

        # Increase the estimated gas limit according to the gas estimation multiplier, if any.
        if gas_estimation_multiplier and not transaction_gas_limit:
            gas_estimation = transaction_dict['gas']
            overestimation = int(math.ceil(gas_estimation * gas_estimation_multiplier))
            self.log.debug(f"Gas limit for this TX was increased from {gas_estimation} to {overestimation}, "
                           f"using a multiplier of {gas_estimation_multiplier}.")
            transaction_dict['gas'] = overestimation
            # TODO: What if we're going over the block limit? Not likely, but perhaps worth checking (NRN)

        return transaction_dict

    def sign_and_broadcast_transaction(self,
                                       transacting_power: TransactingPower,
                                       transaction_dict: TransactionDict,
                                       transaction_name: str = "",
                                       confirmations: int = 0,
                                       fire_and_forget: bool = False
                                       ) -> Union[TxReceipt, HexBytes]:
        """
        Takes a transaction dictionary, signs it with the configured signer, then broadcasts the signed
        transaction using the ethereum provider's eth_sendRawTransaction RPC endpoint.
        Optionally blocks for receipt and confirmation with 'confirmations', and 'fire_and_forget' flags.

        If 'fire and forget' is True this method returns the transaction hash only, without waiting for a receipt -
        otherwise return the transaction receipt.

        """
        #
        # Setup
        #

        # TODO # 1754 - Move this to singleton - I do not approve... nor does Bogdan?
        emitter = StdoutEmitter()

        #
        # Sign
        #

        # TODO: Show the USD Price:  https://api.coinmarketcap.com/v1/ticker/ethereum/
        
        try:
            # post-london fork transactions (Type 2)
            max_unit_price = transaction_dict['maxFeePerGas']
            tx_type = 'EIP-1559'
        except KeyError:
            # pre-london fork "legacy" transactions (Type 0)
            max_unit_price = transaction_dict['gasPrice']
            tx_type = 'Legacy'

        max_price_gwei = Web3.from_wei(max_unit_price, 'gwei')
        max_cost_wei = max_unit_price * transaction_dict['gas']
        max_cost = Web3.from_wei(max_cost_wei, 'ether')

        if transacting_power.is_device:
            emitter.message(f'Confirm transaction {transaction_name} on hardware wallet... '
                            f'({max_cost} ETH @ {max_price_gwei} gwei)',
                            color='yellow')
        signed_raw_transaction = transacting_power.sign_transaction(transaction_dict)

        #
        # Broadcast
        #
        emitter.message(f'Broadcasting {transaction_name} {tx_type} Transaction ({max_cost} ETH @ {max_price_gwei} gwei)',
                        color='yellow')
        try:
            txhash = self.client.send_raw_transaction(signed_raw_transaction)  # <--- BROADCAST
            emitter.message(f'TXHASH {txhash.hex()}', color='yellow')
        except (TestTransactionFailed, ValueError):
            raise  # TODO: Unify with Transaction failed handling -- Entry point for _handle_failed_transaction
        else:
            if fire_and_forget:
                return txhash

        #
        # Receipt
        #

        try:  # TODO: Handle block confirmation exceptions
            waiting_for = 'receipt'
            if confirmations:
                waiting_for = f'{confirmations} confirmations'
            emitter.message(f'Waiting {self.TIMEOUT} seconds for {waiting_for}', color='yellow')
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

    @validate_checksum_address
    def send_transaction(self,
                         contract_function: Union[ContractFunction, ContractConstructor],
                         transacting_power: TransactingPower,
                         payload: dict = None,
                         transaction_gas_limit: Optional[int] = None,
                         gas_estimation_multiplier: Optional[float] = 1.15,  # TODO: Workaround for #2635, #2337
                         confirmations: int = 0,
                         fire_and_forget: bool = False,  # do not wait for receipt.  See #2385
                         replace: bool = False,
                         ) -> Union[TxReceipt, HexBytes]:

        if fire_and_forget:
            if confirmations > 0:
                raise ValueError("Transaction Prevented: "
                                 "Cannot use 'confirmations' and 'fire_and_forget' options together.")

            use_pending_nonce = False  # TODO: #2385
        else:
            use_pending_nonce = replace  # TODO: #2385

        transaction = self.build_contract_transaction(contract_function=contract_function,
                                                      sender_address=transacting_power.account,
                                                      payload=payload,
                                                      transaction_gas_limit=transaction_gas_limit,
                                                      gas_estimation_multiplier=gas_estimation_multiplier,
                                                      use_pending_nonce=use_pending_nonce)

        # Get transaction name
        try:
            transaction_name = contract_function.fn_name.upper()
        except AttributeError:
            transaction_name = 'DEPLOY' if isinstance(contract_function, ContractConstructor) else 'UNKNOWN'

        txhash_or_receipt = self.sign_and_broadcast_transaction(transacting_power=transacting_power,
                                                                transaction_dict=transaction,
                                                                transaction_name=transaction_name,
                                                                confirmations=confirmations,
                                                                fire_and_forget=fire_and_forget)
        return txhash_or_receipt

    def get_contract_by_name(
        self,
        registry: ContractRegistry,
        contract_name: str,
    ):
        record = registry.search(
            chain_id=self.client.chain_id, contract_name=contract_name
        )
        contract = self.client.w3.eth.contract(
            abi=record.abi,
            address=record.address,
            ContractFactoryClass=self._CONTRACT_FACTORY,
        )
        return contract


Interfaces = Union[BlockchainInterface]


class BlockchainInterfaceFactory:
    """
    Canonical source of bound blockchain interfaces.
    """

    _instance = None
    _interfaces = dict()
    _default_interface_class = BlockchainInterface

    class CachedInterface(NamedTuple):
        interface: BlockchainInterface
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
    def is_interface_initialized(cls, blockchain_endpoint: str) -> bool:
        """
        Returns True if there is an existing connection with an equal blockchain_endpoint.
        """
        return bool(cls._interfaces.get(blockchain_endpoint, False))

    @classmethod
    def register_interface(cls,
                           interface: BlockchainInterface,
                           emitter=None,
                           force: bool = False
                           ) -> None:

        blockchain_endpoint = interface.blockchain_endpoint
        if (blockchain_endpoint in cls._interfaces) and not force:
            raise cls.InterfaceAlreadyInitialized(
                f"A connection already exists for {blockchain_endpoint}. "
                "Use .get_interface instead."
            )
        cached = cls.CachedInterface(interface=interface, emitter=emitter)
        cls._interfaces[blockchain_endpoint] = cached

    @classmethod
    def initialize_interface(
        cls,
        blockchain_endpoint: str,
        emitter=None,
        interface_class: Interfaces = None,
        *interface_args,
        **interface_kwargs,
    ) -> None:
        if not blockchain_endpoint:
            # Prevent empty strings and Falsy
            raise BlockchainInterface.UnsupportedProvider(
                f"'{blockchain_endpoint}' is not a valid provider URI"
            )

        if blockchain_endpoint in cls._interfaces:
            raise cls.InterfaceAlreadyInitialized(
                f"A connection already exists for {blockchain_endpoint}.  "
                f"Use .get_interface instead."
            )

        # Interface does not exist, initialize a new one.
        if not interface_class:
            interface_class = cls._default_interface_class
        interface = interface_class(
            blockchain_endpoint=blockchain_endpoint, *interface_args, **interface_kwargs
        )
        interface.connect()
        cls._interfaces[blockchain_endpoint] = cls.CachedInterface(
            interface=interface, emitter=emitter
        )

    @classmethod
    def get_interface(cls, blockchain_endpoint: str = None) -> Interfaces:

        # Try to get an existing cached interface.
        if blockchain_endpoint:
            try:
                cached_interface = cls._interfaces[blockchain_endpoint]
            except KeyError:
                raise cls.InterfaceNotInitialized(
                    f"There is no connection for {blockchain_endpoint}. "
                    f"Call .initialize_connection, then try again."
                )

        # Try to use the most recently created interface by default.
        else:
            try:
                cached_interface = list(cls._interfaces.values())[-1]
            except IndexError:
                raise cls.NoRegisteredInterfaces(
                    "There is no existing blockchain connection."
                )

        # Connect and Sync
        interface, emitter = cached_interface
        if not interface.is_connected:
            interface.connect()
        return interface

    @classmethod
    def get_or_create_interface(
        cls, blockchain_endpoint: str, *interface_args, **interface_kwargs
    ) -> BlockchainInterface:
        try:
            interface = cls.get_interface(blockchain_endpoint=blockchain_endpoint)
        except (cls.InterfaceNotInitialized, cls.NoRegisteredInterfaces):
            cls.initialize_interface(
                blockchain_endpoint=blockchain_endpoint,
                *interface_args,
                **interface_kwargs,
            )
            interface = cls.get_interface(blockchain_endpoint=blockchain_endpoint)
        return interface
