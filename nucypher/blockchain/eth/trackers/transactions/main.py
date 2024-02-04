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
        return list(self.__state.queue)

    @property
    def pending(self) -> PendingTx:
        return self.__state.pending or None

    @property
    def finalized(self) -> Set[FinalizedTx]:
        return self.__state.finalized

    def queue_transaction(self, *args, **kwargs) -> FutureTx:
        tx = self.__state.add(*args, **kwargs)
        return tx

    def start(self, now: bool = False) -> None:
        # self.__state.restore()
        self.log.info("Starting transaction tracker")
        return super().start(now=now)
