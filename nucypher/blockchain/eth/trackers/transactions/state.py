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
        self.__active: Optional[PendingTx] = None
        self.finalized: Set[FinalizedTx] = set()

    def __serialize(self) -> str:
        active = self.__active.to_dict() if self.__active else dict()
        queue = [tx.to_dict() for tx in self.__queue]
        data = json.dumps({"active": active, "queue": queue})
        return data

    def commit(self) -> None:
        with open(self.__filepath, "w+t") as file:
            file.write(self.__serialize())
        txtracker_log.debug(f"[state] wrote transaction cache file {self.__filepath}")

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
        active = data.get("active", dict())
        queue = data.get("queue", list())
        final = data.get("finalized", list())

        # deserialize
        if active is not None:
            active = PendingTx.from_dict(active)
        txs = [FutureTx.from_dict(tx) for tx in queue]

        # restore
        self.__active = active
        self.__queue = deque(txs)
        self.finalized = set(final)
        txtracker_log.debug(
            f"[state] restored {len(queue)} transactions from cache file {self.__filepath}"
        )

    def __track_active(self, tx: PendingTx) -> None:
        """Update the active transaction (destructive operation)."""
        old = None
        if self.__active:
            old = self.__active.txhash
        self.__active = tx
        self.commit()
        if old:
            txtracker_log.debug(f"[state] updated active transaction {old.hex()} -> {tx.txhash.hex()}")
            return
        txtracker_log.debug(f"[state] tracked active transaction {tx.txhash.hex()}")

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
        self.__track_active(tx=tx)
        txtracker_log.info(f"[state] #atx-{self.__active.id} queued -> pending")

    def finalize_active_tx(self, receipt: TxReceipt) -> None:
        """
        Finalizes a pending transaction.
        Use polymorphism to transform the pending transaction into a finalized transaction.
        """
        if not self.__active:
            raise RuntimeError("No pending transaction to finalize")
        self.__active.receipt = receipt
        self.__active.__class__ = FinalizedTx
        self.finalized.add(self.__active)
        txtracker_log.info(f"[state] #atx-{self.__active.id} pending -> finalized")
        self.clear_active()

    def clear_active(self) -> None:
        self.__active = None
        self.commit()
        txtracker_log.debug(
            f"[state] cleared 1 pending transaction \n"
            f"[state] {len(self.waiting)} queued "
            f"transaction{'s' if len(self.waiting) != 1 else ''} remaining"
        )

    @property
    def active(self) -> Optional[PendingTx]:
        return self.__active

    @property
    def waiting(self) -> Deque[FutureTx]:
        return self.__queue

    def _pop(self) -> FutureTx:
        return self.__queue.popleft()

    def _requeue(self, tx: FutureTx) -> None:
        self.__queue.append(tx)
        self.commit()
        txtracker_log.info(
            f"[state] re-queued transaction #atx-{tx.id} "
            f"priority {len(self.__queue) + 1}"
        )

    def _queue(
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
            f"[state] queued transaction #atx-{tx.id} "
            f"priority {len(self.__queue)}"
        )
        self.commit()
        return tx

    def __len__(self) -> int:
        return len(self.__queue)
