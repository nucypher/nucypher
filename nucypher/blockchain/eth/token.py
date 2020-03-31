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
from typing import Dict
from typing import Union, Tuple, Callable

import maya
from constant_sorrow.constants import (
    NEW_STAKE,
    NO_STAKING_RECEIPT,
    NOT_STAKING,
    EMPTY_STAKING_SLOT,
    UNKNOWN_WORKER_STATUS
)
from eth_utils import currency, is_checksum_address
from twisted.internet import task, reactor
from twisted.logger import Logger

from nucypher.blockchain.eth.agents import StakingEscrowAgent, ContractAgency
from nucypher.blockchain.eth.decorators import validate_checksum_address
from nucypher.blockchain.eth.registry import BaseContractRegistry
from nucypher.blockchain.eth.utils import datetime_at_period


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

    def to_nunits(self) -> int:
        """Returns an int value in NuNit"""
        return int(self.__value)

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

    @validate_checksum_address
    def __init__(self,
                 staking_agent: StakingEscrowAgent,
                 checksum_address: str,
                 value: NU,
                 first_locked_period: int,
                 final_locked_period: int,
                 index: int,
                 economics,
                 validate_now: bool = True):

        self.log = Logger(f'stake-{checksum_address}-{index}')

        # Ownership
        self.staker_address = checksum_address
        self.worker_address = UNKNOWN_WORKER_STATUS

        # Stake Metadata
        self.index = index
        self.value = value

        # Periods
        self.first_locked_period = first_locked_period

        # TODO: #1502 - Move Me Brightly - Docs
        # After this period has passes, workers can go offline, if this is the only stake.
        # This is the last period that can be confirmed for this stake.
        # Meaning, It must be confirmed in the previous period,
        # and no confirmation can be performed in this period for this stake.
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

        if validate_now:
            self.validate()

        self.receipt = NO_STAKING_RECEIPT

    def __repr__(self) -> str:
        r = f'Stake(index={self.index}, value={self.value}, end_period={self.final_locked_period})'
        return r

    @property
    def address_index_ordering_key(self):
        """To be used as a lexicographical order key for Stakes based on the tuple (staker_address, index)."""
        return self.staker_address, self.index

    #
    # Metadata
    #

    @property
    def is_expired(self) -> bool:
        current_period = self.staking_agent.get_current_period()  # TODO #1514 this is online only.
        return bool(current_period > self.final_locked_period)

    @property
    def is_active(self) -> bool:
        return not self.is_expired

    @classmethod
    @validate_checksum_address
    def from_stake_info(cls,
                        checksum_address: str,
                        index: int,
                        stake_info: Tuple[int, int, int],
                        economics,
                        *args, **kwargs
                        ) -> 'Stake':

        """Reads staking values as they exist on the blockchain"""
        first_locked_period, final_locked_period, value = stake_info

        instance = cls(checksum_address=checksum_address,
                       index=index,
                       first_locked_period=first_locked_period,
                       final_locked_period=final_locked_period,
                       value=NU(value, 'NuNit'),
                       economics=economics,
                       validate_now=False,
                       *args, **kwargs)

        instance.worker_address = instance.staking_agent.get_worker_from_staker(staker_address=checksum_address)
        return instance

    def to_stake_info(self) -> Tuple[int, int, int]:
        """Returns a tuple representing the blockchain record of a stake"""
        return self.first_locked_period, self.final_locked_period, int(self.value)

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
            blocktime_epoch = self.staking_agent.blockchain.client.w3.eth.getBlock('latest').timestamp
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
    # Validation
    #

    @staticmethod
    def __handle_validation_failure(rulebook: Tuple[Tuple[bool, str], ...]) -> bool:
        """Validate a staking rulebook"""
        for rule, failure_message in rulebook:
            if not rule:
                raise ValueError(failure_message)
        return True

    def validate(self) -> bool:
        return all((self.validate_value(), self.validate_duration()))

    def validate_value(self, raise_on_fail: bool = True) -> Union[bool, Tuple[Tuple[bool, str]]]:
        """Validate a single staking value against pre-defined requirements"""

        rulebook = (
            (self.minimum_nu <= self.value,
             f'Stake amount too low; ({self.value}) must be at least {self.minimum_nu}'),

            # Add any additional rules here following the above format...
        )

        if raise_on_fail is True:
            self.__handle_validation_failure(rulebook=rulebook)
        return all(rulebook)

    def validate_duration(self, raise_on_fail=True) -> Union[bool, Tuple[Tuple[bool, str]]]:
        """Validate a single staking lock-time against pre-defined requirements"""

        rulebook = (

            (self.economics.minimum_locked_periods <= self.duration,
             'Stake duration of ({duration}) periods is too short; must be at least {minimum} periods.'
             .format(minimum=self.economics.minimum_locked_periods, duration=self.duration)),

        )

        if raise_on_fail is True:
            self.__handle_validation_failure(rulebook=rulebook)
        return all(rulebook)

    #
    # Blockchain
    #

    def sync(self) -> None:
        """Update this stakes attributes with on-chain values."""

        # Read from blockchain
        stake_info = self.staking_agent.get_substake_info(staker_address=self.staker_address,
                                                          stake_index=self.index)  # < -- Read from blockchain

        first_period, last_period, locked_value = stake_info
        if not self.first_locked_period == first_period:
            raise self.StakingError("Inconsistent staking cache.  Make sure your node is synced and try again.")

        # Mutate the instance with the on-chain values
        self.final_locked_period = last_period
        self.value = NU.from_nunits(locked_value)
        self.worker_address = self.staking_agent.get_worker_from_staker(staker_address=self.staker_address)

    def divide(self, target_value: NU, additional_periods: int = None) -> Tuple['Stake', 'Stake']:
        """
        Modifies the unlocking schedule and value of already locked tokens.

        This actor requires that is_me is True, and that the expiration datetime is after the existing
        locking schedule of this staker, or an exception will be raised.
       """

        # Read on-chain stake
        self.sync()

        # Ensure selected stake is active
        if self.is_expired:
            raise self.StakingError(f'Cannot divide an expired stake. Selected stake expired {self.unlock_datetime}.')

        if target_value >= self.value:
            raise self.StakingError(f"Cannot divide stake; Target value ({target_value}) must be less "
                                    f"than the existing stake value {self.value}.")

        #
        # Generate SubStakes
        #

        # Modified Original Stake
        remaining_stake_value = self.value - target_value
        modified_stake = Stake(checksum_address=self.staker_address,
                               index=self.index,
                               first_locked_period=self.first_locked_period,
                               final_locked_period=self.final_locked_period,
                               value=remaining_stake_value,
                               staking_agent=self.staking_agent,
                               economics=self.economics,
                               validate_now=False)

        # New Derived Stake
        end_period = self.final_locked_period + additional_periods
        new_stake = Stake(checksum_address=self.staker_address,
                          first_locked_period=self.first_locked_period,
                          final_locked_period=end_period,
                          value=target_value,
                          index=NEW_STAKE,
                          staking_agent=self.staking_agent,
                          economics=self.economics,
                          validate_now=False)

        #
        # Validate
        #

        # Ensure both halves are for valid amounts
        modified_stake.validate_value()
        new_stake.validate_value()

        #
        # Transmit
        #

        # TODO: Entrypoint for PreallocationEscrowAgent here - #1497
        # Transmit the stake division transaction
        receipt = self.staking_agent.divide_stake(staker_address=self.staker_address,
                                                  stake_index=self.index,
                                                  target_value=int(target_value),
                                                  periods=additional_periods)
        new_stake.receipt = receipt

        return modified_stake, new_stake

    @classmethod
    def initialize_stake(cls, staker, amount: NU, lock_periods: int) -> 'Stake':

        # Value
        amount = NU(int(amount), 'NuNit')

        # Duration
        current_period = staker.staking_agent.get_current_period()
        final_locked_period = current_period + lock_periods

        stake = Stake(checksum_address=staker.checksum_address,
                      first_locked_period=current_period + 1,
                      final_locked_period=final_locked_period,
                      value=amount,
                      index=NEW_STAKE,
                      staking_agent=staker.staking_agent,
                      economics=staker.economics)

        # Validate
        stake.validate_value()
        stake.validate_duration()

        # Create stake on-chain
        stake.receipt = staker.deposit(amount=int(amount), lock_periods=lock_periods)

        # Log and return Stake instance
        log = Logger(f'stake-{staker.checksum_address}-creation')
        log.info(f"{staker.checksum_address} Initialized new stake: {amount} tokens for {lock_periods} periods")
        return stake

    def prolong(self, additional_periods: int):
        self.sync()
        if self.is_expired:
            raise self.StakingError(f'Cannot divide an expired stake. Selected stake expired {self.unlock_datetime}.')
        receipt = self.staking_agent.prolong_stake(staker_address=self.staker_address,
                                                   stake_index=self.index,
                                                   periods=additional_periods)
        return receipt


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

    def start(self, act_now: bool = False, requirement_func: Callable = None, force: bool = False) -> None:
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

        d = self._tracking_task.start(interval=self._refresh_rate)
        d.addErrback(self.handle_working_errors)
        self.log.info(f"STARTED WORK TRACKING")

        if act_now:
            self._do_work()

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
            self.log.critical(f"Unhandled error during node work tracking. {failure}")
            reactor.callFromThread(self._crash_gracefully, failure=failure)
        else:
            self.log.warn(f"Unhandled error during work tracking: {failure.getTraceback()}")

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
        interval = onchain_period - self.worker.last_active_period
        if interval < 0:
            return  # No need to confirm this period.  Save the gas.
        if interval > 0:
            # TODO: #1516 Follow-up actions for downtime
            self.log.warn(f"MISSED CONFIRMATIONS - {interval} missed staking confirmations detected.")

        # Only perform work this round if the requirements are met
        if not self.__check_work_requirement():
            self.log.warn(f'CONFIRMATION PREVENTED (callable: "{self.__requirement.__name__}") - '
                          f'There are unmet confirmation requirements.')
            # TODO: Follow-up actions for downtime
            return

        # Confirm Activity
        self.log.info("Confirmed activity for period {}".format(self.current_period))
        transacting_power = self.worker.transacting_power
        with transacting_power:
            self.worker.confirm_activity()  # < --- blockchain WRITE


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
