from typing import Union

from _pydecimal import Decimal
from eth_utils import currency

from nucypher.types import ERC20UNits, NuNits, TuNits


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
