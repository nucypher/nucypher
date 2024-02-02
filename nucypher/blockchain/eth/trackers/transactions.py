import json
import time
from collections import deque
from dataclasses import dataclass
from json import JSONDecodeError
from tempfile import NamedTemporaryFile
from typing import Optional, Tuple, Union, List, Dict, NamedTuple, Callable

from hexbytes import HexBytes
from web3 import Web3
from web3.exceptions import TransactionNotFound
from web3.types import PendingTx as PendingTxData
from web3.types import Wei, Gwei, TxData, TxParams, RPCError

from nucypher.utilities.logging import Logger
from nucypher.utilities.task import SimpleTask

TxHash = HexBytes

log = Logger('txtracker')


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


def _log_gas_weather(base_fee: Wei, tip: Wei) -> None:
    base_fee_gwei = Web3.from_wei(base_fee, "gwei")
    tip_gwei = Web3.from_wei(tip, "gwei")
    log.info(f"Gas conditions: base {base_fee_gwei} gwei | tip {tip_gwei} gwei")


def _is_tx_finalized(w3: Web3, data: Union[TxData, PendingTxData]) -> bool:
    try:
        receipt = w3.eth.get_transaction_receipt(data["hash"])
    except TransactionNotFound:
        return False
    status = receipt.get("status")
    if status == 0:
        # If status in response equals 1 the transaction was successful.
        # If it is equals 0 the transaction was reverted by EVM.
        # https://web3py.readthedocs.io/en/stable/web3.eth.html#web3.eth.Eth.get_transaction_receipt
        # TODO: What follow-up actions can be taken if the transaction was reverted?
        log.info(
            f"Transaction {data['hash'].hex()} was reverted by EVM with status {status}"
        )
        return True
    return True


def _make_tx_params(tx: TxData) -> TxParams:
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


@dataclass
class PendingTx:
    txhash: TxHash
    created: int
    capped: bool = False
    retries: int = 0


@dataclass
class FutureTx:
    id: int
    params: TxParams
    signer: 'TransactingPower' = None
    info: Optional[Dict] = None
    success: Optional[Callable] = None
    error: Optional[Callable] = None


class TransactionTracker(SimpleTask):
    """
    A transaction tracker that manages the lifecycle of transactions on the Ethereum blockchain.

    The tracker is responsible for queuing, speeding up, and broadcasting transactions.
    Transactions are queued and broadcasted in a first-in-first-out (FIFO) order.

    There are two modes of operation: idle (slow scan) and work (fast scan).
    Internal state is written to a temporary cache file to help recover from crashes
    and restarts.

    """

    INTERVAL = 60 * 5  # 5 min. steady state interval

    IDLE_INTERVAL = INTERVAL  # renames above constant
    BLOCK_INTERVAL = 20  # ~20 blocks
    BLOCK_SAMPLE_SIZE = 1_000  # blocks
    DEFAULT_MAX_TIP = Gwei(2)  # gwei maxPriorityFeePerGas per transaction
    DEFAULT_TIMEOUT = 60 * 60  # 1 hour
    RPC_THROTTLE = 1  # min. seconds between RPC calls (>1 recommended)
    SPEEDUP_FACTOR = 1.125  # 12.5% increase
    CONFIRMATIONS = 3  # confirmations
    QUEUE_JOIN_TIMEOUT = 15  # seconds

    __COUNTER = 0

    class TransactionFinalized(Exception):
        """raised when a transaction has been included in a block"""

    class InsufficientFunds(RPCError):
        """raised when a transaction exceeds the spending cap"""

    def __init__(
            self,
            w3: Web3,
            max_tip: Gwei = DEFAULT_MAX_TIP,
            timeout: int = DEFAULT_TIMEOUT,
            *args, **kwargs,
    ):
        # w3
        self.w3 = w3

        # gwei -> wei
        self.max_tip: Wei = Web3.to_wei(max_tip, "gwei")
        self.timeout = timeout

        # queue of transactions to be broadcasted
        self.__queue = deque()

        # pending transaction (nonce, txhash)
        self.__pending: Optional[PendingTx] = None

        # transactions to follow beyond finalization
        # self.__follow = set()

        self.__file = NamedTemporaryFile(
            mode="w+",
            delete=False,

            # https://docs.python.org/3/library/functions.html#open
            # errors="strict",
            # errors="replace",
            # errors="ignore",

            encoding="utf-8",
            prefix="txs-cache-",
            suffix=".json",
        )
        super().__init__(*args, **kwargs)

    #
    # Disk
    #

    def __serialize_queue(self) -> List:
        queue = []
        for tx in self.__queue:
            # serialize the transaction
            tx = dict(tx)
            # tx = {str(k): v for k, v in tx.items()}
            queue.append(tx)
        return queue

    def __serialize_pending(self) -> Dict[str, str]:
        pending = dict()
        if self.pending:
            pending = {
                "created": str(self.pending.created),
                "txhash": str(self.pending.txhash.hex()),
            }
        return pending

    def __serialize_state(self) -> Dict:
        return {
            'pending': self.__serialize_pending(),
            'queue': self.__serialize_queue(),
        }

    def __write_file(self):
        self.__file.seek(0)
        self.__file.truncate()
        # state = self.__serialize_state()
        # json.dump(state, self.__file)
        self.__file.flush()
        self.log.debug(f"Updated transaction cache file {self.__file.name}")

    def __restore_state(self) -> None:

        # read file
        self.__file.seek(0)
        try:
            data = json.load(self.__file)
        except JSONDecodeError:
            data = dict()

        # deserialize
        pending = data.get('pending', dict())
        if pending:
            txhash = HexBytes(pending['txhash'])
            created = int(pending['created'])
            self.__pending = PendingTx(txhash=txhash, created=created)
        txs = data.get('queue', list())
        self.__queue = deque(txs)
        self.log.debug(f"Loaded {len(data)} transactions from cache file {self.__file.name}")

    #
    # Memory
    #

    def __track_pending(self, txhash: TxHash) -> None:
        """Track a pending transaction by its hash. Overwrites any existing pending transaction."""
        self.__pending = PendingTx(
            txhash=txhash,
            created=int(time.time())
        )
        self.__write_file()
        self.log.debug(f"Tacking pending transaction {txhash.hex()}")

    def __clear_pending(self) -> None:
        self.__pending = None
        self.__write_file()
        self.log.debug(
            f"Cleared 1 pending transaction - {len(self.queue)} "
            f"queued transaction{'s' if len(self.queue) > 1 else ''} remaining"
        )

    #
    # Rate
    #

    def __idle_mode(self):
        """Return to idle mode (slow down)"""
        self._task.interval = self.IDLE_INTERVAL
        self.log.info(f"[done] returning to idle mode with "
                      f"{self._task.interval} second interval")

    def __work_mode(self):
        """Start work mode (speed up)"""
        average_block_time = _get_average_blocktime(w3=self.w3, sample_size=self.BLOCK_SAMPLE_SIZE)
        self._task.interval = round(average_block_time * self.BLOCK_INTERVAL)
        self.log.info(f"[working] cycle interval is {self._task.interval} seconds")

    #
    # Transactions
    #

    def __handle_timeout(self) -> bool:
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

    def __fire(self, tx: FutureTx, msg: str) -> Optional[PendingTx]:
        try:
            txhash = self.w3.eth.send_raw_transaction(
                tx.signer.sign_transaction(tx.params)
            )
        except ValueError as e:
            _handle_rpc_error(e, tx=tx)
            return
        self.log.info(
            f"[{msg}] Fired transaction #{tx.params['nonce']}|{txhash.hex()}"
        )
        self.__track_pending(txhash=txhash)
        return self.pending

    def __speedup(self, txdata: TxData) -> Optional[TxHash]:
        """Speeds up the pending transaction."""
        params = _make_speedup_params(
            w3=self.w3,
            params=_make_tx_params(txdata),
            factor=self.SPEEDUP_FACTOR
        )
        if params["maxPriorityFeePerGas"] > self.max_tip:
            self.log.warn(
                f"[cap] Pending transaction maxPriorityFeePerGas exceeds spending cap {self.max_tip}"
            )
            self.pending.capped = True
            # self.__follow.add(txdata["hash"])
            self.log.info("Waiting for capped transaction to clear...")
            return
        txhash = self.__fire(tx=params, msg="speedup")
        self.pending.retries += 1
        self.log.info(f"Pending transaction #{txdata['nonce']} has been sped up {self.pending.retries} times")
        return txhash

    def __broadcast(self) -> Optional[TxHash]:
        """
        Broadcasts the next transaction in the queue.
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
        pending_tx = self.__fire(tx=future_tx, msg='broadcast')
        if not pending_tx:
            self.__queue.append(future_tx)
        return pending_tx

    def __get_pending_tx(self) -> Optional[TxData]:
        """Make and RPC call to get the pending transaction data."""

        if not self.pending:
            return

        # check if the transaction is finalized
        if self.__handle_timeout():
            self.__clear_pending()
            return

        # get the transaction data from RPC
        try:
            txdata = self.w3.eth.get_transaction(self.pending.txhash)
        except TransactionNotFound:
            self.log.info(f"Transaction {self.pending.txhash.hex()} not found")
            self.__clear_pending()
            return

        if _is_tx_finalized(w3=self.w3, data=txdata):
            log.info(
                f"[success] Transaction #{txdata['nonce']}|{txdata['hash'].hex()} "
                f"has been included in block #{txdata['blockNumber']}"
            )
            # self.__follow.add(txdata["hash"])
            self.__clear_pending()
            return

        return txdata

    def __followup(self) -> bool:
        current_block = self.w3.eth.block_number

        try:
            txdata = self.w3.eth.get_transaction(self.pending.txhash)
        except TransactionNotFound:
            self.log.info(f"[pending] transaction {self.pending.txhash.hex()} is still pending")
            return False

        tx_block = txdata["blockNumber"]
        if tx_block is None:
            self.log.info(f"[pending] Transaction {self.pending.txhash.hex()} is still pending")
            return False

        confirmations = current_block - tx_block
        self.log.info(
            f"[confirmations] Transaction #{txdata['nonce']}|{txdata['hash'].hex()} "
            f"has been included in block #{txdata['blockNumber']} with {confirmations} confirmations"
        )
        time.sleep(self.RPC_THROTTLE)
        if confirmations > self.CONFIRMATIONS:
            self.log.info(f"Stopping follow-up on transaction {txdata['hash'].hex()}")
            self.__clear_pending()
            return True

        return False

    #
    # Async
    #

    def run(self):
        """Executes one cycle of the transaction tracker."""

        # steady state
        if not self.busy:
            self.log.info(f"[idle] cycle interval is {self._task.interval} seconds")
            return
        self.log.info(
            f"Tracking {len(self.queue)} queued transaction{'s' if len(self.queue) > 1 else ''} "
            f"{'and 1 pending transaction' if self.pending else ''}"
        )

        # go to work
        self.__work_mode()

        # follow-up on post-finalized or capped transactions
        # these are not re-queued and not sped up, we're just
        # waiting for them to finalize or clear.
        # if self.__follow:
        #     clear = self.__followup()
        #     if not clear:
        #         return
        if self.pending and self.pending.capped:
            self.__followup()
            if self.pending:
                return

        # Speedup the current pending transaction
        pending_tx = self.__get_pending_tx()
        if pending_tx:
            self.__speedup(txdata=pending_tx)

        # Broadcast the next transaction in the queue
        if self.queue and not self.pending:
            self.__broadcast()

        # If all work is done, return to idle mode (slow down)
        if not self.busy:
            self.__idle_mode()

    def handle_errors(self, *args, **kwargs):
        """Handles unexpected errors during transaction processing."""
        self.log.warn("Error during transaction: {}".format(args[0].getTraceback()))
        if not self._task.running:
            self.log.warn("Restarting transaction task!")
            self.start(now=False)  # take a breather

    def block_until_free(self) -> None:
        """Blocks until the transaction is finalized."""
        start = time.time()
        while self.pending:
            if time.time() - start > self.QUEUE_JOIN_TIMEOUT:
                raise TimeoutError("Pending transaction timeout")
            self.log.info(f"Waiting for pending transaction {self.pending[1].hex()} to clear...")
            time.sleep(self.RPC_THROTTLE)

    ##############
    # Public API #
    ##############

    @property
    def queue(self) -> List[FutureTx]:
        return list(self.__queue)

    def send_transaction(self, tx: TxParams) -> TxHash:
        """
        Skip the queue and send a transaction as soon as
        possible without overriding the pending transaction.
        """
        if self.pending:
            # wait for the pending transaction to be finalized
            self.block_until_free()
        self.__queue.appendleft(tx)
        txhash = self.__broadcast()
        return txhash

    @property
    def pending(self) -> PendingTx:
        return self.__pending or None

    @property
    def busy(self) -> bool:
        if self.pending:
            return True
        if len(self.__queue) > 0:
            return True
        return False

    def queue_transaction(
            self,
            tx: TxParams,
            transacting_power,
            info: Dict = None,
            success: Callable = None,
            error: Callable = None
    ) -> FutureTx:
        performance = FutureTx(
            id=self.__COUNTER,
            params=tx,
            info=info,
            signer=transacting_power,
            success=success,
            error=error
        )
        self.__queue.append(performance)
        self.__COUNTER += 1
        self.log.info(f"Queued transaction #{tx['nonce']} "
                      f"in broadcast queue position {len(self.__queue)}")
        self.__write_file()
        return performance

    def start(self, now: bool = False) -> None:
        self.__restore_state()
        super().start(now=now)
        self.log.info("Starting transaction tracker")
