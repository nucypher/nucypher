from typing import List, Set

from eth_account.signers.local import LocalAccount
from web3.types import TxParams

from nucypher.blockchain.eth.trackers.transactions.tracker import _TransactionTracker
from nucypher.blockchain.eth.trackers.transactions.tx import (
    FinalizedTx,
    FutureTx,
    PendingTx,
)


class TransactionTracker(_TransactionTracker):
    """
    A crash-tolerant transaction manager for EVM transactions.

    The tracker is responsible for queuing, broadcasting, and
    retrying (speedup) transactions. Transactions are queued
    and broadcasted in a first-in-first-out (FIFO) order.

    Throttle: There are two rates, idle (slow scan) and work (fast scan),
    to reduce the use of network resources when there are no transactions to track.
    When a transaction is queued, the tracker switches to work mode and
    starts scanning for transaction receipts. When the queue is empty,
    the tracker switches to idle mode and scans less frequently.

    Retry Strategies: The tracker supports a generic configurable
    interface for retry strategies.

    Crash-Tolerance: Internal state is written to a file to help recover from crashes
    and restarts. Internally caches LocalAccount instances in-memory which in
    combination with disk i/o is used to recover from async task restarts.

    Futures: The tracker returns a FutureTx instance when a transaction is queued.
    The FutureTx instance can be used to track the transaction's lifecycle and
    to retrieve the transaction's receipt when it is finalized.

    Hooks: The tracker provides hooks for transaction lifecycle events.
    - on_queued: When a transaction is queued.
    - on_broadcast: When a transaction is broadcasted.
    - on_finalized: When a transaction is finalized.
    - on_capped: When a transaction capped by its retry strategy.
    - on_timeout: When a transaction times out.
    - on_reverted: When a transaction reverted.

    """

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
        self, params: TxParams, signer: LocalAccount, *args, **kwargs
    ) -> FutureTx:
        """
        Queue a new transaction for broadcast and subsequent tracking.
        Optionally provide a dictionary of additional string data
        to log during the transaction's lifecycle for identification.
        """
        if signer.address not in self.signers:
            self.signers[signer.address] = signer
        tx = self.__state.queue(_from=signer.address, params=params, *args, **kwargs)
        return tx

    def queue_transactions(
        self, params: List[TxParams], signer: LocalAccount, *args, **kwargs
    ) -> List[FutureTx]:
        """
        Queue a list of transactions for broadcast and subsequent tracking.

        Sorts incoming transactions by nonce. The tracker is tolerant
        to nonce collisions, but it's best to avoid them when possible,
        plus it's a good practice to broadcast transactions in the
        order they were originally created in by the caller.
        """
        params = sorted(params, key=lambda x: x["nonce"])

        future_txs = []
        for _params in params:
            future_txs.append(
                self.queue_transaction(signer=signer, params=_params, *args, **kwargs)
            )
        return future_txs
