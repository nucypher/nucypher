from _pydecimal import Decimal
from typing import Union, Tuple

import maya
from constant_sorrow.constants import NEW_STAKE, NO_STAKING_RECEIPT
from eth_utils import currency
from twisted.logger import Logger

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

    __ID_LENGTH = 16

    def __init__(self,
                 staker,
                 value: NU,
                 start_period: int,
                 end_period: int,
                 index: int,
                 validate_now: bool = True):

        self.staker = staker
        owner_address = staker.checksum_address
        self.log = Logger(f'stake-{owner_address}-{index}')

        # Stake Metadata
        self.owner_address = owner_address
        self.index = index
        self.value = value
        self.start_period = start_period
        self.end_period = end_period

        # Time
        self.start_datetime = datetime_at_period(period=start_period)
        self.end_datetime = datetime_at_period(period=end_period)
        self.duration_delta = self.end_datetime - self.start_datetime

        self.blockchain = staker.blockchain

        # Agency
        self.staker_agent = staker.staker_agent
        self.token_agent = staker.token_agent

        # Economics
        self.economics = staker.economics
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
        current_period = self.staker_agent.get_current_period()
        return bool(current_period >= self.end_period)

    @property
    def is_active(self) -> bool:
        return not self.is_expired

    @classmethod
    def from_stake_info(cls,
                        staker,
                        index: int,
                        stake_info: Tuple[int, int, int]
                        ) -> 'Stake':

        """Reads staking values as they exist on the blockchain"""
        start_period, end_period, value = stake_info

        instance = cls(staker=staker,
                       index=index,
                       start_period=start_period,
                       end_period=end_period,
                       value=NU(value, 'NuNit'))
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
             'Stake amount too low; ({amount}) must be at least {minimum}'
             .format(minimum=self.minimum_nu, amount=self.value)),

            (self.maximum_nu >= self.value,
             'Stake amount too high; ({amount}) must be no more than {maximum}.'
             .format(maximum=self.maximum_nu, amount=self.value)),
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

        # Read from blockchain
        stake_info = self.staker_agent.get_substake_info(staker_address=self.owner_address,
                                                        stake_index=self.index)  # < -- Read from blockchain

        first_period, last_period, locked_value = stake_info
        if not self.start_period == first_period:
            # TODO: Provide an escape path or re-attempt in implementation
            raise self.StakingError("Inconsistent staking cache, aborting stake division.")

        # Mutate the instance with the on-chain values
        self.end_period = last_period
        self.value = NU.from_nunits(locked_value)

    @classmethod
    def __deposit(cls, staker, amount: int, lock_periods: int) -> Tuple[str, str]:
        """Public facing method for token locking."""

        approve_txhash = staker.token_agent.approve_transfer(amount=amount,
                                                            target_address=staker.staker_agent.contract_address,
                                                            sender_address=staker.checksum_address)

        deposit_txhash = staker.staker_agent.deposit_tokens(amount=amount,
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
        modified_stake = Stake(staker=self.staker,
                               index=self.index,
                               start_period=self.start_period,
                               end_period=self.end_period,
                               value=remaining_stake_value)

        # New Derived Stake
        end_period = self.end_period + additional_periods
        new_stake = Stake(staker=self.staker,
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
        tx = self.staker_agent.divide_stake(staker_address=self.owner_address,
                                           stake_index=self.index,
                                           target_value=int(target_value),
                                           periods=additional_periods)
        receipt = self.blockchain.wait_for_receipt(tx)
        new_stake.receipt = receipt

        return modified_stake, new_stake

    @classmethod
    def initialize_stake(cls, staker, amount: NU, lock_periods: int = None) -> 'Stake':

        # Value
        amount = NU(int(amount), 'NuNit')

        # Duration
        current_period = staker.staker_agent.get_current_period()
        end_period = current_period + lock_periods

        stake = Stake(staker=staker,
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
