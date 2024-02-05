import json
import time
from collections import deque
from json import JSONDecodeError
from pathlib import Path
from typing import Callable, Deque, Dict, Optional, Set

from eth_typing import ChecksumAddress
from web3.types import TxParams, TxReceipt

from nucypher.blockchain.eth.trackers.transactions.tx import (
    FinalizedTx,
    FutureTx,
    PendingTx,
    TxHash,
)
from nucypher.blockchain.eth.trackers.transactions.utils import fire_hook, txtracker_log
from nucypher.config.constants import APP_DIR


class _TrackerState:
    """State management for transaction tracking."""

    __DEFAULT_FILEPATH = Path(APP_DIR.user_cache_dir) / ".txs.json"
    __COUNTER = 0  # id generator

    def __init__(self, filepath: Optional[Path] = None):
        self.__filepath = filepath or self.__DEFAULT_FILEPATH
        self.__queue: Deque[FutureTx] = deque()
        self.__active: Optional[PendingTx] = None
        self.finalized: Set[FinalizedTx] = set()

    def to_dict(self) -> Dict:
        """Serialize the state to a JSON string."""
        active = self.__active.to_dict() if self.__active else {}
        queue = [tx.to_dict() for tx in self.__queue]
        finalized = [tx.to_dict() for tx in self.finalized]
        _dict = {"queue": queue, "active": active, "finalized": finalized}
        return _dict

    def commit(self) -> None:
        """Write the state to the cache file."""
        with open(self.__filepath, "w+t") as file:
            data = json.dumps(self.to_dict())
            file.write(data)
        txtracker_log.debug(f"[state] wrote transaction cache file {self.__filepath}")

    def restore(self) -> bool:
        """
        Restore the state from the cache file.
        Returns True if the cache file exists and was successfully restored with data.
        """

        # read & parse
        if not self.__filepath.exists():
            return False
        with open(self.__filepath, "r+t") as file:
            data = file.read()
        try:
            data = json.loads(data)
        except JSONDecodeError:
            data = dict()
        active = data.get("active", dict())
        queue = data.get("queue", list())
        final = data.get("finalized", list())

        # deserialize & restore
        self.__active = PendingTx.from_dict(active) if active else None
        self.__queue.extend(FutureTx.from_dict(tx) for tx in queue)
        self.finalized = {FinalizedTx.from_dict(tx) for tx in final}
        txtracker_log.debug(
            f"[state] restored {len(queue)} transactions from cache file {self.__filepath}"
        )

        return bool(data)

    def __track_active(self, tx: PendingTx) -> None:
        """Update the active transaction (destructive operation)."""
        old = None
        if self.__active:
            old = self.__active.txhash
        self.__active = tx
        self.commit()
        if old:
            txtracker_log.debug(
                f"[state] updated active transaction {old.hex()} -> {tx.txhash.hex()}"
            )
            return
        txtracker_log.debug(f"[state] tracked active transaction {tx.txhash.hex()}")

    def evolve_future(self, tx: FutureTx, txhash: TxHash) -> None:
        """
        Evolve a future transaction into a pending transaction.
        Uses polymorphism to transform the future transaction into a pending transaction.
        """
        tx.txhash = txhash
        tx.created = int(time.time())
        tx.capped = False
        tx.__class__ = PendingTx
        tx: PendingTx
        self.__track_active(tx=tx)
        txtracker_log.info(f"[state] #atx-{self.__active.id} queued -> pending")

    def finalize_active_tx(self, receipt: TxReceipt) -> None:
        """
        Finalizes a pending transaction.
        Use polymorphism to transform the pending transaction into a finalized transaction.
        """
        hook = self.__active.on_finalized
        if not self.__active:
            raise RuntimeError("No pending transaction to finalize")
        self.__active.receipt = receipt
        self.__active.__class__ = FinalizedTx
        tx = self.__active
        self.finalized.add(tx)  # noqa
        txtracker_log.info(f"[state] #atx-{tx.id} pending -> finalized")
        self.clear_active()
        if hook:
            fire_hook(hook=hook, tx=tx)

    def clear_active(self) -> None:
        """Clear the active transaction (destructive operation)."""
        self.__active = None
        self.commit()
        txtracker_log.debug(
            f"[state] cleared 1 pending transaction \n"
            f"[state] {len(self.waiting)} queued "
            f"transaction{'s' if len(self.waiting) != 1 else ''} remaining"
        )

    @property
    def active(self) -> Optional[PendingTx]:
        """Return the active pending transaction if there is one."""
        return self.__active

    @property
    def waiting(self) -> Deque[FutureTx]:
        """Return the queue of transactions."""
        return self.__queue

    def _pop(self) -> FutureTx:
        """Pop the next transaction from the queue."""
        return self.__queue.popleft()

    def _requeue(self, tx: FutureTx) -> None:
        """Re-queue a transaction for broadcast and subsequent tracking."""
        self.__queue.append(tx)
        self.commit()
        txtracker_log.info(
            f"[state] re-queued transaction #atx-{tx.id} "
            f"priority {len(self.__queue)}"
        )

    def _queue(
        self,
        params: TxParams,
        _from: ChecksumAddress,
        info: Dict[str, str] = None,
        on_broadcast: Optional[Callable] = None,
        on_timeout: Optional[Callable] = None,
        on_capped: Optional[Callable] = None,
        on_finalized: Optional[Callable] = None,
        on_revert: Optional[Callable] = None,
        on_error: Optional[Callable] = None,
    ) -> FutureTx:
        """Queue a new transaction for broadcast and subsequent tracking."""
        tx = FutureTx(
            _from=_from,
            id=self.__COUNTER,
            params=params,
            info=info,
        )

        # configure hooks
        tx.on_broadcast = on_broadcast
        tx.on_timeout = on_timeout
        tx.on_halt = on_capped
        tx.on_finalized = on_finalized
        tx.on_revert = on_revert
        tx.on_error = on_error

        self.__queue.append(tx)
        self.commit()
        self.__COUNTER += 1
        txtracker_log.info(
            f"[state] queued transaction #atx-{tx.id} " f"priority {len(self.__queue)}"
        )
        return tx
