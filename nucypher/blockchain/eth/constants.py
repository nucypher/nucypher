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

ONE_YEAR_IN_SECONDS = 31540000  # TODO #831: This value is incorrect

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

# Denomination
TOKEN_DECIMALS = 18
NUNITS_PER_TOKEN = 10 ** TOKEN_DECIMALS         # Smallest unit designation

# Supply
__initial_supply = int(1e9) * NUNITS_PER_TOKEN  # Initial token supply
__saturation = int(3.89e9) * NUNITS_PER_TOKEN   # Token supply cap
TOKEN_SUPPLY = __saturation - __initial_supply     # Remaining supply
TOKEN_SATURATION = __saturation


"""
~ Staking ~

Mining formula for one stake in one period:
(totalSupply - currentSupply) * (lockedValue / totalLockedValue) * (k1 + allLockedPeriods) / k2

- totalSupply - Token supply cap
- currentSupply - Current supply cap
- lockedValue - Amount of tokens in one miner's stake in one period
- totalLockedValue - Amount of tokens in all stakes in one period
- allLockedPeriods - Duration of the current miner's stake
- if allLockedPeriods > rewardedPeriods then allLockedPeriods = rewardedPeriods

"""


# Periods
HOURS_PER_PERIOD = 24                            # Hours in single period
SECONDS_PER_PERIOD = HOURS_PER_PERIOD * 60 * 60  # Seconds in single period

# Lock Time
MIN_LOCKED_PERIODS = 30                          # 720 Hours minimum
MAX_MINTING_PERIODS = 365                        # Maximum number of periods

# Lock Value
MIN_ALLOWED_LOCKED = 15000 * NUNITS_PER_TOKEN
MAX_ALLOWED_LOCKED = int(4e6) * NUNITS_PER_TOKEN

# Rewards
K2 = 2 * 10 ** 7   # Mining Coefficient

MINING_COEFFICIENT = (
    HOURS_PER_PERIOD,       # Hours in single period
    K2,                     # Mining coefficient (k2)
    MAX_MINTING_PERIODS,    # Locked periods coefficient (k1)
    MAX_MINTING_PERIODS,    # Max periods that will be additionally rewarded (rewardedPeriods)
    MIN_LOCKED_PERIODS,     # Min amount of periods during which tokens can be locked
    MIN_ALLOWED_LOCKED,     # Min amount of tokens that can be locked
    MAX_ALLOWED_LOCKED      # Max amount of tokens that can be locked
)

# Testing and development

NUMBER_OF_URSULAS_IN_BLOCKCHAIN_TESTS = 10

NUMBER_OF_ETH_TEST_ACCOUNTS = NUMBER_OF_URSULAS_IN_BLOCKCHAIN_TESTS + 10


