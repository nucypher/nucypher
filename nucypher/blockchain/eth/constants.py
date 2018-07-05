"""
Base NuCypher Token and Miner constants configuration.

These values are static and do not need to be changed during runtime;
Once the NuCypherToken contract is deployed to a network with one set of constant values,
those values are then required to be compatible with the rest of the network.
"""

import maya
from constant_sorrow.constants import (NULL_ADDRESS, TOKEN_SATURATION, MINING_COEFFICIENT, TOKEN_SUPPLY,
                                       M, HOURS_PER_PERIOD, MIN_LOCKED_PERIODS, MAX_MINTING_PERIODS,
                                       MIN_ALLOWED_LOCKED, MAX_ALLOWED_LOCKED, SECONDS_PER_PERIOD,
                                       POLICY_ID_LENGTH, )


#
# Token
#


class TokenConfigError(ValueError):
    pass


NULL_ADDRESS('0x' + '0' * 40)

__subdigits = 18
M(10 ** __subdigits)                                  # Unit designation

__initial_supply = int(1e9) * M                       # Initial token supply
__saturation = int(3.89e9) * M                        # Token supply cap
TOKEN_SUPPLY(__saturation - __initial_supply)         # Remaining supply
TOKEN_SATURATION(__saturation)


#
# Miner
#

class MinerConfigError(ValueError):
    pass


HOURS_PER_PERIOD(24)                            # Hours in single period
SECONDS_PER_PERIOD(HOURS_PER_PERIOD * 60 * 60)  # Seconds in single period
MIN_LOCKED_PERIODS(30)                          # 720 Hours minimum
MAX_MINTING_PERIODS(365)                        # Maximum number of periods

MIN_ALLOWED_LOCKED(15000*M)
MAX_ALLOWED_LOCKED(int(4e6)*M)


__mining_coeff = (           # TODO: label
    HOURS_PER_PERIOD,
    2 * 10 ** 7,
    MAX_MINTING_PERIODS,
    MAX_MINTING_PERIODS,
    MIN_LOCKED_PERIODS,
    MIN_ALLOWED_LOCKED,
    MAX_ALLOWED_LOCKED
)

MINING_COEFFICIENT(__mining_coeff)


#
# Policy
#


class PolicyConfigError(ValueError):
    pass


POLICY_ID_LENGTH(16)


def __validate(rulebook) -> bool:
    for rule, failure_message in rulebook:
        if not rule:
            raise MinerConfigError(failure_message)
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


def calculate_period_duration(future_time: maya.MayaDT) -> int:
    """Takes a future MayaDT instance and calculates the duration from now, returning in periods"""

    future_period = datetime_to_period(datetime=future_time)
    current_period = datetime_to_period(datetime=maya.now())
    periods = future_period - current_period
    return periods
