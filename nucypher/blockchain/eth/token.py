from _pydecimal import Decimal

import eth_utils
import maya
from eth_utils import currency
from nacl.hash import sha256
from typing import Union, Tuple

from nucypher.blockchain.eth.agents import NucypherTokenAgent
from nucypher.blockchain.eth.constants import TOKEN_DECIMALS
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
    __decimals = TOKEN_DECIMALS
    __agent_class = NucypherTokenAgent

    # conversions
    __denominations = {'NuNit': 'wei',
                       'NU': 'ether'}

    class InvalidAmount(ValueError):
        """Raised when an invalid input amount is provided"""

    def __init__(self, value: Union[int, float, str], denomination: str):

        # Calculate smallest denomination and store it
        wrapped_denom = self.__denominations[denomination]

        # Convert or Raise
        try:
            self.__value = currency.to_wei(number=value, unit=wrapped_denom)
        except ValueError as e:
            raise NU.InvalidAmount(f"{value} is an invalid amount of tokens: {str(e)}")

    @classmethod
    def from_nunits(cls, value: int):
        return cls(value, denomination='NuNit')

    @classmethod
    def from_tokens(cls, value: Union[int, float, str]):
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
        self.duration = (self.end_period-self.start_period) + 1

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
                       value=NU(value, 'NuNit'))
        return instance

    def to_stake_info(self) -> Tuple[int, int, int]:
        """Returns a tuple representing the blockchain record of a stake"""
        return self.start_period, self.end_period, int(self.value)

    @property
    def id(self) -> str:
        """TODO: Unique staking ID, currently unused"""
        digest_elements = list()
        digest_elements.append(eth_utils.to_canonical_address(address=self.owner_address))
        digest_elements.append(str(self.index).encode())
        digest_elements.append(str(self.start_period).encode())
        digest_elements.append(str(self.end_period).encode())
        digest_elements.append(str(self.value).encode())
        digest = b'|'.join(digest_elements)
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
