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

from _pydecimal import Decimal
from collections import UserList
from enum import Enum

import maya
from constant_sorrow.constants import (EMPTY_STAKING_SLOT, NEW_STAKE, NOT_STAKING, NO_STAKING_RECEIPT,
                                       UNKNOWN_WORKER_STATUS)
from eth_utils import currency, is_checksum_address
from twisted.internet import reactor, task
from twisted.logger import Logger
from typing import Callable, Dict, Tuple, Union

from nucypher.blockchain.eth.agents import ContractAgency, StakingEscrowAgent
from nucypher.blockchain.eth.decorators import validate_checksum_address
from nucypher.blockchain.eth.registry import BaseContractRegistry
from nucypher.blockchain.eth.utils import datetime_at_period
from nucypher.types import SubStakeInfo, NuNits, StakerInfo, Period


class NU:
    """
    An amount of NuCypher tokens that doesn't hurt your eyes.
    Wraps the eth_utils currency conversion methods.

    The easiest way to use NU, is to pass an int, float, or str, and denomination string:

    Int:    nu = NU(100, 'NU')
    Int:    nu_wei = NU(15000000000000000000000, 'NuNit')

    Float:  nu = NU(15042.445, 'NU')
    String: nu = NU('10002.302', 'NU')

    ...or alternately...

    Float: nu = NU.from_tokens(100.50)
    Int: nu_wei = NU.from_nu_wei(15000000000000000000000)

    Token quantity is stored internally as an int in the smallest denomination,
    and all arithmetic operations use this value.
    """

    __symbol = 'NU'
    __denominations = {'NuNit': 'wei', 'NU': 'ether'}

    class InvalidAmount(ValueError):
        """Raised when an invalid input amount is provided"""

    class InvalidDenomination(ValueError):
        """Raised when an unknown denomination string is passed into __init__"""

    def __init__(self, value: Union[int, float, str], denomination: str):

        # Lookup Conversion
        try:
            wrapped_denomination = self.__denominations[denomination]
        except KeyError:
            raise self.InvalidDenomination(f'"{denomination}"')

        # Convert or Raise
        try:
            self.__value = currency.to_wei(number=value, unit=wrapped_denomination)
        except ValueError as e:
            raise NU.InvalidAmount(f"{value} is an invalid amount of tokens: {str(e)}")

    @classmethod
    def ZERO(cls) -> 'NU':
        return cls(0, 'NuNit')

    @classmethod
    def from_nunits(cls, value: int) -> 'NU':
        return cls(value, denomination='NuNit')

    @classmethod
    def from_tokens(cls, value: Union[int, float, str]) -> 'NU':
        return cls(value, denomination='NU')

    def to_tokens(self) -> Decimal:
        """Returns a decimal value of NU"""
        return currency.from_wei(self.__value, unit='ether')

    def to_nunits(self) -> NuNits:
        """Returns an int value in NuNit"""
        return NuNits(self.__value)

    def __eq__(self, other) -> bool:
        return int(self) == int(other)

    def __bool__(self) -> bool:
        if self.__value == 0:
            return False
        else:
            return True

    def __radd__(self, other) -> 'NU':
        return NU(int(self) + int(other), 'NuNit')

    def __add__(self, other) -> 'NU':
        return NU(int(self) + int(other), 'NuNit')

    def __sub__(self, other) -> 'NU':
        return NU(int(self) - int(other), 'NuNit')

    def __rmul__(self, other) -> 'NU':
        return NU(int(self) * int(other), 'NuNit')

    def __mul__(self, other) -> 'NU':
        return NU(int(self) * int(other), 'NuNit')

    def __floordiv__(self, other) -> 'NU':
        return NU(int(self) // int(other), 'NuNit')

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
        return int(self.to_nunits())

    def __round__(self, decimals: int = 0):
        return NU.from_tokens(round(self.to_tokens(), decimals))

    def __repr__(self) -> str:
        r = f'{self.__symbol}(value={str(self.__value)})'
        return r

    def __str__(self) -> str:
        return f'{str(self.to_tokens())} {self.__symbol}'


class Stake:
    """
    A quantity of tokens and staking duration in periods for one stake for one staker.
    """

    class StakingError(Exception):
        """Raised when a staking operation cannot be executed due to failure."""

    class Status(Enum):
        """
        Sub-stake status.
        """
        INACTIVE = 1   # Unlocked inactive
        UNLOCKED = 2   # Unlocked active
        LOCKED = 3     # Locked but not editable
        EDITABLE = 4   # Editable
        DIVISIBLE = 5  # Editable and divisible

        def is_child(self, other: 'Status') -> bool:
            if other == self.INACTIVE:
                return self == self.INACTIVE
            elif other == self.UNLOCKED:
                return self.value <= self.UNLOCKED.value
            else:
                return self.value >= other.value

    @validate_checksum_address
    def __init__(self,
                 staking_agent: StakingEscrowAgent,
                 checksum_address: str,
                 value: NU,
                 first_locked_period: int,
                 final_locked_period: int,
                 index: int,
                 economics):

        self.log = Logger(f'stake-{checksum_address}-{index}')

        # Ownership
        self.staker_address = checksum_address

        # Stake Metadata
        self.index = index
        self.value = value

        # Periods
        self.first_locked_period = first_locked_period

        # TODO: #1502 - Move Me Brightly - Docs
        # After this period has passes, workers can go offline, if this is the only stake.
        # This is the last period that can be committed for this stake.
        # Meaning, It must be committed in the previous period,
        # and no commitment can be made in this period for this stake.
        self.final_locked_period = final_locked_period

        # Blockchain
        self.staking_agent = staking_agent

        # Economics
        self.economics = economics
        self.minimum_nu = NU(int(self.economics.minimum_allowed_locked), 'NuNit')
        self.maximum_nu = NU(int(self.economics.maximum_allowed_locked), 'NuNit')

        # Time
        self.start_datetime = datetime_at_period(period=first_locked_period,
                                                 seconds_per_period=self.economics.seconds_per_period,
                                                 start_of_period=True)
        self.unlock_datetime = datetime_at_period(period=final_locked_period + 1,
                                                  seconds_per_period=self.economics.seconds_per_period,
                                                  start_of_period=True)
        self._status = None

    def __repr__(self) -> str:
        r = f'Stake(' \
            f'index={self.index}, ' \
            f'value={self.value}, ' \
            f'end_period={self.final_locked_period}, ' \
            f'address={self.staker_address[:6]}, ' \
            f'escrow={self.staking_agent.contract_address[:6]}' \
            f')'
        return r

    def __eq__(self, other: 'Stake') -> bool:
        this_stake = (self.index,
                      self.value,
                      self.first_locked_period,
                      self.final_locked_period,
                      self.staker_address,
                      self.staking_agent.contract_address)
        try:
            that_stake = (other.index,
                          other.value,
                          other.first_locked_period,
                          other.final_locked_period,
                          other.staker_address,
                          other.staking_agent.contract_address)
        except AttributeError:
            return False

        return this_stake == that_stake

    @property
    def address_index_ordering_key(self):
        """To be used as a lexicographical order key for Stakes based on the tuple (staker_address, index)."""
        return self.staker_address, self.index

    #
    # Metadata
    #

    def status(self, staker_info: StakerInfo = None, current_period: Period = None) -> Status:
        """
        Returns status of sub-stake:
        UNLOCKED - final period in the past
        INACTIVE - UNLOCKED and sub-stake will not be included in any future calculations
        LOCKED - sub-stake is still locked and final period is current period
        EDITABLE - LOCKED and final period greater than current
        DIVISIBLE - EDITABLE and locked value is greater than two times the minimum allowed locked
        """

        if self._status:
            return self._status

        staker_info = staker_info or self.staking_agent.get_staker_info(self.staker_address) # TODO related to #1514
        current_period = current_period or self.staking_agent.get_current_period()  # TODO #1514 this is online only.

        if self.final_locked_period < current_period:
            if (staker_info.current_committed_period == 0 or
                staker_info.current_committed_period > self.final_locked_period) and \
                (staker_info.next_committed_period == 0 or
                 staker_info.next_committed_period > self.final_locked_period):
                self._status = Stake.Status.INACTIVE
            else:
                self._status = Stake.Status.UNLOCKED
        elif self.final_locked_period == current_period:
            self._status = Stake.Status.LOCKED
        elif self.value < 2 * self.economics.minimum_allowed_locked:
            self._status = Stake.Status.EDITABLE
        else:
            self._status = Stake.Status.DIVISIBLE

        return self._status

    @classmethod
    @validate_checksum_address
    def from_stake_info(cls,
                        checksum_address: str,
                        index: int,
                        stake_info: SubStakeInfo,
                        economics,
                        *args, **kwargs
                        ) -> 'Stake':

        """Reads staking values as they exist on the blockchain"""

        instance = cls(checksum_address=checksum_address,
                       index=index,
                       first_locked_period=stake_info.first_period,
                       final_locked_period=stake_info.last_period,
                       value=NU(stake_info.locked_value, 'NuNit'),
                       economics=economics,
                       *args, **kwargs)

        return instance

    def to_stake_info(self) -> SubStakeInfo:
        """Returns a tuple representing the blockchain record of a stake"""
        return SubStakeInfo(self.first_locked_period, self.final_locked_period, self.value.to_nunits())

    #
    # Duration
    #

    @property
    def duration(self) -> int:
        """Return stake duration in periods"""
        result = (self.final_locked_period - self.first_locked_period) + 1
        return result

    @property
    def periods_remaining(self) -> int:
        """Returns the number of periods remaining in the stake from now."""
        current_period = self.staking_agent.get_current_period()
        return self.final_locked_period - current_period + 1

    def time_remaining(self, slang: bool = False) -> Union[int, str]:
        """
        Returns the time delta remaining in the stake from now.
        This method is designed for *UI* usage.
        """
        if slang:
            result = self.unlock_datetime.slang_date()
        else:
            # TODO - #1509 EthAgent?
            blocktime_epoch = self.staking_agent.blockchain.client.get_blocktime()
            delta = self.unlock_datetime.epoch - blocktime_epoch
            result = delta
        return result

    def describe(self) -> Dict[str, str]:
        start_datetime = self.start_datetime.local_datetime().strftime("%b %d %Y")
        end_datetime = self.unlock_datetime.local_datetime().strftime("%b %d %Y")

        data = dict(index=self.index,
                    value=str(self.value),
                    remaining=self.periods_remaining,
                    enactment=start_datetime,
                    last_period=end_datetime)
        return data

    #
    # Blockchain
    #

    def sync(self) -> None:
        """Update this stakes attributes with on-chain values."""

        # Read from blockchain
        stake_info = self.staking_agent.get_substake_info(staker_address=self.staker_address,
                                                          stake_index=self.index)  # < -- Read from blockchain

        if not self.first_locked_period == stake_info.first_period:
            raise self.StakingError("Inconsistent staking cache.  Make sure your node is synced and try again.")

        # Mutate the instance with the on-chain values
        self.final_locked_period = stake_info.last_period
        self.value = NU.from_nunits(stake_info.locked_value)
        self._status = None

    @classmethod
    def initialize_stake(cls,
                         staking_agent,
                         economics,
                         checksum_address: str,
                         amount: NU,
                         lock_periods: int) -> 'Stake':

        # Value
        amount = NU(int(amount), 'NuNit')

        # Duration
        current_period = staking_agent.get_current_period()
        final_locked_period = current_period + lock_periods

        stake = cls(checksum_address=checksum_address,
                    first_locked_period=current_period + 1,
                    final_locked_period=final_locked_period,
                    value=amount,
                    index=NEW_STAKE,
                    staking_agent=staking_agent,
                    economics=economics)

        # Validate
        validate_value(stake)
        validate_duration(stake)
        validate_max_value(stake)

        return stake


def validate_value(stake: Stake) -> None:
    """Validate a single staking value against pre-defined requirements"""
    if stake.minimum_nu > stake.value:
        raise Stake.StakingError(f'Stake amount of {stake.value} is too low; must be at least {stake.minimum_nu}')


def validate_duration(stake: Stake) -> None:
    """Validate a single staking lock-time against pre-defined requirements"""
    if stake.economics.minimum_locked_periods > stake.duration:
        raise Stake.StakingError(
            'Stake duration of {duration} periods is too short; must be at least {minimum} periods.'
            .format(minimum=stake.economics.minimum_locked_periods, duration=stake.duration))


def validate_divide(stake: Stake, target_value: NU, additional_periods: int = None) -> None:
    """
    Validates possibility to divide specified stake into two stakes using provided parameters.
    """

    # Ensure selected stake is active
    status = stake.status()
    if not status.is_child(Stake.Status.DIVISIBLE):
        raise Stake.StakingError(f'Cannot divide an non-divisible stake. '
                                 f'Selected stake expired {stake.unlock_datetime} and has value {stake.value}.')

    if target_value >= stake.value:
        raise Stake.StakingError(f"Cannot divide stake; Target value ({target_value}) must be less "
                                 f"than the existing stake value {stake.value}.")

    #
    # Generate SubStakes
    #

    # Modified Original Stake
    remaining_stake_value = stake.value - target_value
    modified_stake = Stake(checksum_address=stake.staker_address,
                           index=stake.index,
                           first_locked_period=stake.first_locked_period,
                           final_locked_period=stake.final_locked_period,
                           value=remaining_stake_value,
                           staking_agent=stake.staking_agent,
                           economics=stake.economics)

    # New Derived Stake
    end_period = stake.final_locked_period + additional_periods
    new_stake = Stake(checksum_address=stake.staker_address,
                      first_locked_period=stake.first_locked_period,
                      final_locked_period=end_period,
                      value=target_value,
                      index=NEW_STAKE,
                      staking_agent=stake.staking_agent,
                      economics=stake.economics)

    #
    # Validate
    #

    # Ensure both halves are for valid amounts
    validate_value(modified_stake)
    validate_value(new_stake)


def validate_max_value(stake: Stake, amount: NU = None) -> None:
    amount = amount or stake.value

    # Ensure the new stake will not exceed the staking limit
    locked_tokens = stake.staking_agent.get_locked_tokens(staker_address=stake.staker_address, periods=1)
    if (locked_tokens + amount) > stake.economics.maximum_allowed_locked:
        raise Stake.StakingError(f"Cannot initialize stake - "
                                 f"Maximum stake value exceeded for {stake.staker_address} "
                                 f"with a target value of {amount}.")


def validate_prolong(stake: Stake, additional_periods: int) -> None:
    status = stake.status()
    if not status.is_child(Stake.Status.EDITABLE):
        raise Stake.StakingError(f'Cannot prolong a non-editable stake. '
                                 f'Selected stake expired {stake.unlock_datetime}.')
    new_duration = stake.periods_remaining + additional_periods - 1
    if new_duration < stake.economics.minimum_locked_periods:
        raise stake.StakingError(f'Sub-stake duration of {new_duration} periods after prolongation'
                                 f'is shorter than minimum allowed duration '
                                 f'of {stake.economics.minimum_locked_periods} periods.')


def validate_increase(stake: Stake, amount: NU) -> None:
    status = stake.status()
    if not status.is_child(Stake.Status.EDITABLE):
        raise Stake.StakingError(f'Cannot increase a non-editable stake. '
                                 f'Selected stake expired {stake.unlock_datetime}.')

    validate_max_value(stake=stake, amount=amount)


class WorkTracker:

    CLOCK = reactor
    REFRESH_RATE = 60 * 15  # Fifteen minutes

    def __init__(self,
                 worker,
                 refresh_rate: int = None,
                 *args, **kwargs):

        super().__init__(*args, **kwargs)
        self.log = Logger('stake-tracker')
        self.worker = worker
        self.staking_agent = self.worker.staking_agent

        self._refresh_rate = refresh_rate or self.REFRESH_RATE
        self._tracking_task = task.LoopingCall(self._do_work)
        self._tracking_task.clock = self.CLOCK

        self.__requirement = None
        self.__current_period = None
        self.__start_time = NOT_STAKING
        self.__uptime_period = NOT_STAKING
        self._abort_on_error = True

    @property
    def current_period(self):
        return self.__current_period

    def stop(self) -> None:
        if self._tracking_task.running:
            self._tracking_task.stop()
            self.log.info(f"STOPPED WORK TRACKING")

    def start(self, act_now: bool = True, requirement_func: Callable = None, force: bool = False) -> None:
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
        self.__uptime_period = self.staking_agent.get_current_period()
        self.__current_period = self.__uptime_period

        self.log.info(f"START WORK TRACKING")
        d = self._tracking_task.start(interval=self._refresh_rate, now=act_now)
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
            self.log.critical('Unhandled error during node work tracking. {failure!r}',
                              failure=failure)
            reactor.callFromThread(self._crash_gracefully, failure=failure)
        else:
            self.log.warn('Unhandled error during work tracking: {failure.getTraceback()!r}',
                          failure=failure)

    def __check_work_requirement(self) -> bool:
        # TODO: Check for stake expiration and exit
        if self.__requirement is None:
            return True
        try:
            r = self.__requirement()
            if not isinstance(r, bool):
                raise ValueError(f"'requirement' must return a boolean.")
        except TypeError:
            raise ValueError(f"'requirement' must be a callable.")
        return r

    def _do_work(self) -> None:
        # TODO: #1515 Shut down at end of terminal stake

        # Update on-chain status
        self.log.info(f"Checking for new period. Current period is {self.__current_period}")
        onchain_period = self.staking_agent.get_current_period()  # < -- Read from contract
        if self.current_period != onchain_period:
            self.__current_period = onchain_period
            # self.worker.stakes.refresh()  # TODO: #1517 Track stakes for fast access to terminal period.

        # Measure working interval
        interval = onchain_period - self.worker.last_committed_period
        if interval < 0:
            return  # No need to commit to this period.  Save the gas.
        if interval > 0:
            # TODO: #1516 Follow-up actions for downtime
            self.log.warn(f"MISSED COMMITMENTS - {interval} missed staking commitments detected.")

        # Only perform work this round if the requirements are met
        if not self.__check_work_requirement():
            self.log.warn(f'COMMIT PREVENTED (callable: "{self.__requirement.__name__}") - '
                          f'There are unmet commit requirements.')
            # TODO: Follow-up actions for downtime
            return

        # Make a Commitment
        self.log.info("Made a commitment to period {}".format(self.current_period))
        transacting_power = self.worker.transacting_power
        with transacting_power:
            self.worker.commit_to_next_period()  # < --- blockchain WRITE


class StakeList(UserList):

    @validate_checksum_address
    def __init__(self,
                 registry: BaseContractRegistry,
                 checksum_address: str = None,
                 *args, **kwargs):

        super().__init__(*args, **kwargs)
        self.log = Logger('stake-tracker')
        self.staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=registry)
        from nucypher.blockchain.economics import EconomicsFactory
        self.economics = EconomicsFactory.get_economics(registry=registry)

        self.__initial_period = NOT_STAKING
        self.__terminal_period = NOT_STAKING

        # "load-in":  Read on-chain stakes
        # Allow stake tracker to be initialized as an empty collection.
        if checksum_address:
            if not is_checksum_address(checksum_address):
                raise ValueError(f'{checksum_address} is not a valid EIP-55 checksum address')
        self.checksum_address = checksum_address
        self.__updated = None

    @property
    def updated(self) -> maya.MayaDT:
        return self.__updated

    @property
    def initial_period(self) -> int:
        return self.__initial_period

    @property
    def terminal_period(self) -> int:
        return self.__terminal_period

    @validate_checksum_address
    def refresh(self) -> None:
        """Public staking cache invalidation method"""
        return self.__read_stakes()

    def __read_stakes(self) -> None:
        """Rewrite the local staking cache by reading on-chain stakes"""

        existing_records = len(self)

        # Candidate replacement cache values
        current_period = self.staking_agent.get_current_period()
        onchain_stakes, initial_period, terminal_period = list(), 0, current_period

        # Read from blockchain
        stakes_reader = self.staking_agent.get_all_stakes(staker_address=self.checksum_address)
        for onchain_index, stake_info in enumerate(stakes_reader):

            if not stake_info:
                onchain_stake = EMPTY_STAKING_SLOT

            else:
                onchain_stake = Stake.from_stake_info(checksum_address=self.checksum_address,
                                                      stake_info=stake_info,
                                                      staking_agent=self.staking_agent,
                                                      index=onchain_index,
                                                      economics=self.economics)

                # rack the earliest terminal period
                if onchain_stake.first_locked_period:
                    if onchain_stake.first_locked_period < initial_period:
                        initial_period = onchain_stake.first_locked_period

                # rack the latest terminal period
                if onchain_stake.final_locked_period > terminal_period:
                    terminal_period = onchain_stake.final_locked_period

            # Store the replacement stake
            onchain_stakes.append(onchain_stake)

        # Commit the new stake and terminal values to the cache
        self.data = onchain_stakes
        if onchain_stakes:
            self.__initial_period = initial_period
            self.__terminal_period = terminal_period
            changed_records = abs(existing_records - len(onchain_stakes))
            self.log.debug(f"Updated {changed_records} local staking cache entries.")

        # Record most recent cache update
        self.__updated = maya.now()
