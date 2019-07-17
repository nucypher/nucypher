from _pydecimal import Decimal
from typing import Union, Tuple, Callable, List

import maya
from constant_sorrow.constants import (
    NEW_STAKE,
    NO_STAKING_RECEIPT,
    NOT_STAKING,
    UNKNOWN_STAKES,
    NO_STAKES,
    EMPTY_STAKING_SLOT,
    UNKNOWN_WORKER_STATUS
)
from eth_utils import currency, is_checksum_address
from twisted.internet import task, reactor
from twisted.logger import Logger

from nucypher.blockchain.eth.agents import NucypherTokenAgent, StakingEscrowAgent
from nucypher.blockchain.eth.decorators import validate_checksum_address
from nucypher.blockchain.eth.utils import datetime_at_period, datetime_to_period


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
        """Returns an decimal value of NU"""
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

    def __repr__(self) -> str:
        r = f'{self.__symbol}(value={str(self.__value)})'
        return r

    def __str__(self) -> str:
        return f'{str(self.to_tokens())} {self.__symbol}'


class Stake:
    """
    A quantity of tokens and staking duration for one stake for one staker.
    """

    class StakingError(Exception):
        """Raised when a staking operation cannot be executed due to failure."""

    def __init__(self,
                 checksum_address: str,
                 value: NU,
                 start_period: int,
                 end_period: int,
                 index: int,
                 economics = None,
                 validate_now: bool = True):

        self.log = Logger(f'stake-{checksum_address}-{index}')

        # Stake Metadata
        self.owner_address = checksum_address
        self.worker_address = UNKNOWN_WORKER_STATUS
        self.index = index
        self.value = value
        self.start_period = start_period
        self.end_period = end_period

        # Time
        self.start_datetime = datetime_at_period(period=start_period)
        self.end_datetime = datetime_at_period(period=end_period)
        self.duration_delta = self.end_datetime - self.start_datetime

        # Agency
        self.staking_agent = None
        self.token_agent = NucypherTokenAgent()  # TODO: Use Agency
        self.blockchain = self.token_agent.blockchain

        # Economics
        from nucypher.blockchain.economics import TokenEconomics
        self.economics = economics or TokenEconomics()
        self.minimum_nu = NU(int(self.economics.minimum_allowed_locked), 'NuNit')
        self.maximum_nu = NU(int(self.economics.maximum_allowed_locked), 'NuNit')

        if validate_now:
            self.validate_duration()

        self.transactions = NO_STAKING_RECEIPT
        self.receipt = NO_STAKING_RECEIPT

    def __repr__(self) -> str:
        r = f'Stake(index={self.index}, value={self.value}, end_period={self.end_period})'
        return r

    def __eq__(self, other) -> bool:
        return bool(self.value == other.value)

    #
    # Metadata
    #

    @property
    def is_expired(self) -> bool:
        if self.staking_agent:
            current_period = self.staking_agent.get_current_period()  # on-chain
        else:
            current_period = datetime_to_period(maya.now())  # off-chain
        return bool(current_period >= self.end_period)

    @property
    def is_active(self) -> bool:
        return not self.is_expired

    @classmethod
    @validate_checksum_address
    def from_stake_info(cls,
                        checksum_address: str,
                        index: int,
                        stake_info: Tuple[int, int, int]
                        ) -> 'Stake':

        """Reads staking values as they exist on the blockchain"""
        start_period, end_period, value = stake_info

        instance = cls(checksum_address=checksum_address,
                       index=index,
                       start_period=start_period,
                       end_period=end_period,
                       value=NU(value, 'NuNit'))

        agent = StakingEscrowAgent()
        instance.worker_address = agent.get_worker_from_staker(staker_address=checksum_address)
        return instance

    def to_stake_info(self) -> Tuple[int, int, int]:
        """Returns a tuple representing the blockchain record of a stake"""
        return self.start_period, self.end_period, int(self.value)

    #
    # Duration
    #

    @property
    def duration(self) -> int:
        """Return stake duration in periods"""
        result = (self.end_period - self.start_period) + 1
        return result

    @property
    def periods_remaining(self) -> int:
        """Returns the number of periods remaining in the stake from now."""
        current_period = datetime_to_period(datetime=maya.now())
        return self.end_period - current_period

    def time_remaining(self, slang: bool = False) -> Union[int, str]:
        """Returns the time delta remaining in the stake from now."""
        now = maya.now()
        delta = self.end_datetime - now

        if slang:
            result = self.end_datetime.slang_date()
        else:
            result = delta.seconds
        return result

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
             'Stake duration of ({duration}) is too short; must be at least {minimum} periods.'
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

        if not self.staking_agent:
            self.staking_agent = StakingEscrowAgent(blockchain=self.blockchain)
        if not self.token_agent:
            self.token_agent = NucypherTokenAgent(blockchain=self.blockchain)

        # Read from blockchain
        stake_info = self.staking_agent.get_substake_info(staker_address=self.owner_address,
                                                          stake_index=self.index)  # < -- Read from blockchain

        first_period, last_period, locked_value = stake_info
        if not self.start_period == first_period:
            # TODO: Provide an escape path or re-attempt in implementation
            raise self.StakingError("Inconsistent staking cache, aborting stake division.")

        # Mutate the instance with the on-chain values
        self.end_period = last_period
        self.value = NU.from_nunits(locked_value)
        self.worker_address = self.staking_agent.get_worker_from_staker(staker_address=self.owner_address)

    @classmethod
    def __deposit(cls, staker, amount: int, lock_periods: int) -> Tuple[str, str]:
        """Public facing method for token locking."""

        approve_txhash = staker.token_agent.approve_transfer(amount=amount,
                                                             target_address=staker.staking_agent.contract_address,
                                                             sender_address=staker.checksum_address)

        deposit_txhash = staker.staking_agent.deposit_tokens(amount=amount,
                                                             lock_periods=lock_periods,
                                                             sender_address=staker.checksum_address)

        return approve_txhash, deposit_txhash

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
            raise self.StakingError(f'Cannot divide an expired stake. Selected stake expired {self.end_datetime}.')

        if target_value >= self.value:
            raise self.StakingError(f"Cannot divide stake; Target value ({target_value}) must be less "
                                    f"than the existing stake value {self.value}.")

        #
        # Generate SubStakes
        #

        # Modified Original Stake
        remaining_stake_value = self.value - target_value
        modified_stake = Stake(checksum_address=self.owner_address,
                               index=self.index,
                               start_period=self.start_period,
                               end_period=self.end_period,
                               value=remaining_stake_value)

        # New Derived Stake
        end_period = self.end_period + additional_periods
        new_stake = Stake(checksum_address=self.owner_address,
                          start_period=self.start_period,
                          end_period=end_period,
                          value=target_value,
                          index=NEW_STAKE)

        #
        # Validate
        #

        # Ensure both halves are for valid amounts
        modified_stake.validate_value()
        new_stake.validate_value()

        #
        # Transmit
        #

        # Transmit the stake division transaction
        receipt = self.staking_agent.divide_stake(staker_address=self.owner_address,
                                                  stake_index=self.index,
                                                  target_value=int(target_value),
                                                  periods=additional_periods)
        new_stake.receipt = receipt

        return modified_stake, new_stake

    @classmethod
    def initialize_stake(cls, staker, amount: NU, lock_periods: int = None) -> 'Stake':

        # Value
        amount = NU(int(amount), 'NuNit')

        # Duration
        current_period = staker.staking_agent.get_current_period()
        end_period = current_period + lock_periods

        stake = Stake(checksum_address=staker.checksum_address,
                      start_period=current_period+1,
                      end_period=end_period,
                      value=amount,
                      index=NEW_STAKE)

        # Validate
        stake.validate_value()
        stake.validate_duration()

        # Transmit
        approve_txhash, initial_deposit_txhash = stake.__deposit(amount=int(amount),
                                                                 lock_periods=lock_periods,
                                                                 staker=staker)

        # Store the staking transactions on the instance
        staking_transactions = dict(approve=approve_txhash, deposit=initial_deposit_txhash)
        stake.transactions = staking_transactions

        # Log and return Stake instance
        log = Logger(f'stake-{staker.checksum_address}-creation')
        log.info("{} Initialized new stake: {} tokens for {} periods".format(staker.checksum_address,
                                                                             amount,
                                                                             lock_periods))
        return stake


class StakeTracker:

    REFRESH_RATE = 60

    tracking_addresses = set()

    __stakes = dict()    # type: Dict[str: List[Stake]]
    __actions = list()   # type: List[Tuple[Callable, tuple]]

    def __init__(self,
                 checksum_addresses: List[str],
                 refresh_rate: int = None,
                 start_now: bool = False,
                 *args, **kwargs):

        super().__init__(*args, **kwargs)

        self.log = Logger('stake-tracker')
        self.staking_agent = StakingEscrowAgent()

        self._refresh_rate = refresh_rate or self.REFRESH_RATE
        self._tracking_task = task.LoopingCall(self.__update)

        self.__current_period = None
        self.__stakes = dict()
        self.__start_time = NOT_STAKING
        self.__uptime_period = NOT_STAKING
        self.__terminal_period = NOT_STAKING
        self._abort_on_stake_tracking_error = True

        # "load-in":  Read on-chain stakes
        for checksum_address in checksum_addresses:
            if not is_checksum_address(checksum_address):
                raise ValueError(f'{checksum_address} is not a valid EIP-55 checksum address')
            self.tracking_addresses.add(checksum_address)

        if start_now:
            self.start()  # deamonize
        else:
            self.refresh(checksum_addresses=checksum_addresses)  # read-once

    @validate_checksum_address
    def __getitem__(self, checksum_address: str):
        stakes = self.stakes(checksum_address=checksum_address)
        return stakes

    def add_action(self, func: Callable, args=()) -> None:
        self.__actions.append((func, args))

    def clear_actions(self) -> None:
        self.__actions.clear()

    @property
    def current_period(self):
        return self.__current_period

    @validate_checksum_address
    def stakes(self, checksum_address: str) -> List[Stake]:
        """Return all cached stake instances from the blockchain."""
        try:
            return self.__stakes[checksum_address]
        except KeyError:
            return NO_STAKES.bool_value(False)
        except TypeError:
            if self.__stakes in (UNKNOWN_STAKES, NO_STAKES):
                return NO_STAKES.bool_value(False)
            raise

    @validate_checksum_address
    def refresh(self, checksum_addresses: List[str] = None) -> None:
        """Public staking cache invalidation method"""
        return self.__read_stakes(checksum_addresses=checksum_addresses)

    def stop(self) -> None:
        self._tracking_task.stop()
        self.log.info(f"STOPPED STAKE TRACKING")

    def start(self, force: bool = False) -> None:
        """
        High-level stake tracking initialization, this function aims
        to be safely called at any time - For example, it is okay to call
        this function multiple times within the same period.
        """
        if self._tracking_task.running and not force:
            return

        # Record the start time and period
        self.__start_time = maya.now()
        self.__uptime_period = self.staking_agent.get_current_period()
        self.__current_period = self.__uptime_period

        d = self._tracking_task.start(interval=self._refresh_rate)
        d.addErrback(self.handle_tracking_errors)
        self.log.info(f"STARTED STAKE TRACKING for {len(self.tracking_addresses)} addresses")

    def _crash_gracefully(self, failure=None) -> None:
        """
        A facility for crashing more gracefully in the event that
        an exception is unhandled in a different thread.
        """
        self._crashed = failure
        failure.raiseException()

    def handle_tracking_errors(self, *args, **kwargs) -> None:
        failure = args[0]
        if self._abort_on_stake_tracking_error:
            self.log.critical(f"Unhandled error during node stake tracking. {failure}")
            reactor.callFromThread(self._crash_gracefully, failure=failure)
        else:
            self.log.warn(f"Unhandled error during stake tracking: {failure.getTraceback()}")

    def __update(self) -> None:
        self.log.info(f"Checking for new period. Current period is {self.__current_period}")
        onchain_period = self.staking_agent.get_current_period()  # < -- Read from contract
        if self.__current_period != onchain_period:
            self.__current_period = onchain_period
            self.__read_stakes()
            for action, args in self.__actions:
                action(*args)

    @validate_checksum_address
    def __read_stakes(self, checksum_addresses: List[str] = None) -> None:
        """Rewrite the local staking cache by reading on-chain stakes"""

        if not checksum_addresses:
            checksum_addresses = self.tracking_addresses

        for checksum_address in checksum_addresses:

            if not is_checksum_address(checksum_address):
                if self._abort_on_stake_tracking_error:
                    raise ValueError(f'{checksum_address} is not a valid EIP-55 checksum address')
                self.tracking_addresses.remove(checksum_address)  # Prune

            existing_records = len(self.stakes(checksum_address=checksum_address))

            # Candidate replacement cache values
            onchain_stakes, terminal_period = list(), 0

            # Read from blockchain
            stakes_reader = self.staking_agent.get_all_stakes(staker_address=checksum_address)
            for onchain_index, stake_info in enumerate(stakes_reader):

                if not stake_info:
                    onchain_stake = EMPTY_STAKING_SLOT

                else:
                    onchain_stake = Stake.from_stake_info(checksum_address=checksum_address,
                                                          stake_info=stake_info,
                                                          index=onchain_index)

                    # rack the latest terminal period
                    if onchain_stake.end_period > terminal_period:
                        terminal_period = onchain_stake.end_period

                # Store the replacement stake
                onchain_stakes.append(onchain_stake)

            # Commit the new stake and terminal values to the cache
            if not onchain_stakes:
                self.__stakes[checksum_address] = NO_STAKES.bool_value(False)
            else:
                self.__terminal_period = terminal_period
                self.__stakes[checksum_address] = onchain_stakes
                new_records = existing_records - len(self.__stakes[checksum_address])
                self.log.debug(f"Updated local staking cache ({new_records} new stakes).")

            # Record most recent cache update
            self.__updated = maya.now()
