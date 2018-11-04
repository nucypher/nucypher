"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""
"""Nucypher Token and Miner constants."""

ONE_YEAR_IN_SECONDS = 31540000
NUCYPHER_GAS_LIMIT = 5000000  # TODO: move elsewhere?

#
# Dispatcher
#

DISPATCHER_SECRET_LENGTH = 32

#
# Policy
#

POLICY_ID_LENGTH = 16


#
# Token
#

NULL_ADDRESS = '0x' + '0' * 40

__subdigits = 18
M = 10 ** __subdigits                                  # Unit designation

__initial_supply = int(1e9) * M                        # Initial token supply
__saturation = int(3.89e9) * M                         # Token supply cap
TOKEN_SUPPLY = __saturation - __initial_supply         # Remaining supply
TOKEN_SATURATION = __saturation


#
# Miner
#

HOURS_PER_PERIOD = 24                            # Hours in single period
SECONDS_PER_PERIOD = HOURS_PER_PERIOD * 60 * 60  # Seconds in single period
MIN_LOCKED_PERIODS = 30                          # 720 Hours minimum
MAX_MINTING_PERIODS = 365                        # Maximum number of periods

MIN_ALLOWED_LOCKED = 15000 * M
MAX_ALLOWED_LOCKED = int(4e6) * M

"""

Mining formula for one stake in one period:
(totalSupply - currentSupply) * (lockedValue / totalLockedValue) * (k1 + allLockedPeriods) / k2

- totalSupply - Token supply cap
- currentSupply - Current supply cap
- lockedValue - Amount of tokens in one miner's stake in one period
- totalLockedValue - Amount of tokens in all stakes in one period
- allLockedPeriods - Duration of the current miner's stake
- if allLockedPeriods > rewardedPeriods then allLockedPeriods = rewardedPeriods

"""

__mining_coeff = (
    HOURS_PER_PERIOD,       # Hours in single period
    2 * 10 ** 7,            # Mining coefficient (k2)
    MAX_MINTING_PERIODS,    # Locked periods coefficient (k1)
    MAX_MINTING_PERIODS,    # Max periods that will be additionally rewarded (rewardedPeriods)
    MIN_LOCKED_PERIODS,     # Min amount of periods during which tokens can be locked
    MIN_ALLOWED_LOCKED,     # Min amount of tokens that can be locked
    MAX_ALLOWED_LOCKED      # Max amount of tokens that can be locked
)

MINING_COEFFICIENT = __mining_coeff
