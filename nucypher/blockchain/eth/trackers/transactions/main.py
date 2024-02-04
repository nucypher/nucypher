from typing import List, Set, Dict, Optional, Callable

from web3.types import TxParams

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
        """Return a list of queued transactions."""
        return list(self.__state.waiting)

    @property
    def pending(self) -> PendingTx:
        """Return the active transaction if there is one."""
        return self.__state.active or None

    @property
    def finalized(self) -> Set[FinalizedTx]:
        """Return a set of finalized transactions."""
        return self.__state.finalized

    def queue_transaction(
            self,
            params: TxParams,
            info: Optional[Dict[str, str]] = None,
            on_finalized: Optional[Callable] = None,
            on_capped: Optional[Callable] = None,
            on_timeout: Optional[Callable] = None
            ) -> FutureTx:
        """
        Queue a new transaction for broadcast and subsequent tracking.
        Optionally provide a dictionary of additional string data
        to log during the transaction's lifecycle for identification.
        """
        tx = self.__state._queue(
            params=params,
            info=info,
            on_timeout=on_timeout,
            on_capped=on_capped,
            on_finalized=on_finalized,
        )
        return tx

    def queue_transactions(
            self,
            params: List[TxParams],
            info: Optional[Dict[str, str]] = None,
            on_finalized: Optional[Callable] = None,
            on_capped: Optional[Callable] = None,
            on_timeout: Optional[Callable] = None
    ) -> List[FutureTx]:
        """Queue a list of transactions for broadcast and subsequent tracking."""
        future_txs = []
        for _params in params:
            future_txs.append(
                self.queue_transaction(
                    params=_params,
                    info=info,
                    on_timeout=on_timeout,
                    on_capped=on_capped,
                    on_finalized=on_finalized,
                )
            )
        return future_txs
