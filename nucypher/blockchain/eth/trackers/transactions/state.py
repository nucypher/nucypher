import json
import time
from collections import deque
from json import JSONDecodeError
from pathlib import Path
from typing import Callable, Deque, Dict, Optional, Set

from web3.types import TxParams, TxReceipt

from nucypher.blockchain.eth.trackers.transactions.tx import (
    FinalizedTx,
    FutureTx,
    PendingTx,
)
from nucypher.blockchain.eth.trackers.transactions.utils import txtracker_log
from nucypher.config.constants import DEFAULT_CONFIG_ROOT


class _TrackerState:
    __DEFAULT_FILEPATH = Path(DEFAULT_CONFIG_ROOT / "txtracker.json")
    __COUNTER = 0  # id generator

    def __init__(self, filepath: Optional[Path] = None):
        self.__filepath = filepath or self.__DEFAULT_FILEPATH
        self.__queue: Deque[FutureTx] = deque()
        self.__pending: Optional[PendingTx] = None
        self.finalized: Set[FinalizedTx] = set()

    def __serialize(self) -> str:
        pending = self.__pending.to_dict() if self.__pending else dict()
        queue = [tx.to_dict() for tx in self.__queue]
        data = json.dumps({"pending": pending, "queue": queue})
        return data

    def commit(self) -> None:
        with open(self.__filepath, "w+t") as file:
            file.write(self.__serialize())
        txtracker_log.debug(f"Updated transaction cache file {self.__filepath}")

    def restore(self) -> None:
        # read
        if not self.__filepath.exists():
            return
        with open(self.__filepath, "r+t") as file:
            data = file.read()
        try:
            data = json.loads(data)
        except JSONDecodeError:
            data = dict()

        # parse
        pending = data.get("pending", dict())
        queue = data.get("queue", list())

        # deserialize
        if pending is not None:
            pending = PendingTx.from_dict(pending)
        txs = [FutureTx.from_dict(tx) for tx in queue]

        # restore
        self.__pending = pending
        self.__queue = deque(txs)
        txtracker_log.debug(
            f"Loaded {len(queue)} transactions from cache file {self.__filepath}"
        )

    def track_pending(self, tx: PendingTx) -> None:
        """Track a pending transaction by its hash. Overwrites any existing pending transaction."""
        self.__pending = tx
        self.commit()
        txtracker_log.debug(f"Tacking pending transaction {tx.txhash.hex()}")

    def evolve_future(self, tx: FutureTx, txhash) -> None:
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
        self.track_pending(tx=tx)
        txtracker_log.info(f"{self.__pending.id} Queued -> Pending")

    def finalize_pending(self, receipt: TxReceipt) -> None:
        """
        Finalizes a pending transaction.
        Use polymorphism to transform the pending transaction into a finalized transaction.
        """
        if not self.pending:
            raise RuntimeError("No pending transaction to finalize")
        self.__pending.receipt = receipt
        self.__pending.__class__ = FinalizedTx
        self.finalized.add(self.__pending)
        txtracker_log.info(f"{self.__pending.id} Pending -> Finalized")
        self.clear_pending()

    def clear_pending(self) -> None:
        self.__pending = None
        self.commit()
        txtracker_log.debug(
            f"Cleared 1 pending transaction - {len(self.queue)} "
            f"queued transaction{'s' if len(self.queue) > 1 else ''} remaining"
        )

    @property
    def pending(self) -> Optional[PendingTx]:
        return self.__pending

    @property
    def queue(self) -> Deque[FutureTx]:
        return self.__queue

    def next(self) -> FutureTx:
        return self.__queue.popleft()

    def requeue(self, tx: FutureTx) -> None:
        self.__queue.append(tx)
        self.commit()
        txtracker_log.info(
            f"Re-queued transaction #{tx.id} " f"in position {len(self.__queue) + 1}"
        )

    def add(
        self,
        tx: TxParams,
        signer: Callable,
        info: Dict[str, str] = None,
    ) -> FutureTx:
        tx = FutureTx(
            id=self.__COUNTER,
            params=tx,
            info=info,
            signer=signer,
        )
        self.__queue.append(tx)
        self.__COUNTER += 1
        txtracker_log.info(
            f"Queued transaction #{tx.params['nonce']} "
            f"in broadcast queue position {len(self.__queue)}"
        )
        self.commit()
        return tx

    def __len__(self) -> int:
        return len(self.__queue)
