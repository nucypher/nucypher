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


from decimal import Decimal

import eth_utils
import maya
from eth_utils import currency
from nacl.hash import sha256
from typing import Union, Tuple

from nucypher.blockchain.eth.agents import NucypherTokenAgent
from nucypher.blockchain.eth.constants import (MIN_ALLOWED_LOCKED,
                                               MAX_ALLOWED_LOCKED,
                                               MIN_LOCKED_PERIODS,
                                               MAX_MINTING_PERIODS,
                                               SECONDS_PER_PERIOD)


def datetime_to_period(datetime: maya.MayaDT) -> int:
    """Converts a MayaDT instance to a period number."""
    future_period = datetime._epoch // int(SECONDS_PER_PERIOD)
    return int(future_period)


def datetime_at_period(period: int) -> maya.MayaDT:
    """Returns the datetime object at a given period, future, or past."""

    now = maya.now()
    current_period = datetime_to_period(datetime=now)
    delta_periods = period - current_period

    # +
    if delta_periods:
        target_period = now + maya.timedelta(days=delta_periods)

    # -
    else:
        target_period = now - maya.timedelta(days=delta_periods)

    return target_period


def calculate_period_duration(future_time: maya.MayaDT) -> int:
    """Takes a future MayaDT instance and calculates the duration from now, returning in periods"""
    future_period = datetime_to_period(datetime=future_time)
    current_period = datetime_to_period(datetime=maya.now())
    periods = future_period - current_period
    return periods


class NU:
    """
    An amount of NuCypher tokens that doesn't hurt your eyes.
    Wraps the eth_utils currency conversion methods.

    The easiest way to use NU, is to pass an int, float, or str, and denomination string:

    Int:    nu = NU(100, 'NU')
    Int:    nu_wei = NU(15000000000000000000000, 'NUWei')

    Float:  nu = NU(15042.445, 'NU')
    String: nu = NU('10002.302', 'NU')

    ...or alternately...

    Float: nu = NU.from_tokens(100.50)
    Int: nu_wei = NU.from_nu_wei(15000000000000000000000)

    Token quantity is stored internally as an int in the smallest denomination,
    and all arithmetic operations use this value.
    """

    __symbol = 'NU'
    __decimals = 18
    __agent_class = NucypherTokenAgent

    # conversions to smallest denomination
    __denominations = {'NUWei': 'wei',
                       'NU': 'ether'}

    def __init__(self, value: Union[int, float, str], denomination: str):

        # Calculate smallest denomination and store it
        wrapped_denom = self.__denominations[denomination]

        # Validate Early
        if '.' in str(value):

            _, fraction = str(value).split('.')
            if len(fraction) > self.__decimals:
                raise ValueError("Cannot initialize with fractional wei value")

            if wrapped_denom == 'wei':
                raise ValueError("Cannot initialize with fractional wei value")

        self.__value = currency.to_wei(number=value, unit=wrapped_denom)

    @classmethod
    def from_nu_wei(cls, value: int):
        return cls(value, denomination='NUWei')

    @classmethod
    def from_tokens(cls, value: Union[int, float, str]):
        return cls(value, denomination='NU')

    def to_tokens(self) -> Decimal:
        """Returns an decimal value of NU"""
        return currency.from_wei(self.__value, unit='ether')

    def to_nu_wei(self) -> int:
        """Returns an int value in NU-Wei"""
        return int(self.__value)

    def __eq__(self, other) -> bool:
        return int(self) == int(other)

    def __radd__(self, other) -> int:
        return int(self) + other

    def __add__(self, other) -> 'NU':
        return NU(int(self) + int(other), 'NUWei')

    def __sub__(self, other) -> 'NU':
        return NU(int(self) - int(other), 'NUWei')

    def __mul__(self, other) -> 'NU':
        return NU(int(self) * int(other), 'NUWei')

    def __floordiv__(self, other) -> 'NU':
        return NU(int(self) // int(other), 'NUWei')

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
        return int(self.to_nu_wei())

    def __repr__(self) -> str:
        r = f'{self.__symbol}(value={str(self.__value)})'
        return r

    def __str__(self) -> str:
        return f'{str(self.to_tokens())} {self.__symbol}'


class Stake:
    """
    A quantity of tokens, and staking time-frame for one stake for one miner.
    """

    __ID_LENGTH = 16

    def __init__(self,
                 owner_address: str,
                 index: int,
                 value: NU,
                 start_period: int,
                 end_period: int):

        # Stake Info
        self.owner_address = owner_address
        self.index = index
        self.value = value
        self.start_period = start_period
        self.end_period = end_period
        self.duration = self.end_period - self.start_period

        # Internals
        self.start_datetime = datetime_at_period(period=start_period)
        self.end_datetime = datetime_at_period(period=end_period)
        self.duration_delta = self.end_datetime - self.start_datetime

    def __repr__(self):
        r = f'Stake(index={self.index}, value={self.value}, end_period={self.end_period})'
        return r

    def __eq__(self, other):
        return bool(self.value == other.value)

    @classmethod
    def from_stake_info(cls, owner_address, index: int, stake_info: Tuple[int, int, int]):
        """Reads staking values as they exist on the blockchain"""
        start_period, end_period, value = stake_info
        instance = cls(owner_address=owner_address,
                       index=index,
                       start_period=start_period,
                       end_period=end_period,
                       value=NU(value, 'NUWei'))
        return instance

    def to_stake_info(self) -> Tuple[int, int, int]:
        """Returns a tuple representing the blockchain record of a stake"""
        return self.start_period, self.end_period, int(self.value)

    @property
    def id(self) -> str:
        """TODO: Unique staking ID, currently unused"""
        digest = b''
        digest += eth_utils.to_canonical_address(address=self.owner_address)
        digest += str(self.index).encode()
        digest += str(self.start_period).encode()
        digest += str(self.end_period).encode()
        digest += str(self.value).encode()
        stake_id = sha256(digest).hex()[:16]
        return stake_id[:self.__ID_LENGTH]

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


def __validate(rulebook) -> bool:
    """Validate a rulebook"""
    for rule, failure_message in rulebook:
        if not rule:
            raise ValueError(failure_message)
    return True


def validate_stake_amount(amount: NU, raise_on_fail=True) -> bool:
    """Validate a single staking value against pre-defined requirements"""

    min_locked = NU(MIN_ALLOWED_LOCKED, 'NUWei')
    max_locked = NU(MAX_ALLOWED_LOCKED, 'NUWei')

    rulebook = (

        (min_locked <= amount,
         'Stake amount too low; ({amount}) must be at least {minimum}'
         .format(minimum=min_locked, amount=amount)),

        (max_locked >= amount,
         'Stake amount too high; ({amount}) must be no more than {maximum}.'
         .format(maximum=max_locked, amount=amount)),
    )

    if raise_on_fail is True:
        __validate(rulebook=rulebook)
    return all(rulebook)


def validate_locktime(lock_periods: int, raise_on_fail=True) -> bool:
    """Validate a single staking lock-time against pre-defined requirements"""

    rulebook = (

        (MIN_LOCKED_PERIODS <= lock_periods,
         'Locktime ({locktime}) too short; must be at least {minimum}'
         .format(minimum=MIN_LOCKED_PERIODS, locktime=lock_periods)),

        (MAX_MINTING_PERIODS >= lock_periods,
         'Locktime ({locktime}) too long; must be no more than {maximum}'
         .format(maximum=MAX_MINTING_PERIODS, locktime=lock_periods)),
    )

    if raise_on_fail is True:
        __validate(rulebook=rulebook)
    return all(rulebook)
