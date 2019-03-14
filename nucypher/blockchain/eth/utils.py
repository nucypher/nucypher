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
from nacl.hash import sha256
from typing import Union, Tuple

from nucypher.blockchain.eth.agents import NucypherTokenAgent
from nucypher.blockchain.eth.constants import (MIN_ALLOWED_LOCKED,
                                               MAX_ALLOWED_LOCKED,
                                               MIN_LOCKED_PERIODS,
                                               MAX_MINTING_PERIODS,
                                               SECONDS_PER_PERIOD)


def __validate(rulebook) -> bool:
    for rule, failure_message in rulebook:
        if not rule:
            raise ValueError(failure_message)
    return True


def validate_stake_amount(amount: int, raise_on_fail=True) -> bool:

    rulebook = (

        (MIN_ALLOWED_LOCKED <= amount,
         'Stake amount too low; ({amount}) must be at least {minimum}'
         .format(minimum=MIN_ALLOWED_LOCKED, amount=amount)),

        (MAX_ALLOWED_LOCKED >= amount,
         'Stake amount too high; ({amount}) must be no more than {maximum}.'
         .format(maximum=MAX_ALLOWED_LOCKED, amount=amount)),
    )

    if raise_on_fail is True:
        __validate(rulebook=rulebook)
    return all(rulebook)


def validate_locktime(lock_periods: int, raise_on_fail=True) -> bool:

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


def datetime_to_period(datetime: maya.MayaDT) -> int:
    """Converts a MayaDT instance to a period number."""
    future_period = datetime._epoch // int(SECONDS_PER_PERIOD)
    return int(future_period)


def datetime_at_period(period: int) -> maya.MayaDT:
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
    """An amount of NuCypher tokens"""

    __symbol = 'NU'
    __decimals = 18
    __agent_class = NucypherTokenAgent

    # conversions to smallest denomination
    __denominations = {'NUWei': 10 ** __decimals,
                       'NU': 1}

    def __init__(self, value: int, denomination: str):

        # Calculate smallest denomination and store it
        divisor = self.__denominations[denomination]
        self.__value = Decimal(value) / divisor

    @classmethod
    def from_nu_wei(cls, value):
        return cls(value, denomination='NUWei')

    @classmethod
    def from_tokens(cls, value):
        return cls(value, denomination='NU')

    def to_tokens(self) -> int:
        return int(self.__value)

    def to_nu_wei(self) -> int:
        token_value = self.__value * self.__denominations['NUWei']
        return int(token_value)

    def __eq__(self, other):
        return int(self) == int(other)

    def __radd__(self, other):
        return int(self) + other

    def __add__(self, other):
        return NU(int(self) + int(other), 'NUWei')

    def __sub__(self, other):
        return NU(int(self) - int(other), 'NUWei')

    def __mul__(self, other):
        return NU(int(self) * int(other), 'NUWei')

    def __floordiv__(self, other):
        return NU(int(self) // int(other), 'NUWei')

    def __gt__(self, other):
        return int(self) > int(other)

    def __ge__(self, other):
        return int(self) >= int(other)

    def __lt__(self, other):
        return int(self) < int(other)

    def __le__(self, other):
        return int(self) <= int(other)

    def __int__(self):
        """Cast to smallest denomination"""
        return int(self.to_nu_wei())

    def __repr__(self):
        r = f'{self.__symbol}(value={int(self.__value)})'
        return r

    def __str__(self):
        return f'{str(self.__value)} {self.__symbol}'


class Stake:

    def __init__(self,
                 owner,
                 value: NU,
                 start_period: int,
                 end_period: int):

        # Stake Info
        self.owner = owner
        self.value = value
        self.start_period = start_period
        self.end_period = end_period
        self.duration = self.end_period - self.start_period

        # Internals
        self.start_datetime = datetime_at_period(period=start_period)
        self.end_datetime = datetime_at_period(period=end_period)
        self.duration_delta = self.end_datetime - self.start_datetime

        self.miner_agent = owner.miner_agent

    def __repr__(self):
        r = f'Stake({self.id}, value={self.value}, end_period={self.end_period})'
        return r

    @classmethod
    def from_stake_info(cls, owner, stake_info: Tuple[int, int, int]):
        start_period, end_period, value = stake_info
        instance = cls(owner=owner,
                       start_period=start_period,
                       end_period=end_period,
                       value=NU(value, 'NUWei'))
        return instance

    def to_stake_info(self) -> Tuple[int, int, int]:
        return self.start_period, self.end_period, int(self.value)

    @property
    def id(self) -> str:
        digest = b''
        digest += eth_utils.to_canonical_address(address=self.owner.checksum_public_address)
        digest += str(self.start_period).encode()
        digest += str(self.end_period).encode()
        digest += str(self.value).encode()
        stake_id = sha256(digest).hex()[:16]
        return stake_id[:16]

    @property
    def periods_remaining(self):
        current_period = self.miner_agent.get_current_period()
        return self.end_period - current_period

    def time_remaining(self, slang: bool = False) -> Union[int, str]:
        now = maya.now()
        delta = self.end_datetime - now
        if slang:
            result = self.end_datetime.slang_date()
        else:
            result = delta.seconds
        return result
