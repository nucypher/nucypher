import json
import time
from collections import deque
from json import JSONDecodeError
from tempfile import NamedTemporaryFile
from typing import Optional, Tuple, Union, List, Dict

from hexbytes import HexBytes
from web3 import Web3
from web3.exceptions import TransactionNotFound
from web3.types import Nonce, Wei, Gwei, TxData, TxParams, RPCError, PendingTx

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


def _is_tx_finalized(w3: Web3, data: Union[TxData, PendingTx]) -> bool:
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
        log.warn("Overriding non-protocol pending transactions")

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

    INTERVAL = 60 * 5  # 5 min. steady state interval

    IDLE_INTERVAL = INTERVAL  # renames above constant
    BLOCK_INTERVAL = 20  # ~20 blocks
    BLOCK_SAMPLE_SIZE = 1_000  # blocks
    DEFAULT_MAX_TIP = Gwei(5)  # gwei maxPriorityFeePerGas per transaction
    DEFAULT_TIMEOUT = 60 * 60  # 1 hour
    RPC_THROTTLE = 1  # min. seconds between RPC calls (>1 recommended)
    SPEEDUP_FACTOR = 1.125  # 12.5% increase
    CONFIRMATIONS = 3  # confirmations
    QUEUE_JOIN_TIMEOUT = 15  # seconds

    class TransactionFinalized(Exception):
        """raised when a transaction has been included in a block"""

    class InsufficientFunds(RPCError):
        """raised when a transaction exceeds the spending cap"""

    def __init__(
            self,
            w3: Web3,
            transacting_power: "actors.TransactingPower",
            max_tip: Gwei = DEFAULT_MAX_TIP,
            timeout: int = DEFAULT_TIMEOUT,
            *args, **kwargs,
    ):
        # w3
        self.w3 = w3
        self.transacting_power = transacting_power  # TODO: Use LocalAccount instead
        self.address = transacting_power.account

        # gwei -> wei
        self.max_tip: Wei = self.w3.to_wei(max_tip, "gwei")
        self.timeout = timeout

        # state

        # queue of transactions to be broadcasted
        self.__queue = deque()

        # pending transaction (nonce, txhash)
        self.__pending: Optional[Tuple[Nonce, TxHash]] = None

        # transactions to follow beyond finalization
        self.__follow = set()

        self.__file = NamedTemporaryFile(
            mode="w+",
            delete=False,
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
            tx = {str(k): v for k, v in tx.items()}
            queue.append(tx)
        return queue

    def __serialize_pending(self) -> Dict[str, str]:
        pending = dict()
        if self.pending:
            try:
                created, txhash = self.__pending
            except ValueError:
                print(self.__pending)
                raise ValueError("Invalid pending transaction")
            pending = {str(created): txhash.hex()}
        return pending

    def __serialize_state(self) -> Dict:
        return {
            'pending': self.__serialize_pending(),
            'queue': self.__serialize_queue()
        }

    def __write_file(self):
        self.__file.seek(0)
        self.__file.truncate()
        state = self.__serialize_state()
        # json.dump(state, self.__file)
        self.__file.flush()
        self.log.debug(f"Updated transaction cache file {self.__file.name}")

    def __restore_state(self) -> None:
        self.__file.seek(0)
        try:
            data = json.load(self.__file)
        except JSONDecodeError:
            data = dict()
        self.log.debug(f"Loaded {len(data)} transactions from cache file {self.__file.name}")
        pending = data.get('pending', dict())
        txs = data.get('queue', list())
        self.__queue = deque(txs)
        self.__pending = tuple(pending.items())

    #
    # Memory
    #

    def __track_pending(self, txhash: TxHash) -> None:
        """Track a pending transaction by its hash. Overwrites any existing pending transaction."""
        self.__pending = (int(time.time()), txhash)
        self.__write_file()
        self.log.debug(f"Tacking pending transaction {txhash.hex()}")

    def __clear_pending(self) -> None:
        self.__pending = tuple()
        self.__write_file()
        self.log.debug("Cleared pending transaction")

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
        if not self.__pending:
            return False
        created, txhash = self.__pending
        timeout = (time.time() - created) > self.timeout
        if timeout:
            self.log.warn(
                f"[timeout] Transaction {txhash.hex()} has been pending for more than"
                f"{self.timeout} seconds"
            )
            return True
        time_remaining = round(self.timeout - (time.time() - created))
        minutes = round(time_remaining / 60)
        remainder_seconds = time_remaining % 60
        end_time = time.time() + time_remaining
        human_end_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(end_time))
        if time_remaining < (60 * 2):
            self.log.warn(
                f"Transaction {txhash.hex()} will timeout in "
                f"{minutes}m{remainder_seconds}s at {human_end_time}"
            )
        else:
            self.log.info(
                f"Pending Transaction: {txhash.hex()} \n"
                f"Elapsed {round(time.time() - created)}s, "
                f"Remaining {minutes}m{remainder_seconds}s, "
                f"Timeout {human_end_time}"
            )
        return False

    def __fire(self, tx: PendingTx, msg: str) -> Optional[TxHash]:
        try:
            txhash = self.w3.eth.send_raw_transaction(
                self.transacting_power.sign_transaction(tx)
            )
        except ValueError as e:
            _handle_rpc_error(e, tx=tx)
            return
        self.log.info(
            f"[{msg}] Fired transaction #{tx['nonce']}|{txhash.hex()}"
        )
        self.__track_pending(txhash=txhash)
        return txhash

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
            self.__follow.add(txdata["hash"])
            self.log.info("Waiting for capped transaction to clear...")
            self.__clear_pending()
            return
        txhash = self.__fire(tx=params, msg="speedup")
        return txhash

    def __broadcast(self) -> TxHash:
        """
        Broadcasts the next transaction in the queue.
        If the transaction is not successful, it is re-queued.
        """
        params = self.__queue.popleft()
        params = _make_tx_params(params)
        nonce = self.w3.eth.get_transaction_count(params["from"], "latest")
        if nonce > params["nonce"]:
            self.log.warn(
                f"Transaction #{params['nonce']} has been front-run "
                f"by another transaction. Updating nonce {params['nonce']} -> {nonce}"
            )
        params["nonce"] = nonce
        txhash = self.__fire(tx=params, msg='broadcast')
        if not txhash:
            self.__queue.append(params)
        return txhash

    def __get_pending_tx(self) -> Optional[TxData]:
        """Make and RPC call to get the pending transaction data."""

        if not self.__pending:
            return

        # check if the transaction is finalized
        if self.__handle_timeout():
            self.__clear_pending()
            return

        # get the transaction data from RPC
        created, txhash = self.__pending
        try:
            txdata = self.w3.eth.get_transaction(txhash)
        except TransactionNotFound:
            self.log.info(f"Transaction {txhash.hex()} not found")
            self.__clear_pending()
            return

        if _is_tx_finalized(w3=self.w3, data=txdata):
            log.info(
                f"[success] Transaction #{txdata['nonce']}|{txdata['hash'].hex()} "
                f"has been included in block #{txdata['blockNumber']}"
            )
            self.__follow.add(txdata["hash"])
            self.__clear_pending()
            return

        return txdata

    def __followup(self) -> None:
        current_block = self.w3.eth.block_number
        for txhash in self.__follow.copy():

            try:
                txdata = self.w3.eth.get_transaction(txhash)
            except TransactionNotFound:
                self.log.info(f"Transaction {txhash.hex()} is still pending")
                continue

            tx_block = txdata["blockNumber"]
            if tx_block is None:
                self.log.info(f"Transaction {txhash.hex()} is still pending")
                continue

            confirmations = current_block - tx_block
            self.log.info(
                f"[confirmations] Transaction #{txdata['nonce']}|{txdata['hash'].hex()} "
                f"has been included in block #{txdata['blockNumber']} with {confirmations} confirmations"
            )
            time.sleep(self.RPC_THROTTLE)
            if confirmations > self.CONFIRMATIONS:
                self.log.info(f"Stopping follow-up on transaction {txdata['hash'].hex()}")
                self.__follow.remove(txdata["hash"])

            return confirmations
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
            f"Tracking {len(self.__queue)} queued transaction{'s' if len(self.__queue) > 1 else ''} "
            f"{'and 1 pending transaction' if self.__pending else ''}"
        )

        # go to work
        self.__work_mode()

        # follow-up on post-finalized or capped transactions
        if self.__follow:
            self.__followup()
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
    def queue(self) -> List[TxParams]:
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
    def pending(self) -> Optional[Tuple[Nonce, TxHash]]:
        return self.__pending or None

    @property
    def busy(self) -> bool:
        if self.pending:
            return True
        if len(self.__queue) > 0:
            return True
        return False

    def queue_transaction(self, tx: TxParams) -> None:
        self.__queue.append(tx)
        self.log.info(f"Queued transaction #{tx['nonce']} "
                      f"in broadcast queue position {len(self.__queue)}")
        self.__write_file()

    def start(self, now: bool = False) -> None:
        self.__restore_state()
        super().start(now=now)
        self.log.info("Starting transaction tracker")
