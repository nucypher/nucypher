"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""

import random
from _pydecimal import Decimal
from typing import Callable, Dict, Union

import maya
from constant_sorrow.constants import (
    NOT_STAKING,
    UNTRACKED_PENDING_TRANSACTION
)
from eth_utils import currency
from hexbytes.main import HexBytes
from twisted.internet import reactor, task
from web3.exceptions import TransactionNotFound

from nucypher.blockchain.eth.constants import AVERAGE_BLOCK_TIME_IN_SECONDS, NULL_ADDRESS
from nucypher.types import ERC20UNits, NuNits, TuNits
from nucypher.utilities.gas_strategies import EXPECTED_CONFIRMATION_TIME_IN_SECONDS
from nucypher.utilities.logging import Logger


class ERC20:
    """
    An amount of ERC20 tokens that doesn't hurt your eyes.
    Wraps the eth_utils currency conversion methods.

    The easiest way to use ERC20, is to pass an int, Decimal, or str, and denomination string:

    Int:    t = T(100, 'T')
    Int:    t = T(15000000000000000000000, 'TuNits')

    Decimal:  t = T(Decimal('15042.445'), 'T')
    String: t = T('10002.302', 'T')

    ...or alternately...

    Decimal: t = T.from_tokens(Decimal('100.50'))
    Int: t = T.from_units(15000000000000000000000)

    Token quantity is stored internally as an int in the smallest denomination,
    and all arithmetic operations use this value.

    Using float inputs to this class to represent amounts of NU is supported but not recommended,
    as floats don't have enough precision to represent some quantities.
    """

    _symbol = None
    _denominations = {}
    _unit_name = None

    class InvalidAmount(ValueError):
        """Raised when an invalid input amount is provided"""

    class InvalidDenomination(ValueError):
        """Raised when an unknown denomination string is passed into __init__"""

    def __init__(self, value: Union[int, Decimal, str], denomination: str):
        # super().__init__()
        # Lookup Conversion
        try:
            wrapped_denomination = self._denominations[denomination]
        except KeyError:
            raise self.InvalidDenomination(f'"{denomination}"')

        # Convert or Raise
        try:
            self.__value = currency.to_wei(number=value, unit=wrapped_denomination)
        except ValueError as e:
            raise self.__class__.InvalidAmount(f"{value} is an invalid amount of tokens: {str(e)}")

    @classmethod
    def ZERO(cls) -> 'ERC20':
        return cls(0, cls._unit_name)

    @classmethod
    def from_units(cls, value: int) -> 'ERC20':
        return cls(value, denomination=cls._unit_name)

    @classmethod
    def from_tokens(cls, value: Union[int, Decimal, str]) -> 'ERC20':
        return cls(value, denomination=cls._symbol)

    def to_tokens(self) -> Decimal:
        """Returns a decimal value of NU"""
        return currency.from_wei(self.__value, unit='ether')

    def to_units(self) -> ERC20UNits:
        """Returns an int value in the Unit class for this token"""
        return self.__class__._unit(self.__value)

    def __eq__(self, other) -> bool:
        return int(self) == int(other)

    def __bool__(self) -> bool:
        if self.__value == 0:
            return False
        else:
            return True

    def __radd__(self, other) -> 'ERC20':
        return self.__class__(int(self) + int(other), self._unit_name)

    def __add__(self, other) -> 'ERC20':
        return self.__class__(int(self) + int(other), self._unit_name)

    def __sub__(self, other) -> 'ERC20':
        return self.__class__(int(self) - int(other), self._unit_name)

    def __rmul__(self, other) -> 'ERC20':
        return self.__class__(int(self) * int(other), self._unit_name)

    def __mul__(self, other) -> 'ERC20':
        return self.__class__(int(self) * int(other), self._unit_name)

    def __floordiv__(self, other) -> 'ERC20':
        return self.__class__(int(self) // int(other), self._unit_name)

    def __gt__(self, other) -> bool:
        return int(self) > int(other)

    def __ge__(self, other) -> bool:
        return int(self) >= int(other)

    def __lt__(self, other) -> bool:
        return int(self) < int(other)

    def __le__(self, other) -> bool:
        return int(self) <= int(other)

    def __int__(self) -> int:
        """Cast to smallest denomination"""
        return int(self.to_units())

    def __round__(self, decimals: int = 0):
        return self.__class__.from_tokens(round(self.to_tokens(), decimals))

    def __repr__(self) -> str:
        r = f'{self._symbol}(value={str(self.__value)})'
        return r

    def __str__(self) -> str:
        return f'{str(self.to_tokens())} {self._symbol}'


class NU(ERC20):
    _symbol = 'NU'
    _denominations = {'NuNit': 'wei', 'NU': 'ether'}
    _unit_name = 'NuNit'
    _unit = NuNits


class TToken(ERC20):
    _symbol = 'T'
    _denominations = {'TuNit': 'wei', 'T': 'ether'}
    _unit_name = 'TuNit'
    _unit = TuNits


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
        self.__uptime_period = NOT_STAKING
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
            self.log.info(f"STOPPED WORK TRACKING")

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

        # Record the start time and period
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
            raise ValueError(f"'requirement' must return a boolean.")
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
            message = f"We have an untracked pending transaction. Issuing a replacement transaction."
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
        """ allows the work tracker to indicate that its work is completed and it can be shut down """
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
