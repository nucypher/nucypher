import json
import time
from abc import ABC
from collections import deque
from dataclasses import dataclass, field
from json import JSONDecodeError
from pathlib import Path
from typing import Optional, Tuple, Union, List, Dict, Callable, Deque, Set

from hexbytes import HexBytes
from web3 import Web3
from web3.exceptions import TransactionNotFound
from web3.types import PendingTx as PendingTxData, TxReceipt
from web3.types import Wei, Gwei, TxData, TxParams, RPCError

from nucypher.config.constants import DEFAULT_CONFIG_ROOT
from nucypher.utilities.logging import Logger
from nucypher.utilities.task import SimpleTask

TxHash = HexBytes

log = Logger('txtracker')


def _serialize_tx_params(params: TxParams) -> Dict:
    """Serializes transaction parameters to a dictionary for disk storage."""
    data = params.get("data", b"")
    if isinstance(data, bytes):
        data = data.hex()
    return {
        "nonce": params["nonce"],
        "maxPriorityFeePerGas": params["maxPriorityFeePerGas"],
        "maxFeePerGas": params["maxFeePerGas"],
        "chainId": params["chainId"],
        "gas": params["gas"],
        "type": params.get("type", ''),
        "from": params["from"],
        "to": params["to"],
        "value": params["value"],
        "data": data
    }


def _serialize_tx_receipt(receipt: TxReceipt) -> Dict:
    return {
        "transactionHash": receipt["transactionHash"].hex(),
        "transactionIndex": receipt["transactionIndex"],
        "blockHash": receipt["blockHash"].hex(),
        "blockNumber": receipt["blockNumber"],
        "from": receipt["from"],
        "to": receipt["to"],
        "cumulativeGasUsed": receipt["cumulativeGasUsed"],
        "gasUsed": receipt["gasUsed"],
        "contractAddress": receipt["contractAddress"],
        "logs": [dict(l) for l in receipt["logs"]],
        "status": receipt["status"],
        "logsBloom": receipt["logsBloom"].hex(),
        "root": receipt["root"].hex(),
        "type": receipt["type"],
        "effectiveGasPrice": receipt["effectiveGasPrice"],
    }


def _make_tx_params(tx: TxData) -> TxParams:
    """Creates a transaction parameters object from a transaction data object for broadcast."""
    return TxParams(
        {
            "nonce": tx['nonce'],
            "maxPriorityFeePerGas": tx["maxPriorityFeePerGas"],
            "maxFeePerGas": tx["maxFeePerGas"],
            "chainId": tx["chainId"],
            "gas": tx["gas"],
            "type": "0x2",
            "from": tx["from"],
            "to": tx["to"],
            "value": tx["value"],
            "data": tx.get("data", b"")
        }
    )


@dataclass
class AsyncTX(ABC):
    id: int
    final: bool = field(default=None, init=False)


@dataclass
class FutureTx(AsyncTX):
    final: bool = field(default=False, init=False)
    params: TxParams
    signer: 'TransactingPower' = None
    info: Optional[Dict] = None
    success: Optional[Callable] = None
    error: Optional[Callable] = None

    def __hash__(self):
        return hash(self.id)

    def to_dict(self):
        return {
            "id": self.id,
            "params": _serialize_tx_params(self.params),
            "info": self.info,
        }

    @classmethod
    def from_dict(cls, data: Dict):
        return cls(
            id=int(data['id']),
            params=TxParams(data['params']),
            info=dict(data['info'])
        )


@dataclass
class PendingTx(AsyncTX):
    final: bool = field(default=False, init=False)
    txhash: TxHash
    created: int
    data: Optional[TxData] = None
    capped: bool = False
    retries: int = 0

    def __hash__(self):
        return hash(self.txhash)

    def to_dict(self):
        return {
            "id": self.id,
            "txhash": self.txhash.hex(),
            "created": self.created,
            "data": self.data,
            "capped": self.capped,
            "retries": self.retries
        }

    @classmethod
    def from_dict(cls, data: Dict):
        data = dict(data) if data else dict()
        return cls(
            id=int(data['id']),
            txhash=HexBytes(data['txhash']),
            created=int(data['created']),
            data=data,
            capped=bool(data['capped']),
            retries=int(data['retries'])
        )


@dataclass
class FinalizedTx(AsyncTX):
    final: bool = field(default=True, init=False)
    receipt: TxReceipt

    def __hash__(self):
        return hash(self.receipt['transactionHash'])

    def to_dict(self):
        return {
            "id": self.id,
            "receipt": _serialize_tx_receipt(self.receipt)
        }

    @classmethod
    def from_dict(cls, data: Dict):
        return cls(
            id=int(data['id']),
            receipt=TxReceipt(data['receipt'])
        )


def _get_average_blocktime(w3, sample_size: int) -> float:
    """Returns the average block time in seconds."""
    latest_block = w3.eth.get_block("latest")
    if latest_block.number == 0:
        return 0
    sample_block_number = latest_block.number - sample_size
    if sample_block_number <= 0:
        return 0
    base_block = w3.eth.get_block(sample_block_number)
    delta = latest_block.timestamp - base_block.timestamp
    average_block_time = delta / sample_size
    return average_block_time


def _log_gas_weather(base_fee: Wei, tip: Wei) -> None:
    base_fee_gwei = Web3.from_wei(base_fee, "gwei")
    tip_gwei = Web3.from_wei(tip, "gwei")
    log.info(f"Gas conditions: base {base_fee_gwei} gwei | tip {tip_gwei} gwei")


def _calculate_speedup_fee(w3: Web3, tx: TxParams, factor: float) -> Tuple[Wei, Wei]:
    base_fee = w3.eth.get_block("latest")["baseFeePerGas"]
    suggested_tip = w3.eth.max_priority_fee
    _log_gas_weather(base_fee, suggested_tip)
    max_priority_fee = round(
        max(tx["maxPriorityFeePerGas"], suggested_tip) * factor
    )
    max_fee_per_gas = round(
        max(tx["maxFeePerGas"] * factor, (base_fee * 2) + max_priority_fee)
    )
    return max_priority_fee, max_fee_per_gas


def _get_receipt(w3: Web3, data: Union[TxData, PendingTxData]) -> Optional[TxReceipt]:
    try:
        receipt = w3.eth.get_transaction_receipt(data["hash"])
    except TransactionNotFound:
        return
    status = receipt.get("status")
    if status == 0:
        # If status in response equals 1 the transaction was successful.
        # If it is equals 0 the transaction was reverted by EVM.
        # https://web3py.readthedocs.io/en/stable/web3.eth.html#web3.eth.Eth.get_transaction_receipt
        # TODO: What follow-up actions can be taken if the transaction was reverted?
        log.info(
            f"Transaction {data['hash'].hex()} was reverted by EVM with status {status}"
        )
        return receipt
    return receipt


def _make_speedup_params(w3: Web3, params: TxParams, factor: float) -> TxParams:
    old_tip, old_max_fee = params["maxPriorityFeePerGas"], params["maxFeePerGas"]
    new_tip, new_max_fee = _calculate_speedup_fee(w3=w3, tx=params, factor=factor)
    tip_increase = round(Web3.from_wei(new_tip - old_tip, 'gwei'), 4)
    fee_increase = round(Web3.from_wei(new_max_fee - old_max_fee, 'gwei'), 4)

    latest_nonce = w3.eth.get_transaction_count(params["from"], "latest")
    pending_nonce = w3.eth.get_transaction_count(params["from"], "pending")
    if pending_nonce - latest_nonce > 0:
        log.warn("Overriding pending transaction!")

    log.info(
        f"Speeding up transaction #{params['nonce']} \n"
        f"maxPriorityFeePerGas (~+{tip_increase} gwei) {old_tip} -> {new_tip} \n"
        f"maxFeePerGas (~+{fee_increase} gwei) {old_max_fee} -> {new_max_fee}"
    )
    params = dict(params)
    params["maxPriorityFeePerGas"] = new_tip
    params["maxFeePerGas"] = new_max_fee
    params["nonce"] = latest_nonce
    params = TxParams(params)
    return params


def _handle_rpc_error(e: Exception, tx: TxParams) -> None:
    error = RPCError(**e.args[0])
    log.critical(
        f"Transaction #{tx['nonce']} failed with {error['code']} | {error['message']}"
    )
    if error['code'] == -32000:
        if "insufficient funds" in error['message']:
            raise TransactionTracker.InsufficientFunds


class TransactionTracker(SimpleTask):
    """
    A transaction tracker that manages the lifecycle of transactions on the Ethereum blockchain.

    The tracker is responsible for queuing, speeding up, and broadcasting transactions.
    Transactions are queued and broadcasted in a first-in-first-out (FIFO) order.

    There are two modes of operation: idle (slow scan) and work (fast scan).
    Internal state is written to a temporary cache file to help recover from crashes
    and restarts.
    """

    # slow
    INTERVAL = 20 * 1
    IDLE_INTERVAL = INTERVAL  # renames above constant

    # fast
    BLOCK_INTERVAL = 20  # ~20 blocks
    BLOCK_SAMPLE_SIZE = 10_000  # blocks

    # public config
    DEFAULT_MAX_TIP = Gwei(1)  # gwei maxPriorityFeePerGas per transaction
    DEFAULT_TIMEOUT = 60 * 60  # 1 hour
    SPEEDUP_FACTOR = 1.125  # 12.5% increase

    # tweaks
    _FINALITY_CONFIRMATIONS = 30  # blocks until a transaction is considered finalized
    _TRACKING_CONFIRMATIONS = 300  # confirmations until clearing a finalized transaction
    _RPC_THROTTLE = 1  # min. seconds between RPC calls (>1 recommended)
    _QUEUE_JOIN_TIMEOUT = 15  # seconds

    # internal
    __COUNTER = 0  # id generator
    __MIN_INTERVAL = 1  # seconds
    __DEFAULT_FILEPATH = DEFAULT_CONFIG_ROOT / "txtracker.json"

    class TransactionFinalized(Exception):
        """raised when a transaction has been included in a block"""

    class InsufficientFunds(RPCError):
        """raised when a transaction exceeds the spending cap"""

    def __init__(
            self,
            w3: Web3,
            max_tip: Gwei = DEFAULT_MAX_TIP,
            timeout: int = DEFAULT_TIMEOUT,
            filepath: str = __DEFAULT_FILEPATH,
            disk_restore: bool = False
    ):
        # w3
        self.w3 = w3

        # gwei -> wei
        self.max_tip: Wei = Web3.to_wei(max_tip, "gwei")
        self.timeout = timeout
        self.disk_restore = disk_restore

        # internal
        self.__queue: Deque[FutureTx] = deque()
        self.__pending: Optional[PendingTx] = None
        self.__finalized: Set[FinalizedTx] = set()
        self.__filepath = Path(filepath)
        super().__init__(interval=self.INTERVAL)

    #
    # Disk I/O
    #

    def __write_file(self) -> None:
        if not self.disk_restore:
            return
        pending = self.pending.to_dict() if self.pending else dict()
        queue = [tx.to_dict() for tx in self.queue]
        data = json.dumps({'pending': pending, 'queue': queue})
        with open(self.__filepath, 'w+t') as file:
            file.write(data)
        self.log.debug(f"Updated transaction cache file {self.__filepath}")

    def __restore_state(self) -> None:
        if not self.disk_restore:
            return

        if not self.__filepath.exists():
            return

        # read
        with open(self.__filepath, 'r+t') as file:
            data = file.read()
        try:
            data = json.loads(data)
        except JSONDecodeError:
            data = dict()

        # parse
        pending = data.get('pending', dict())
        queue = data.get('queue', list())

        # deserialize
        if pending is not None:
            pending = PendingTx.from_dict(pending)
        txs = [FutureTx.from_dict(tx) for tx in queue]

        # restore
        self.__pending = pending
        self.__queue = deque(txs)
        self.log.debug(f"Loaded {len(queue)} transactions from cache file {self.__filepath}")

    #
    # Throttle
    #

    def __idle_mode(self) -> None:
        """Return to idle mode (slow down)"""
        self._task.interval = self.IDLE_INTERVAL
        self.log.info(f"[done] returning to idle mode with "
                      f"{self._task.interval} second interval")

    def __work_mode(self) -> None:
        """Start work mode (speed up)"""
        average_block_time = _get_average_blocktime(w3=self.w3, sample_size=self.BLOCK_SAMPLE_SIZE)
        self._task.interval = max(round(average_block_time * self.BLOCK_INTERVAL), self.__MIN_INTERVAL)
        self.log.info(f"[working] cycle interval is {self._task.interval} seconds")

    #
    # Lifecycle
    #

    def __track_pending(self, tx: PendingTx) -> None:
        """Track a pending transaction by its hash. Overwrites any existing pending transaction."""
        self.__pending = tx
        self.__write_file()
        self.log.debug(f"Tacking pending transaction {tx.txhash.hex()}")

    def __evolve_future(self, tx: FutureTx, txhash) -> None:
        """
        Evolve a future transaction into a pending transaction.
        Uses polymorphism to transform the future transaction into a pending transaction.
        """
        tx.txhash = txhash
        tx.created = int(time.time())
        tx.capped = False
        tx.retries = 0
        tx.__class__ = PendingTx
        tx: PendingTx
        self.__track_pending(tx=tx)
        self.log.info(f"{self.pending.id} Queued -> Pending")

    def __handle_pending(self) -> bool:
        """
        Handles the currently tracked pending transaction.

        There are 4 possible outcomes:
        1. Pending transaction has timed out
        2. Pending transaction is finalized
        3. Pending transaction is capped
        4. Pending transaction has been sped up

        Returns True if the pending transaction has been cleared
        and the queue is ready for the next transaction.
        """

        # Outcome 1: pending transaction has timed out
        if self.__is_pending_timed_out():
            self.log.warn(f"[timeout] pending transaction {self.pending.txhash.hex()} has timed out")
            self.__clear_pending()
            return True

        # Outcome 2: pending transaction is finalized
        receipt = self.__get_receipt()
        if receipt:
            self.__finalize_pending(receipt=receipt)
            return True

        # Outcome 3: pending transaction is capped
        if self.pending.capped:
            return False

        # Outcome4: pending transaction has been sped up
        self.__speedup()
        return False

    def __finalize_pending(self, receipt: TxReceipt) -> None:
        """
        Finalizes a pending transaction.
        Use polymorphism to transform the pending transaction into a finalized transaction.
        """
        self.pending.receipt = receipt
        self.pending.__class__ = FinalizedTx
        self.__finalized.add(self.pending)
        self.__clear_pending()
        self.log.info(f"{self.pending.id} Pending -> Finalized")

    def __clear_pending(self) -> None:
        self.__pending = None
        self.__write_file()
        self.log.debug(
            f"Cleared 1 pending transaction - {len(self.queue)} "
            f"queued transaction{'s' if len(self.queue) > 1 else ''} remaining"
        )

    #
    # Broadcast
    #

    def __fire(self, tx: FutureTx, msg: str) -> Optional[PendingTx]:
        try:
            txhash = self.w3.eth.send_raw_transaction(
                tx.signer.sign_transaction(tx.params)
            )
        except ValueError as e:
            _handle_rpc_error(e, tx=tx)
            return
        self.log.info(
            f"[{msg}] Fired transaction #{tx.id}: {tx.params['nonce']}|{txhash.hex()}"
        )
        self.__evolve_future(tx=tx, txhash=txhash)

    def __speedup(self) -> Optional[TxHash]:
        """Speeds up the currently tracked pending transaction."""
        params = _make_speedup_params(
            w3=self.w3,
            params=_make_tx_params(self.pending.data),
            factor=self.SPEEDUP_FACTOR
        )
        if params["maxPriorityFeePerGas"] > self.max_tip:
            self.log.warn(
                f"[cap] Pending transaction maxPriorityFeePerGas exceeds spending cap {self.max_tip}"
            )
            self.pending.capped = True
            self.log.info("Waiting for capped transaction to clear...")
            return

        self.__fire(tx=params, msg="speedup")
        self.pending.retries += 1
        self.log.info(f"Pending transaction #{params['nonce']} has been sped up {self.pending.retries} times")

    def __broadcast(self) -> Optional[TxHash]:
        """
        Attempts to broadcast the next (future) transaction in the queue.
        If the transaction is not successful, it is re-queued.
        """
        future_tx = self.__queue.popleft()
        future_tx.params = _make_tx_params(future_tx.params)
        nonce = self.w3.eth.get_transaction_count(future_tx.params["from"], "latest")
        if nonce > future_tx.params["nonce"]:
            self.log.warn(
                f"Transaction #{future_tx.params['nonce']} has been front-run "
                f"by another transaction. Updating nonce {future_tx.params['nonce']} -> {nonce}"
            )
        future_tx.params["nonce"] = nonce
        self.__fire(tx=future_tx, msg='broadcast')
        if not self.pending:
            self.__queue.append(future_tx)
        return self.pending.txhash

    #
    # Monitoring
    #

    def __get_receipt(self):
        """Make and RPC call to get the pending transaction data."""
        try:
            txdata = self.w3.eth.get_transaction(self.pending.txhash)
            self.pending.data = txdata
        except TransactionNotFound:
            self.log.info(f"Transaction {self.pending.txhash.hex()} not found")
            self.__clear_pending()
            return

        receipt = _get_receipt(w3=self.w3, data=txdata)
        if receipt:
            log.info(
                f"[accepted] Transaction #{txdata['nonce']}|{txdata['hash'].hex()} "
                f"has been included in block #{txdata['blockNumber']}"
            )
            return receipt

    def __get_confirmations(self, tx: Union[PendingTx, FinalizedTx]) -> int:
        current_block = self.w3.eth.block_number
        try:
            txdata = self.w3.eth.get_transaction(tx.txhash)
        except TransactionNotFound:
            self.log.info(f"[pending] transaction {tx.txhash.hex()} is still pending")
            return 0

        if isinstance(tx, PendingTx):
            tx_block = txdata["blockNumber"]
            if tx_block is None:
                self.log.info(f"[pending] Transaction {tx.txhash.hex()} is still pending")
                return 0
        elif isinstance(tx, FinalizedTx):
            tx_block = tx.receipt["blockNumber"]
        else:
            raise ValueError(f"Invalid transaction type {type(tx)}")

        confirmations = current_block - tx_block
        return confirmations

    def __is_pending_timed_out(self) -> bool:
        if not self.pending:
            return False
        timeout = (time.time() - self.pending.created) > self.timeout
        if timeout:
            self.log.warn(
                f"[timeout] Transaction {self.pending.txhash.hex()} has been pending for more than"
                f"{self.timeout} seconds"
            )
            return True
        time_remaining = round(self.timeout - (time.time() - self.pending.created))
        minutes = round(time_remaining / 60)
        remainder_seconds = time_remaining % 60
        end_time = time.time() + time_remaining
        human_end_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(end_time))
        if time_remaining < (60 * 2):
            self.log.warn(
                f"Transaction {self.pending.txhash.hex()} will timeout in "
                f"{minutes}m{remainder_seconds}s at {human_end_time}"
            )
        else:
            self.log.info(
                f"Pending Transaction: {self.pending.txhash.hex()} \n"
                f"{round(time.time() - self.pending.created)}s Elapsed | "
                f"{minutes}m{remainder_seconds}s Remaining | "
                f"Timeout at {human_end_time}"
            )
        return False

    def __monitor_finalized(self) -> None:
        """Follow up on finalized transactions"""
        if not self.__finalized:
            return
        for tx in self.__finalized.copy():
            confirmations = self.__get_confirmations(tx=tx)
            txhash = tx.receipt['transactionHash']
            txblock = tx.receipt['blockNumber']
            if confirmations >= self._FINALITY_CONFIRMATIONS:
                self.log.info(f"[finalized] Transaction {txhash.hex()} has been finalized")
                if tx in self.finalized:
                    self.__finalized.remove(tx)
                continue
            self.log.info(
                f"[confirmation] Transaction {txhash.hex()} "
                f"has been included in block #{txblock} with {confirmations} confirmations"
            )

    #
    # Async
    #

    def handle_errors(self, *args, **kwargs):
        """Handles unexpected errors during transaction processing."""
        self.log.warn("Error during transaction: {}".format(args[0].getTraceback()))
        if not self._task.running:
            self.log.warn("Restarting transaction task!")
            self.start(now=False)  # take a breather

    def run(self):
        """Executes one cycle of the transaction tracker."""

        self.__monitor_finalized()
        if not self.busy:
            self.log.info(f"[idle] cycle interval is {self._task.interval} seconds")
            return

        self.__work_mode()
        self.log.info(
            f"[working] tracking {len(self.queue)} queued transaction{'s' if len(self.queue) > 1 else ''} "
            f"{'and 1 pending transaction' if self.pending else ''}"
        )

        if self.pending:
            clear = self.__handle_pending()
            if not clear:
                # pending transaction is still pending
                return

        if self.queue and not self.pending:
            self.__broadcast()

        if not self.busy:
            self.__idle_mode()

    ##############
    # Public API #
    ##############

    @property
    def queue(self) -> List[FutureTx]:
        return list(self.__queue)

    @property
    def pending(self) -> PendingTx:
        return self.__pending or None

    @property
    def finalized(self) -> List[FinalizedTx]:
        return list(self.__finalized)

    @property
    def busy(self) -> bool:
        if self.pending:
            return True
        if len(self.queue) > 0:
            return True
        return False

    @property
    def processed(self) -> int:
        return self.__COUNTER

    def queue_transaction(
            self,
            tx: TxParams,
            transacting_power,
            info: Dict = None,
            success: Callable = None,
            error: Callable = None
    ) -> FutureTx:
        tx = FutureTx(
            id=self.__COUNTER,
            params=tx,
            info=info,
            signer=transacting_power,
            success=success,
            error=error
        )
        self.__queue.append(tx)
        self.__COUNTER += 1
        self.log.info(f"Queued transaction #{tx.params['nonce']} "
                      f"in broadcast queue position {len(self.__queue)}")
        self.__write_file()
        return tx

    def start(self, now: bool = False, restore: bool = False) -> None:
        if restore:
            self.__restore_state()
        self.log.info("Starting transaction tracker")
        return super().start(now=now)
