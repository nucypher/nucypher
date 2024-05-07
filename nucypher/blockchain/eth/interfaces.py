import math
import pprint
from typing import Callable, Dict, NamedTuple, Optional, Union
from urllib.parse import urlparse

import requests
from atxm import AutomaticTxMachine
from atxm.exceptions import InsufficientFunds
from atxm.strategies import ExponentialSpeedupStrategy
from atxm.tx import AsyncTx, FaultedTx, FinalizedTx, FutureTx, PendingTx
from constant_sorrow.constants import (
    INSUFFICIENT_FUNDS,  # noqa
    NO_BLOCKCHAIN_CONNECTION,  # noqa
    UNKNOWN_TX_STATUS,  # noqa
)
from eth_utils import to_checksum_address
from web3 import HTTPProvider, IPCProvider, Web3, WebsocketProvider
from web3.contract.contract import Contract, ContractConstructor, ContractFunction
from web3.exceptions import TimeExhausted
from web3.middleware import geth_poa_middleware, simple_cache_middleware
from web3.providers import BaseProvider
from web3.types import TxParams, TxReceipt

from nucypher.blockchain.eth.clients import POA_CHAINS, EthereumClient
from nucypher.blockchain.eth.decorators import validate_checksum_address
from nucypher.blockchain.eth.providers import (
    _get_http_provider,
    _get_mock_test_provider,
    _get_pyevm_test_provider,
)
from nucypher.blockchain.eth.registry import ContractRegistry
from nucypher.blockchain.eth.utils import (
    get_transaction_name,
    get_tx_cost_data,
    prettify_eth_amount,
)
from nucypher.crypto.powers import TransactingPower
from nucypher.utilities.emitters import StdoutEmitter
from nucypher.utilities.gas_strategies import (
    WEB3_GAS_STRATEGIES,
    max_price_gas_strategy_wrapper,
)
from nucypher.utilities.logging import Logger

Web3Providers = Union[
    IPCProvider, WebsocketProvider, HTTPProvider
]  # TODO: Move to types.py


class BlockchainInterface:
    """
    Interacts with a solidity compiler and a registry in order to instantiate compiled
    ethereum contracts with the given web3 provider backend.
    """

    TIMEOUT = 600  # seconds  # TODO: Correlate with the gas strategy - #2070

    DEFAULT_GAS_STRATEGY = "fast"
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

        def __init__(
            self,
            message: str,
            transaction_dict: dict,
            contract_function: Union[ContractFunction, ContractConstructor],
            *args,
        ):
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
            message = (
                f"{self.name} from {sender[:6]}... \n"
                f"Sender balance: {prettify_eth_amount(self.get_balance())} \n"
                f"Reason: {self.base_message} \n"
                f"Transaction: {self.payload}"
            )
            return message

        def get_balance(self):
            blockchain = BlockchainInterfaceFactory.get_interface()
            balance = blockchain.client.get_balance(account=self.payload["from"])
            return balance

        @property
        def insufficient_funds(self) -> str:
            try:
                transaction_fee = self.payload["gas"] * self.payload["gasPrice"]
            except KeyError:
                return self.default
            else:
                cost = transaction_fee + self.payload.get("value", 0)
                message = (
                    f'{self.name} from {self.payload["from"][:8]} - {self.base_message}. '
                    f"Calculated cost is {prettify_eth_amount(cost)}, "
                    f"but sender only has {prettify_eth_amount(self.get_balance())}."
                )
            return message

    class AsyncTxHooks:
        def __init__(
            self,
            on_broadcast_failure: Callable[[FutureTx, Exception], None],
            on_fault: Callable[[FaultedTx], None],
            on_finalized: Callable[[FinalizedTx], None],
            on_insufficient_funds: Callable[
                [Union[FutureTx, PendingTx], InsufficientFunds], None
            ],
            on_broadcast: Optional[Callable[[PendingTx], None]] = None,
        ):
            self.on_broadcast_failure = on_broadcast_failure
            self.on_fault = on_fault
            self.on_finalized = on_finalized
            self.on_insufficient_funds = on_insufficient_funds
            self.on_broadcast = (
                on_broadcast if on_broadcast else self.__default_on_broadcast
            )

        @staticmethod
        def __default_on_broadcast(tx: PendingTx):
            emitter = StdoutEmitter()
            max_cost, max_price_gwei, tx_type = get_tx_cost_data(tx.params)
            emitter.message(
                f"Broadcasted {tx_type} async tx {tx.id} with TXHASH {tx.txhash.hex()} ({max_cost} @ {max_price_gwei} gwei)",
                color="yellow",
            )

    def __init__(
        self,
        emitter=None,  # TODO # 1754
        poa: bool = None,
        light: bool = False,
        endpoint: str = NO_BLOCKCHAIN_CONNECTION,
        provider: BaseProvider = NO_BLOCKCHAIN_CONNECTION,
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

        self.log = Logger("Blockchain")
        self.poa = poa
        self.endpoint = endpoint
        self._provider = provider
        self.w3 = NO_BLOCKCHAIN_CONNECTION
        self.client: EthereumClient = NO_BLOCKCHAIN_CONNECTION
        self.is_light = light

        speedup_strategy = ExponentialSpeedupStrategy(
            w3=self.w3,
            min_time_between_speedups=120,
        )  # speedup txs if not mined after 2 mins.
        self.tx_machine = AutomaticTxMachine(
            w3=self.w3, tx_exec_timeout=self.TIMEOUT, strategies=[speedup_strategy]
        )

        # TODO: Not ready to give users total flexibility. Let's stick for the moment to known values. See #2447
        if gas_strategy not in (
            "slow",
            "medium",
            "fast",
            "free",
            None,
        ):  # FIXME: What is 'None' doing here?
            raise ValueError(f"'{gas_strategy}' is an invalid gas strategy")
        self.gas_strategy = gas_strategy or self.DEFAULT_GAS_STRATEGY
        self.max_gas_price = max_gas_price

    def __repr__(self):
        r = "{name}({uri})".format(name=self.__class__.__name__, uri=self.endpoint)
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
                    raise ValueError(
                        f"{gas_strategy} must be callable to be a valid gas strategy."
                    )
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
            self.log.debug("Injecting POA middleware at layer 0")
            self.client.inject_middleware(geth_poa_middleware, layer=0)

        self.log.debug("Adding simple_cache_middleware")
        self.client.add_middleware(simple_cache_middleware)

        # TODO:  See #2770
        # self.configure_gas_strategy()

    def configure_gas_strategy(self, gas_strategy: Optional[Callable] = None) -> None:
        if gas_strategy:
            reported_gas_strategy = f"fixed/{gas_strategy.name}"
        else:
            reported_gas_strategy = f"web3/{self.gas_strategy}"
            gas_strategy = self.get_gas_strategy(self.gas_strategy)

        configuration_message = f"Using gas strategy '{reported_gas_strategy}'"

        if self.max_gas_price:
            __price = Web3.to_wei(self.max_gas_price, "gwei")  # from gwei to wei
            gas_strategy = max_price_gas_strategy_wrapper(
                gas_strategy=gas_strategy, max_gas_price_wei=__price
            )
            configuration_message += f", with a max price of {self.max_gas_price} gwei."

        self.client.set_gas_strategy(gas_strategy=gas_strategy)

        # TODO: This line must not be called prior to establishing a connection
        #        Move it down to a lower layer, near the client.
        # gwei_gas_price = Web3.from_wei(self.client.gas_price_for_transaction(), 'gwei')

        self.log.info(configuration_message)
        # self.log.debug(f"Gas strategy currently reports a gas price of {gwei_gas_price} gwei.")

    def connect(self):
        endpoint = self.endpoint
        self.log.info(f"Using external Web3 Provider '{self.endpoint}'")

        # Attach Provider
        self._attach_blockchain_provider(
            provider=self._provider,
            endpoint=endpoint,
        )
        self.log.info("Connecting to {}".format(self.endpoint))
        if self._provider is NO_BLOCKCHAIN_CONNECTION:
            raise self.NoProvider("There are no configured blockchain providers")

        # Connect if not connected
        try:
            self.w3 = self.Web3(provider=self._provider)
            self.tx_machine.w3 = self.w3  # share this web3 instance with the tracker
            self.client = EthereumClient(w3=self.w3)
        except requests.ConnectionError:  # RPC
            raise self.ConnectionFailed(
                f"Connection Failed - {str(self.endpoint)} - is RPC enabled?"
            )
        except FileNotFoundError:  # IPC File Protocol
            raise self.ConnectionFailed(
                f"Connection Failed - {str(self.endpoint)} - is IPC enabled?"
            )
        else:
            self.attach_middleware()

        return self.is_connected

    @property
    def provider(self) -> BaseProvider:
        return self._provider

    def _attach_blockchain_provider(
        self,
        provider: Optional[BaseProvider] = None,
        endpoint: str = None,
    ) -> None:
        """
        https://web3py.readthedocs.io/en/latest/providers.html#providers
        """

        if not endpoint and not provider:
            raise self.NoProvider("No URI or provider instances supplied.")

        if endpoint and not provider:
            uri_breakdown = urlparse(endpoint)
            provider_scheme = (
                uri_breakdown.netloc
                if uri_breakdown.scheme == "tester"
                else uri_breakdown.scheme
            )
            if provider_scheme == "pyevm":
                self._provider = _get_pyevm_test_provider(endpoint)
            elif provider_scheme == "mock":
                self._provider = _get_mock_test_provider(endpoint)
            elif provider_scheme == "http" or provider_scheme == "https":
                self._provider = _get_http_provider(endpoint)
            else:
                raise self.UnsupportedProvider(
                    f"{endpoint} is an invalid or unsupported blockchain provider URI"
                )
            self.endpoint = endpoint or NO_BLOCKCHAIN_CONNECTION
        else:
            self._provider = provider

    @classmethod
    def _handle_failed_transaction(
        cls,
        exception: Exception,
        transaction_dict: dict,
        contract_function: Union[ContractFunction, ContractConstructor],
        logger: Logger = None,
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
            code = int(response["code"])
            message = response["message"]
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

        transaction_failed = cls.TransactionFailed(
            message=message,  # rich error (best case)
            contract_function=contract_function,
            transaction_dict=transaction_dict,
        )
        raise transaction_failed from exception

    def __log_transaction(
        self, transaction_dict: dict, contract_function: ContractFunction
    ):
        """
        Format and log a transaction dict and return the transaction name string.
        This method *must not* mutate the original transaction dict.
        """
        # Do not mutate the original transaction dict
        tx = dict(transaction_dict).copy()

        # Format
        if tx.get("to"):
            tx["to"] = to_checksum_address(contract_function.address)
        try:
            tx["selector"] = contract_function.selector
        except AttributeError:
            pass
        tx["from"] = to_checksum_address(tx["from"])
        tx.update(
            {
                f: prettify_eth_amount(v)
                for f, v in tx.items()
                if f in ("gasPrice", "value")
            }
        )
        payload_pprint = ", ".join("{}: {}".format(k, v) for k, v in tx.items())

        # Log
        transaction_name = get_transaction_name(contract_function=contract_function)
        self.log.debug(f"[TX-{transaction_name}] | {payload_pprint}")

    @validate_checksum_address
    def build_payload(
        self,
        sender_address: str,
        payload: dict = None,
        transaction_gas_limit: int = None,
        use_pending_nonce: bool = True,
    ) -> dict:
        nonce = self.client.get_transaction_count(
            account=sender_address, pending=use_pending_nonce
        )
        base_payload = {"nonce": nonce, "from": sender_address}

        # Aggregate
        if not payload:
            payload = {}
        payload.update(base_payload)
        # Explicit gas override - will skip gas estimation in next operation.
        if transaction_gas_limit:
            payload["gas"] = int(transaction_gas_limit)
        return payload

    @validate_checksum_address
    def build_contract_transaction(
        self,
        contract_function: ContractFunction,
        sender_address: str,
        payload: dict = None,
        transaction_gas_limit: Optional[int] = None,
        gas_estimation_multiplier: Optional[float] = None,
        use_pending_nonce: Optional[bool] = None,
        log_now: bool = True,
    ) -> TxParams:
        if transaction_gas_limit is not None:
            self.log.warn(
                f"The transaction gas limit of {transaction_gas_limit} will override gas estimation attempts"
            )

        # Sanity checks for the gas estimation multiplier
        if gas_estimation_multiplier is not None:
            if not 1 <= gas_estimation_multiplier <= 3:  # Arbitrary upper bound.
                raise ValueError(
                    f"The gas estimation multiplier must be a float between 1 and 3, "
                    f"but we received {gas_estimation_multiplier}."
                )

        payload = self.build_payload(
            sender_address=sender_address,
            payload=payload,
            transaction_gas_limit=transaction_gas_limit,
            use_pending_nonce=use_pending_nonce,
        )

        if log_now:
            self.__log_transaction(
                transaction_dict=payload, contract_function=contract_function
            )
        try:
            if "gas" not in payload:  # i.e., transaction_gas_limit is not None
                # As web3 build_transaction() will estimate gas with block identifier "pending" by default,
                # explicitly estimate gas here with block identifier 'latest' if not otherwise specified
                # as a pending transaction can cause gas estimation to fail, notably in case of worklock refunds.
                payload["gas"] = contract_function.estimate_gas(
                    payload, block_identifier="latest"
                )
            transaction_dict = contract_function.build_transaction(payload)
        except ValueError as error:
            # Note: Geth (1.9.15) raises ValueError in the same condition that pyevm raises ValidationError here.
            # Treat this condition as "Transaction Failed" during gas estimation.
            raise self._handle_failed_transaction(
                exception=error,
                transaction_dict=payload,
                contract_function=contract_function,
                logger=self.log,
            )

        # Increase the estimated gas limit according to the gas estimation multiplier, if any.
        if gas_estimation_multiplier and not transaction_gas_limit:
            gas_estimation = transaction_dict["gas"]
            overestimation = int(math.ceil(gas_estimation * gas_estimation_multiplier))
            self.log.debug(
                f"Gas limit for this TX was increased from {gas_estimation} to {overestimation}, "
                f"using a multiplier of {gas_estimation_multiplier}."
            )
            transaction_dict["gas"] = overestimation
            # TODO: What if we're going over the block limit? Not likely, but perhaps worth checking (NRN)

        return transaction_dict

    def sign_and_broadcast_transaction(
        self,
        transacting_power: TransactingPower,
        transaction_dict: Dict,
        transaction_name: str = "",
        confirmations: int = 0,
    ) -> TxReceipt:
        """
        Takes a transaction dictionary, signs it with the configured signer,
        then broadcasts the signed transaction using the RPC provider's
        eth_sendRawTransaction endpoint.
        """
        emitter = StdoutEmitter()
        max_cost, max_price_gwei, tx_type = get_tx_cost_data(transaction_dict)

        if transacting_power.is_device:
            emitter.message(
                f"Confirm transaction {transaction_name} on hardware wallet... "
                f"({max_cost} @ {max_price_gwei} gwei)",
                color="yellow",
            )
        raw_transaction = transacting_power.sign_transaction(transaction_dict)

        #
        # Broadcast
        #
        emitter.message(
            f"Broadcasting {transaction_name} {tx_type} Transaction ({max_cost} @ {max_price_gwei} gwei)",
            color="yellow",
        )
        try:
            txhash = self.client.send_raw_transaction(raw_transaction)  # <--- BROADCAST
            emitter.message(f"TXHASH {txhash.hex()}", color="yellow")
        except ValueError:
            raise  # TODO: Unify with Transaction failed handling -- Entry point for _handle_failed_transaction

        #
        # Receipt
        #

        try:
            waiting_for = "receipt"
            if confirmations:
                waiting_for = f"{confirmations} confirmations"
            emitter.message(
                f"Waiting {self.TIMEOUT} seconds for {waiting_for}", color="yellow"
            )
            receipt = self.client.wait_for_receipt(
                txhash, timeout=self.TIMEOUT, confirmations=confirmations
            )
        except TimeExhausted:
            raise
        else:
            self.log.debug(
                f"[RECEIPT-{transaction_name}] | txhash: {receipt['transactionHash'].hex()}"
            )

        #
        # Confirmations
        #

        # Primary check
        transaction_status = receipt.get("status", UNKNOWN_TX_STATUS)
        if transaction_status == 0:
            failure = (
                f"Transaction transmitted, but receipt returned status code 0. "
                f"Full receipt: \n {pprint.pformat(receipt, indent=2)}"
            )
            raise self.InterfaceError(failure)

        if transaction_status is UNKNOWN_TX_STATUS:
            self.log.info(
                f"Unknown transaction status for {txhash} (receipt did not contain a status field)"
            )

            # Secondary check
            tx = self.client.get_transaction(txhash)
            if tx["gas"] == receipt["gasUsed"]:
                raise self.InterfaceError(
                    f"Transaction consumed 100% of transaction gas. "
                    f"Full receipt: \n {pprint.pformat(receipt, indent=2)}"
                )

        return receipt

    def send_async_transaction(
        self,
        contract_function: ContractFunction,
        transacting_power: TransactingPower,
        async_tx_hooks: AsyncTxHooks,
        transaction_gas_limit: Optional[int] = None,
        gas_estimation_multiplier: float = 1.15,
        info: Optional[Dict[str, str]] = None,
        payload: dict = None,
    ) -> AsyncTx:
        transaction = self.build_contract_transaction(
            contract_function=contract_function,
            sender_address=transacting_power.account,
            payload=payload,
            transaction_gas_limit=transaction_gas_limit,
            gas_estimation_multiplier=gas_estimation_multiplier,
            log_now=False,
        )

        basic_info = {
            "name": contract_function.fn_name,
            "contract": contract_function.address,
        }
        if info:
            basic_info.update(info)

        # TODO: This is a bit of a hack. temporary solution until incoming PR #3382 is merged.
        signer = transacting_power._signer._get_signer(transacting_power.account)

        async_tx = self.tx_machine.queue_transaction(
            info=info,
            params=transaction,
            signer=signer,
            on_broadcast=async_tx_hooks.on_broadcast,
            on_broadcast_failure=async_tx_hooks.on_broadcast_failure,
            on_fault=async_tx_hooks.on_fault,
            on_finalized=async_tx_hooks.on_finalized,
            on_insufficient_funds=async_tx_hooks.on_insufficient_funds,
        )
        return async_tx

    @validate_checksum_address
    def send_transaction(
        self,
        contract_function: Union[ContractFunction, ContractConstructor],
        transacting_power: TransactingPower,
        payload: dict = None,
        transaction_gas_limit: Optional[int] = None,
        gas_estimation_multiplier: Optional[
            float
        ] = 1.15,  # TODO: Workaround for #2635, #2337
    ) -> TxReceipt:
        transaction = self.build_contract_transaction(
            contract_function=contract_function,
            sender_address=transacting_power.account,
            payload=payload,
            transaction_gas_limit=transaction_gas_limit,
            gas_estimation_multiplier=gas_estimation_multiplier,
            log_now=True,
        )
        try:
            transaction_name = contract_function.fn_name.upper()
        except AttributeError:
            transaction_name = (
                "DEPLOY"
                if isinstance(contract_function, ContractConstructor)
                else "UNKNOWN"
            )
        receipt = self.sign_and_broadcast_transaction(
            transacting_power=transacting_power,
            transaction_dict=transaction,
            transaction_name=transaction_name,
        )
        return receipt

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
    def is_interface_initialized(cls, endpoint: str) -> bool:
        """
        Returns True if there is an existing connection with an equal endpoint.
        """
        return bool(cls._interfaces.get(endpoint, False))

    @classmethod
    def register_interface(
        cls, interface: BlockchainInterface, emitter=None, force: bool = False
    ) -> None:
        endpoint = interface.endpoint
        if (endpoint in cls._interfaces) and not force:
            raise cls.InterfaceAlreadyInitialized(
                f"A connection already exists for {endpoint}. "
                "Use .get_interface instead."
            )
        cached = cls.CachedInterface(interface=interface, emitter=emitter)
        cls._interfaces[endpoint] = cached

    @classmethod
    def initialize_interface(
        cls,
        endpoint: str,
        emitter=None,
        interface_class: Interfaces = None,
        *interface_args,
        **interface_kwargs,
    ) -> None:
        if not endpoint:
            # Prevent empty strings and Falsy
            raise BlockchainInterface.UnsupportedProvider(
                f"'{endpoint}' is not a valid provider URI"
            )

        if endpoint in cls._interfaces:
            raise cls.InterfaceAlreadyInitialized(
                f"A connection already exists for {endpoint}.  "
                f"Use .get_interface instead."
            )

        # Interface does not exist, initialize a new one.
        if not interface_class:
            interface_class = cls._default_interface_class
        interface = interface_class(
            endpoint=endpoint, *interface_args, **interface_kwargs
        )
        interface.connect()
        cls._interfaces[endpoint] = cls.CachedInterface(
            interface=interface, emitter=emitter
        )

    @classmethod
    def get_interface(cls, endpoint: str = None) -> Interfaces:
        # Try to get an existing cached interface.
        if endpoint:
            try:
                cached_interface = cls._interfaces[endpoint]
            except KeyError:
                raise cls.InterfaceNotInitialized(
                    f"There is no connection for {endpoint}. "
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
        cls, endpoint: str, *interface_args, **interface_kwargs
    ) -> BlockchainInterface:
        try:
            interface = cls.get_interface(endpoint=endpoint)
        except (cls.InterfaceNotInitialized, cls.NoRegisteredInterfaces):
            cls.initialize_interface(
                endpoint=endpoint,
                *interface_args,
                **interface_kwargs,
            )
            interface = cls.get_interface(endpoint=endpoint)
        return interface
