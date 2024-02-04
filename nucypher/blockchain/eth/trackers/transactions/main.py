from typing import List, Set

from nucypher.blockchain.eth.trackers.transactions.tracker import _TransactionTracker
from nucypher.blockchain.eth.trackers.transactions.tx import (
    FinalizedTx,
    FutureTx,
    PendingTx,
)


class TransactionTracker(_TransactionTracker):
    """Public interface for async transaction tracking."""

    @property
    def queued(self) -> List[FutureTx]:
        return list(self.__state.waiting)

    @property
    def pending(self) -> PendingTx:
        return self.__state.active or None

    @property
    def finalized(self) -> Set[FinalizedTx]:
        return self.__state.finalized

    def queue_transaction(self, *args, **kwargs) -> FutureTx:
        tx = self.__state._queue(*args, **kwargs)
        return tx

    def start(self, now: bool = True) -> None:
        # self.__state.restore()
        # self.log.info("Resuming transaction tracker")
        self.log.info("Starting transaction tracker")
        return super().start(now=now)
