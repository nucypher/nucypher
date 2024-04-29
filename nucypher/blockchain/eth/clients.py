import time
from functools import cached_property
from typing import Union

from constant_sorrow.constants import UNKNOWN_DEVELOPMENT_CHAIN_ID
from eth_typing.evm import BlockNumber
from web3 import Web3
from web3._utils.threads import Timeout
from web3.contract.contract import Contract
from web3.exceptions import TimeExhausted, TransactionNotFound
from web3.types import TxReceipt, Wei

from nucypher.blockchain.eth.constants import AVERAGE_BLOCK_TIME_IN_SECONDS
from nucypher.blockchain.middleware.retry import (
    AlchemyRetryRequestMiddleware,
    InfuraRetryRequestMiddleware,
    RetryRequestMiddleware,
)
from nucypher.utilities.logging import Logger

UNKNOWN_DEVELOPMENT_CHAIN_ID.bool_value(True)


class Web3ClientError(Exception):
    pass


class Web3ClientConnectionFailed(Web3ClientError):
    pass


class Web3ClientUnexpectedVersionString(Web3ClientError):
    pass


PUBLIC_CHAINS = {
    1: "Mainnet",
    137: "Polygon/Mainnet",
    11155111: "Sepolia",
    80002: "Polygon/Amoy",
}

# This list is not exhaustive,
# but is sufficient for the current needs of the project.
POA_CHAINS = {
    4,  # Rinkeby
    5,  # Goerli
    42,  # Kovan
    77,  # Sokol
    100,  # xDAI
    10200,  # gnosis/chiado,
    137,  # Polygon/Mainnet
    80001,  # "Polygon/Mumbai"
    80002,  # "Polygon/Amoy"
}


class EthereumClient:
    BLOCK_CONFIRMATIONS_POLLING_TIME = 3  # seconds
    TRANSACTION_POLLING_TIME = 0.5  # seconds
    COOLING_TIME = 5  # seconds
    STALECHECK_ALLOWABLE_DELAY = 30  # seconds

    class ConnectionNotEstablished(RuntimeError):
        pass

    class SyncTimeout(RuntimeError):
        pass

    class UnknownAccount(ValueError):
        pass

    class TransactionBroadcastError(RuntimeError):
        pass

    class NotEnoughConfirmations(TransactionBroadcastError):
        pass

    class TransactionTimeout(TransactionBroadcastError):
        pass

    class ChainReorganizationDetected(TransactionBroadcastError):
        """Raised when block confirmations logic detects that a TX was lost due to a chain reorganization"""

        error_message = ("Chain re-organization detected: Transaction {transaction_hash} was reported to be in "
                         "block {block_hash}, but it's not there anymore")

        def __init__(self, receipt):
            self.receipt = receipt
            self.message = self.error_message.format(transaction_hash=Web3.to_hex(receipt['transactionHash']),
                                                     block_hash=Web3.to_hex(receipt['blockHash']))
            super().__init__(self.message)

    def __init__(self, w3):
        self.w3 = w3
        self.log = Logger(self.__class__.__name__)

        self._add_default_middleware()

    def _add_default_middleware(self):
        endpoint_uri = getattr(self.w3.provider, "endpoint_uri", "")
        if "infura" in endpoint_uri:
            self.log.debug("Adding Infura RPC retry middleware to client")
            self.add_middleware(InfuraRetryRequestMiddleware)
        elif "alchemyapi.io" in endpoint_uri:
            self.log.debug("Adding Alchemy RPC retry middleware to client")
            self.add_middleware(AlchemyRetryRequestMiddleware)
        else:
            self.log.debug("Adding RPC retry middleware to client")
            self.add_middleware(RetryRequestMiddleware)

    @property
    def chain_name(self) -> str:
        name = PUBLIC_CHAINS.get(self.chain_id, UNKNOWN_DEVELOPMENT_CHAIN_ID)
        return name

    @property
    def is_connected(self):
        return self.w3.is_connected()

    @property
    def accounts(self):
        return self.w3.eth.accounts

    def get_balance(self, account):
        return self.w3.eth.get_balance(account)

    def inject_middleware(self, middleware, **kwargs):
        self.w3.middleware_onion.inject(middleware, **kwargs)

    def add_middleware(self, middleware):
        self.w3.middleware_onion.add(middleware)

    def set_gas_strategy(self, gas_strategy):
        self.w3.eth.set_gas_price_strategy(gas_strategy)

    @cached_property
    def chain_id(self) -> int:
        _chain_id = self._get_chain_id(self.w3)
        return _chain_id

    @property
    def net_version(self) -> int:
        return int(self.w3.net.version)

    def get_contract(self, **kwargs) -> Contract:
        return self.w3.eth.contract(**kwargs)

    @property
    def gas_price(self) -> Wei:
        """
        Returns client's gas price. Underneath, it uses the eth_gasPrice JSON-RPC method
        """
        return self.w3.eth.gas_price

    def gas_price_for_transaction(self, transaction=None) -> Wei:
        """
        Obtains a gas price via the current gas strategy, if any; otherwise, it resorts to the client's gas price.
        This method mirrors the behavior of web3._utils.transactions when building transactions.
        """
        return self.w3.eth.generate_gas_price(transaction) or self.gas_price

    @property
    def block_number(self) -> BlockNumber:
        return self.w3.eth.block_number

    def wait_for_receipt(self,
                         transaction_hash: str,
                         timeout: float,
                         confirmations: int = 0) -> TxReceipt:
        receipt: TxReceipt = None
        if confirmations:
            # If we're waiting for confirmations, we may as well let pass some time initially to make everything easier
            time.sleep(self.COOLING_TIME)

            # We'll keep trying to get receipts until there are enough confirmations or the timeout happens
            with Timeout(seconds=timeout, exception=self.TransactionTimeout) as timeout_context:
                while not receipt:
                    try:
                        receipt = self.block_until_enough_confirmations(transaction_hash=transaction_hash,
                                                                        timeout=timeout,
                                                                        confirmations=confirmations)
                    except (self.ChainReorganizationDetected, self.NotEnoughConfirmations, TimeExhausted):
                        timeout_context.sleep(self.BLOCK_CONFIRMATIONS_POLLING_TIME)
                        continue

        else:
            # If not asking for confirmations, just use web3 and assume the returned receipt is final
            try:
                receipt = self.w3.eth.wait_for_transaction_receipt(
                    transaction_hash=transaction_hash,
                    timeout=timeout,
                    poll_latency=self.TRANSACTION_POLLING_TIME
                )
            except TimeExhausted:
                raise  # TODO: #1504 - Handle transaction timeout

        return receipt

    def block_until_enough_confirmations(self, transaction_hash: str, timeout: float, confirmations: int) -> dict:

        receipt: TxReceipt = self.w3.eth.wait_for_transaction_receipt(
            transaction_hash=transaction_hash,
            timeout=timeout,
            poll_latency=self.TRANSACTION_POLLING_TIME
        )

        preliminary_block_hash = Web3.to_hex(receipt['blockHash'])
        tx_block_number = Web3.to_int(receipt['blockNumber'])
        self.log.info(f"Transaction {Web3.to_hex(transaction_hash)} is preliminarily included in "
                      f"block {preliminary_block_hash}")

        confirmations_timeout = self._calculate_confirmations_timeout(confirmations)
        confirmations_so_far = 0
        with Timeout(seconds=confirmations_timeout, exception=self.NotEnoughConfirmations) as timeout_context:
            while confirmations_so_far < confirmations:
                timeout_context.sleep(self.BLOCK_CONFIRMATIONS_POLLING_TIME)
                self.check_transaction_is_on_chain(receipt=receipt)
                confirmations_so_far = self.block_number - tx_block_number
                self.log.info(f"We have {confirmations_so_far} confirmations. "
                              f"Waiting for {confirmations - confirmations_so_far} more.")
            return receipt

    @staticmethod
    def _calculate_confirmations_timeout(confirmations):
        confirmations_timeout = 3 * AVERAGE_BLOCK_TIME_IN_SECONDS * confirmations
        return confirmations_timeout

    def check_transaction_is_on_chain(self, receipt: TxReceipt) -> bool:
        transaction_hash = Web3.to_hex(receipt['transactionHash'])
        try:
            new_receipt = self.w3.eth.get_transaction_receipt(transaction_hash)
        except TransactionNotFound:
            reorg_detected = True
        else:
            reorg_detected = receipt['blockHash'] != new_receipt['blockHash']

        if reorg_detected:
            exception = self.ChainReorganizationDetected(receipt=receipt)
            self.log.info(exception.message)
            raise exception
            # TODO: Consider adding an optional param in this exception to include extra info (e.g. new block)
        return True

    def get_transaction(self, transaction_hash) -> dict:
        return self.w3.eth.get_transaction(transaction_hash)

    def get_transaction_receipt(self, transaction_hash) -> Union[dict, None]:
        return self.w3.eth.get_transaction_receipt(transaction_hash)

    def get_transaction_count(self, account: str, pending: bool) -> int:
        block_identifier = 'pending' if pending else 'latest'
        return self.w3.eth.get_transaction_count(account, block_identifier)

    def send_transaction(self, transaction_dict: dict) -> str:
        return self.w3.eth.send_transaction(transaction_dict)

    def send_raw_transaction(self, transaction_bytes: bytes) -> str:
        return self.w3.eth.send_raw_transaction(transaction_bytes)

    def get_blocktime(self):
        highest_block = self.w3.eth.get_block('latest')
        now = highest_block['timestamp']
        return now

    def get_block(self, block_identifier):
        return self.w3.eth.get_block(block_identifier)

    def _has_latest_block(self) -> bool:
        # TODO: Investigate using `web3.middleware.make_stalecheck_middleware` #2060
        # check that our local chain data is up to date
        return (time.time() - self.get_blocktime()) < self.STALECHECK_ALLOWABLE_DELAY

    @classmethod
    def _get_chain_id(cls, w3: Web3):
        result = w3.eth.chain_id
        try:
            # from hex-str
            chain_id = int(result, 16)
        except TypeError:
            # from str
            chain_id = int(result)

        return chain_id
