import time
from typing import Optional, Union

from eth_account.signers.local import LocalAccount
from twisted.internet.defer import Deferred
from web3 import Web3
from web3.exceptions import TransactionNotFound
from web3.types import TxReceipt

from nucypher.blockchain.eth.trackers.transactions.exceptions import (
    StrategyLimitExceeded,
    _handle_rpc_error,
)
from nucypher.blockchain.eth.trackers.transactions.state import _TrackerState
from nucypher.blockchain.eth.trackers.transactions.strategies import (
    SpeedupStrategy,
)
from nucypher.blockchain.eth.trackers.transactions.tx import (
    FinalizedTx,
    FutureTx,
    PendingTx,
    TxHash,
    _make_tx_params,
)
from nucypher.blockchain.eth.trackers.transactions.utils import (
    _get_average_blocktime,
    _get_receipt,
    txtracker_log,
    fire_hook,
)
from nucypher.utilities.task import SimpleTask


class _TransactionTracker(SimpleTask):
    """
    Do not import this - use the public TransactionTracker instead.

    The tracker is responsible for queuing, speeding up, and broadcasting transactions.
    Transactions are queued and broadcasted in a first-in-first-out (FIFO) order.

    There are two modes of operation: idle (slow scan) and work (fast scan).
    Internal state is written to a temporary cache file to help recover from crashes
    and restarts.
    """

    # tweaks
    _STRATEGY = SpeedupStrategy
    _TIMEOUT = 60 * 60  # 1 hour
    _TRACKING_CONFIRMATIONS = 300  # blocks until clearing a finalized transaction
    _RPC_THROTTLE = 1  # min. seconds between RPC calls (>1 recommended)
    _MIN_INTERVAL = (
        1  # absolute min. async loop interval (edge case of low block count)
    )

    # idle (slower)
    INTERVAL = 60 * 5  # seconds
    IDLE_INTERVAL = INTERVAL  # renames above constant

    # work (faster)
    BLOCK_INTERVAL = 20  # ~20 blocks
    BLOCK_SAMPLE_SIZE = 10_000  # blocks

    def __init__(self, w3: Web3, signer: LocalAccount):
        self.w3 = w3
        self.signer = signer
        self.strategy = self._STRATEGY(w3=w3)
        self.timeout = self._TIMEOUT
        self.__state = _TrackerState()
        super().__init__(interval=self.INTERVAL)

    #
    # Throttle
    #

    def __idle_mode(self) -> None:
        """Return to idle mode (slow down)"""
        self._task.interval = self.IDLE_INTERVAL
        self.log.info(
            f"[done] returning to idle mode with "
            f"{self._task.interval} second interval"
        )

    def __work_mode(self) -> None:
        """Start work mode (speed up)"""
        average_block_time = _get_average_blocktime(
            w3=self.w3, sample_size=self.BLOCK_SAMPLE_SIZE
        )
        self._task.interval = max(
            round(average_block_time * self.BLOCK_INTERVAL), self._MIN_INTERVAL
        )
        self.log.info(f"[working] cycle interval is {self._task.interval} seconds")

    #
    # Lifecycle
    #

    def __handle_active_tx(self) -> bool:
        """
        Handles the currently tracked pending transaction.

        There are 4 possible outcomes for the pending transaction:
        1. timeout
        2. finalized
        3. capped
        4. (re)strategize & (re)broadcast

        Returns True if the pending transaction has been cleared
        and the queue is ready for the next transaction.
        """

        # Outcome 1: pending transaction has timed out
        if self.__active_timed_out():
            hook = self.__state.active.on_timeout
            self.log.warn(
                f"[timeout] pending transaction {self.__state.active.txhash.hex()} has timed out"
            )
            self.__state.clear_active()
            if hook:
                fire_hook(hook=hook, tx=self.__state.active)
            return True

        # Outcome 2: pending transaction is finalized
        receipt = self.__get_receipt()
        if receipt:
            final_txhash = receipt["transactionHash"]
            confirmations = self.__get_confirmations(tx=self.__state.active)
            self.log.info(
                f"[finalized] Transaction #atx-{self.__state.active.id} has been finalized "
                f"with {confirmations} confirmations txhash: {final_txhash.hex()}"
            )
            self.__state.finalize_active_tx(receipt=receipt)
            return True

        # Outcome 3: pending transaction is capped
        if self.__state.active.capped:
            return False

        # Outcome4: pending transaction has been sped up
        self.__strategize()
        return False

    #
    # Broadcast
    #

    def __fire(self, tx: FutureTx, msg: str) -> Optional[PendingTx]:
        """Signs and broadcasts a transaction. Handles RPC errors and state changes."""
        try:
            txhash = self.w3.eth.send_raw_transaction(
                self.signer.sign_transaction(tx.params).rawTransaction
            )
        except ValueError as e:
            _handle_rpc_error(e, tx=tx)
            return
        self.log.info(
            f"[{msg}] fired transaction #atx-{tx.id}|{tx.params['nonce']}|{txhash.hex()}"
        )
        self.__state.evolve_future(tx=tx, txhash=txhash)

    def __strategize(self) -> Optional[TxHash]:
        """Retry the currently tracked pending transaction with the configured strategy."""
        try:
            params = self.strategy.execute(
                params=_make_tx_params(self.__state.active.data),
            )
        except StrategyLimitExceeded as e:
            self.__state.active.capped = True
            self.log.warn(
                f"[cap] pending transaction {self.__state.active.txhash.hex()} has been capped: {e}"
            )
            # It would be nice to re-queue the capped transaction however,
            # if the pending tx has already reached the spending cap it cannot
            # be sped up again (without increasing the cap).  For now, we just
            # let the transaction timeout and remove it, but this may cascade
            # into a chain of capped transactions if the cap is not increased / is too low.
            hook = self.__state.active.on_capped
            if hook:
                fire_hook(
                    hook=hook,
                    tx=self.__state.active
                )
            return

        # use the strategy-generated transaction parameters
        pending_tx = self.__fire(tx=params, msg="speedup")
        self.log.info(
            f"[{self.strategy.name}] transaction #{pending_tx.id} has been re-broadcasted"
        )

    def __broadcast(self) -> Optional[TxHash]:
        """
        Attempts to broadcast the next (future) transaction in the queue.
        If the transaction is not successful, it is re-queued.
        """
        future_tx = self.__state._pop()
        future_tx.params = _make_tx_params(future_tx.params)
        nonce = self.w3.eth.get_transaction_count(self.signer.address, "latest")
        if nonce > future_tx.params["nonce"]:
            self.log.warn(
                f"[broadcast] nonce {future_tx.params['nonce']} has been front-run "
                f"by another transaction. Updating queued tx nonce {future_tx.params['nonce']} -> {nonce}"
            )
        future_tx.params["nonce"] = nonce
        self.__fire(tx=future_tx, msg="broadcast")
        if not self.__state.active:
            self.__state._requeue(future_tx)
        return self.__state.active.txhash

    #
    # Monitoring
    #

    def __get_receipt(self) -> Optional[TxReceipt]:
        """Make and RPC call to get the pending transaction data."""
        try:
            txdata = self.w3.eth.get_transaction(self.__state.active.txhash)
            self.__state.active.data = txdata
        except TransactionNotFound:
            self.log.error(
                f"[error] Transaction {self.__state.active.txhash.hex()} not found"
            )
            self.__state.clear_active()
            return

        receipt = _get_receipt(w3=self.w3, data=txdata)
        if receipt:
            txtracker_log.info(
                f"[accepted] Transaction {txdata['nonce']}|{txdata['hash'].hex()} "
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
                self.log.info(
                    f"[pending] Transaction {tx.txhash.hex()} is still pending"
                )
                return 0
        elif isinstance(tx, FinalizedTx):
            tx_block = tx.receipt["blockNumber"]
        else:
            raise ValueError(f"Invalid transaction type {type(tx)}")

        confirmations = current_block - tx_block
        return confirmations

    def __active_timed_out(self) -> bool:
        """
        Returns True if the active transaction has timed out.
        Does not perform any state changes.
        """
        if not self.__state.active:
            return False
        timeout = (time.time() - self.__state.active.created) > self.timeout
        if timeout:
            self.log.warn(
                f"[timeout] Transaction {self.__state.active.txhash.hex()} has been pending for more than"
                f"{self.timeout} seconds"
            )
            return True
        time_remaining = round(
            self.timeout - (time.time() - self.__state.active.created)
        )
        minutes = round(time_remaining / 60)
        remainder_seconds = time_remaining % 60
        end_time = time.time() + time_remaining
        human_end_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(end_time))
        if time_remaining < (60 * 2):
            self.log.warn(
                f"[timeout] Transaction {self.__state.active.txhash.hex()} will timeout in "
                f"{minutes}m{remainder_seconds}s at {human_end_time}"
            )
        else:
            self.log.info(
                f"[pending] {self.__state.active.txhash.hex()} \n"
                f"[pending] {round(time.time() - self.__state.active.created)}s Elapsed | "
                f"{minutes}m{remainder_seconds}s Remaining | "
                f"Timeout at {human_end_time}"
            )
        return False

    def __monitor_finalized(self) -> None:
        """Follow-up on finalized transactions for a little while."""
        if not self.__state.finalized:
            return
        for tx in self.__state.finalized.copy():
            confirmations = self.__get_confirmations(tx=tx)
            txhash = tx.receipt["transactionHash"]
            if confirmations >= self._TRACKING_CONFIRMATIONS:
                if tx in self.__state.finalized:
                    self.__state.finalized.remove(tx)
                    self.log.info(
                        f"[monitor] stopped tracking {txhash.hex()} after {confirmations} confirmations"
                    )
                continue
            self.log.info(
                f"[monitor] transaction {txhash.hex()} has {confirmations} confirmations"
            )

    #
    # Async
    #

    def handle_errors(self, *args, **kwargs) -> None:
        """Handles unexpected errors during task processing."""
        self.log.warn("[recovery] error during transaction: {}".format(args[0].getTraceback()))
        self.__state.commit()
        time.sleep(self._RPC_THROTTLE)
        if not self._task.running:
            self.log.warn("[recovery] restarting transaction tracker!")
            self.start(now=False)  # take a breather

    def run(self) -> None:
        """Executes one cycle of the tracker."""

        self.__monitor_finalized()
        if not self.busy:
            self.log.info(f"[idle] cycle interval is {self._task.interval} seconds")
            return

        self.__work_mode()
        self.log.info(
            f"[working] tracking {len(self.__state.waiting)} queued "
            f"transaction{'s' if len(self.__state.waiting) > 1 else ''} "
            f"{'and 1 pending transaction' if self.__state.active else ''}"
        )

        if self.__state.active:
            clear = self.__handle_active_tx()
            if not clear:
                # active transaction is still pending
                return

        if self.fire:
            self.__broadcast()

        if not self.busy:
            self.__idle_mode()

    @property
    def fire(self) -> bool:
        """
        Returns True if the next queued transaction can be broadcasted right now.
        -
        Qualification: There is no active transaction and
        there are transactions waiting in the queue.
        """
        return self.__state.waiting and not self.__state.active

    @property
    def busy(self) -> bool:
        """Returns True if the tracker is busy."""
        if self.__state.active:
            return True
        if len(self.__state.waiting) > 0:
            return True
        return False

    def start(self, now: bool = True) -> Deferred:
        self.__state.restore()
        if now:
            self.log.info("[txtracker] starting transaction tracker now")
        else:
            self.log.info(f"[txtracker] starting transaction tracker in {self.INTERVAL} seconds")
        return super().start(now=now)
