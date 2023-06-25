import maya
from hexbytes import HexBytes
from typing import Callable, Dict

import random

from twisted.internet import reactor, task
from web3.exceptions import TransactionNotFound

from nucypher.blockchain.eth.constants import AVERAGE_BLOCK_TIME_IN_SECONDS, NULL_ADDRESS
from nucypher.utilities.gas_strategies import EXPECTED_CONFIRMATION_TIME_IN_SECONDS
from nucypher.utilities.logging import Logger
from constant_sorrow.constants import NOT_STAKING, UNTRACKED_PENDING_TRANSACTION


class WorkTrackerBase:
    """Baseclass for handling automated transaction tracking..."""

    CLOCK = reactor
    INTERVAL_FLOOR = 60 * 15  # fifteen minutes
    INTERVAL_CEIL = 60 * 180  # three hours

    ALLOWED_DEVIATION = 0.5  # i.e., up to +50% from the expected confirmation time

    def __init__(self, worker, *args, **kwargs):

        super().__init__(*args, **kwargs)
        self.log = Logger('stake-tracker')
        self.worker = worker   # TODO: What to call the subject here?  What is a work tracker without "work"?

        self._tracking_task = task.LoopingCall(self._do_work)
        self._tracking_task.clock = self.CLOCK

        self.__pending = dict()  # TODO: Prime with pending worker transactions
        self.__requirement = None
        self.__start_time = NOT_STAKING
        self._abort_on_error = False

        self._consecutive_fails = 0

        self._configure(*args)
        self.gas_strategy = worker.application_agent.blockchain.gas_strategy

    @classmethod
    def random_interval(cls, fails=None) -> int:
        if fails is not None and fails > 0:
            return cls.INTERVAL_FLOOR
        return random.randint(cls.INTERVAL_FLOOR, cls.INTERVAL_CEIL)

    def max_confirmation_time(self) -> int:
        expected_time = EXPECTED_CONFIRMATION_TIME_IN_SECONDS[self.gas_strategy]  # FIXME: #2447
        result = expected_time * (1 + self.ALLOWED_DEVIATION)
        return result

    def stop(self) -> None:
        if self._tracking_task.running:
            self._tracking_task.stop()
            self.log.info("STOPPED WORK TRACKING")

    def start(self, commit_now: bool = True, requirement_func: Callable = None, force: bool = False) -> None:
        """
        High-level stake tracking initialization, this function aims
        to be safely called at any time - For example, it is okay to call
        this function multiple times within the same period.
        """

        if self._tracking_task.running and not force:
            return

        # Add optional confirmation requirement callable
        self.__requirement = requirement_func

        # Record the start time
        self.__start_time = maya.now()

        self.log.info(f"START WORK TRACKING (immediate action: {commit_now})")
        d = self._tracking_task.start(interval=self.random_interval(fails=self._consecutive_fails), now=commit_now)
        d.addErrback(self.handle_working_errors)

    def _crash_gracefully(self, failure=None) -> None:
        """
        A facility for crashing more gracefully in the event that
        an exception is unhandled in a different thread.
        """
        self._crashed = failure
        failure.raiseException()

    def handle_working_errors(self, *args, **kwargs) -> None:
        failure = args[0]
        if self._abort_on_error:
            self.log.critical(f'Unhandled error during node work tracking. {failure!r}',
                              failure=failure)
            self.stop()
            reactor.callFromThread(self._crash_gracefully, failure=failure)
        else:
            self.log.warn(f'Unhandled error during work tracking (#{self._consecutive_fails}): {failure.getTraceback()!r}',
                          failure=failure)

            # the effect of this is that we get one immediate retry.
            # After that, the random_interval will be honored until
            # success is achieved
            commit_now = self._consecutive_fails < 1
            self._consecutive_fails += 1
            self.start(commit_now=commit_now)

    def _should_do_work_now(self) -> bool:
        # TODO: Check for stake expiration and exit
        if self.__requirement is None:
            return True
        r = self.__requirement(self.worker)
        if not isinstance(r, bool):
            raise ValueError("'requirement' must return a boolean.")
        return r

    @property
    def pending(self) -> Dict[int, HexBytes]:
        return self.__pending.copy()

    def __commitments_tracker_is_consistent(self) -> bool:
        operator_address = self.worker.operator_address
        tx_count_pending = self.client.get_transaction_count(account=operator_address, pending=True)
        tx_count_latest = self.client.get_transaction_count(account=operator_address, pending=False)
        txs_in_mempool = tx_count_pending - tx_count_latest

        if len(self.__pending) == txs_in_mempool:
            return True  # OK!

        if txs_in_mempool > len(self.__pending):  # We're missing some pending TXs
            return False
        else:  # TODO #2429: What to do when txs_in_mempool < len(self.__pending)? What does this imply?
            return True

    def __track_pending_commitments(self) -> bool:
        # TODO: Keep a purpose-built persistent log of worker transaction history

        unmined_transactions = 0
        pending_transactions = self.pending.items()    # note: this must be performed non-mutatively
        for tx_firing_block_number, txhash in sorted(pending_transactions):
            if txhash is UNTRACKED_PENDING_TRANSACTION:
                unmined_transactions += 1
                continue

            try:
                confirmed_tx_receipt = self.client.get_transaction_receipt(transaction_hash=txhash)
            except TransactionNotFound:
                unmined_transactions += 1  # mark as unmined - Keep tracking it for now
                continue
            else:
                confirmation_block_number = confirmed_tx_receipt['blockNumber']
                confirmations = confirmation_block_number - tx_firing_block_number
                self.log.info(f'Commitment transaction {txhash.hex()[:10]} confirmed: {confirmations} confirmations')
                del self.__pending[tx_firing_block_number]

        if unmined_transactions:
            s = "s" if unmined_transactions > 1 else ""
            self.log.info(f'{unmined_transactions} pending commitment transaction{s} detected.')

        inconsistent_tracker = not self.__commitments_tracker_is_consistent()
        if inconsistent_tracker:
            # If we detect there's a mismatch between the number of internally tracked and
            # pending block transactions, create a special pending TX that accounts for this.
            # TODO: Detect if this untracked pending transaction is a commitment transaction at all.
            self.__pending[0] = UNTRACKED_PENDING_TRANSACTION
            return True

        return bool(self.__pending)

    def __fire_replacement_commitment(self, current_block_number: int, tx_firing_block_number: int) -> None:
        replacement_txhash = self._fire_commitment()  # replace
        self.__pending[current_block_number] = replacement_txhash  # track this transaction
        del self.__pending[tx_firing_block_number]  # assume our original TX is stuck

    def __handle_replacement_commitment(self, current_block_number: int) -> None:
        tx_firing_block_number, txhash = list(sorted(self.pending.items()))[0]
        if txhash is UNTRACKED_PENDING_TRANSACTION:
            # TODO: Detect if this untracked pending transaction is a commitment transaction at all.
            message = "We have an untracked pending transaction. Issuing a replacement transaction."
        else:
            # If the transaction is still not mined after a max confirmation time
            # (based on current gas strategy) issue a replacement transaction.
            wait_time_in_blocks = current_block_number - tx_firing_block_number
            wait_time_in_seconds = wait_time_in_blocks * AVERAGE_BLOCK_TIME_IN_SECONDS
            if wait_time_in_seconds < self.max_confirmation_time():
                self.log.info(f'Waiting for pending commitment transaction to be mined ({txhash.hex()}).')
                return
            else:
                message = f"We've waited for {wait_time_in_seconds}, but max time is {self.max_confirmation_time()}" \
                          f" for {self.gas_strategy} gas strategy. Issuing a replacement transaction."

        # Send a replacement transaction
        self.log.info(message)
        self.__fire_replacement_commitment(current_block_number=current_block_number,
                                           tx_firing_block_number=tx_firing_block_number)

    def __reset_tracker_state(self) -> None:
        self.__pending.clear()  # Forget the past. This is a new beginning.
        self._consecutive_fails = 0

    def _do_work(self) -> None:
        """
        Async working task for Ursula  # TODO: Split into multiple async tasks
        """
        if self._all_work_completed():
            # nothing left to do
            self.stop()
            return

        self.log.info(f"{self.__class__.__name__} is running. Advancing to next work cycle.")  # TODO: What to call the verb the subject performs?

        # Call once here, and inject later for temporal consistency
        current_block_number = self.client.block_number

        if self._prep_work_state() is False:
            return

        # Commitment tracking
        unmined_transactions = self.__track_pending_commitments()
        if unmined_transactions:
            self.log.info('Tracking pending transaction.')
            self.__handle_replacement_commitment(current_block_number=current_block_number)
            # while there are known pending transactions, remain in fast interval mode
            self._tracking_task.interval = self.INTERVAL_FLOOR
            return  # This cycle is finished.
        else:
            # Randomize the next task interval over time, within bounds.
            self._tracking_task.interval = self.random_interval(fails=self._consecutive_fails)

        # Only perform work this round if the requirements are met
        if not self._should_do_work_now():
            self.log.warn(f'COMMIT PREVENTED (callable: "{self.__requirement.__name__}") - '
                          f'Situation does not call for doing work now.')

            # TODO: Follow-up actions for failed requirements
            return

        if self._final_work_prep_before_transaction() is False:
            return

        txhash = self._fire_commitment()
        self.__pending[current_block_number] = txhash

    #  the following four methods are specific to PRE network schemes and must be implemented as below
    def _configure(self, stakes):
        """ post __init__ configuration dealing with contracts or state specific to this PRE flavor"""
        raise NotImplementedError

    def _prep_work_state(self) -> bool:
        """ configuration perfomed before transaction management in task execution """
        raise NotImplementedError

    def _final_work_prep_before_transaction(self) -> bool:
        """ configuration perfomed after transaction management in task execution right before transaction firing"""
        raise NotImplementedError()

    def _fire_commitment(self):
        """ actually fire the tranasction """
        raise NotImplementedError

    def _all_work_completed(self) -> bool:
        """allows the work tracker to indicate that its work is completed, and it can be shut down"""
        raise NotImplementedError


class WorkTracker(WorkTrackerBase):

    INTERVAL_FLOOR = 1
    INTERVAL_CEIL = 2

    def _configure(self, *args):
        self.application_agent = self.worker.application_agent
        self.client = self.application_agent.blockchain.client

    def _prep_work_state(self):
        return True

    def _final_work_prep_before_transaction(self):
        should_continue = self.worker.get_staking_provider_address() != NULL_ADDRESS
        if should_continue:
            return True
        self.log.warn('COMMIT PREVENTED - Operator is not bonded to a staking provider.')
        return False

    def _fire_commitment(self):
        """Makes an initial/replacement operator commitment transaction"""
        transacting_power = self.worker.transacting_power
        with transacting_power:
            txhash = self.worker.confirm_address(fire_and_forget=True)  # < --- blockchain WRITE
            self.log.info(f"Confirming operator address {self.worker.operator_address} with staking provider {self.worker.staking_provider_address} - TxHash: {txhash.hex()}")
            return txhash

    def _all_work_completed(self) -> bool:
        # only a one-and-done - work is no longer needed
        return not self._should_do_work_now()
