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


from decimal import Decimal, localcontext
from math import log

from nucypher.blockchain.economics import TokenEconomics, LOG2


def test_rough_economics():
    """
    Formula for staking in one period:
    (totalSupply - currentSupply) * (lockedValue / totalLockedValue) * (k1 + allLockedPeriods) / k2

    K2 - Staking coefficient
    K1 - Locked periods coefficient

    if allLockedPeriods > awarded_periods then allLockedPeriods = awarded_periods
    kappa * log(2) / halving_delay === (k1 + allLockedPeriods) / k2

    kappa = small_stake_multiplier + (1 - small_stake_multiplier) * min(T, T1) / T1
    where allLockedPeriods == min(T, T1)
    """

    e = TokenEconomics(initial_supply=int(1e9),
                       initial_inflation=1,
                       halving_delay=2,
                       reward_saturation=1,
                       small_stake_multiplier=Decimal(0.5))

    assert float(round(e.erc20_total_supply / Decimal(1e9), 2)) == 3.89  # As per economics paper

    # Check that we have correct numbers in day 1
    initial_rate = (e.erc20_total_supply - e.initial_supply) * (e.locked_periods_coefficient + 365) / e.staking_coefficient
    assert int(initial_rate) == int(e.initial_inflation * e.initial_supply / 365)

    initial_rate_small = (e.erc20_total_supply - e.initial_supply) * e.locked_periods_coefficient / e.staking_coefficient
    assert int(initial_rate_small) == int(initial_rate / 2)

    # Sanity check that total and reward supply calculated correctly
    assert int(LOG2 / (e.token_halving * 365) * (e.erc20_total_supply - e.initial_supply)) == int(initial_rate)
    assert int(e.reward_supply) == int(e.erc20_total_supply - Decimal(int(1e9)))

    # Sanity check for locked_periods_coefficient (k1) and staking_coefficient (k2)
    assert e.locked_periods_coefficient * e.token_halving == e.staking_coefficient * LOG2 * e.small_stake_multiplier / 365


def test_exact_economics():
    """
    Formula for staking in one period:
    (totalSupply - currentSupply) * (lockedValue / totalLockedValue) * (k1 + allLockedPeriods) / k2

    K2 - Staking coefficient
    K1 - Locked periods coefficient

    if allLockedPeriods > awarded_periods then allLockedPeriods = awarded_periods
    kappa * log(2) / halving_delay === (k1 + allLockedPeriods) / k2

    kappa = small_stake_multiplier + (1 - small_stake_multiplier) * min(T, T1) / T1
    where allLockedPeriods == min(T, T1)
    """

    #
    # Expected Output
    #

    # Supply
    expected_total_supply = 3885390081777926911255691439
    expected_supply_ratio = Decimal('3.885390081777926911255691439')
    expected_initial_supply = 1000000000000000000000000000

    # Reward
    expected_reward_supply = 2885390081777926911255691439
    reward_saturation = 1

    # Staking
    halving = 2
    multiplier = 0.5
    expected_locked_periods_coefficient = 365
    expected_staking_coefficient = 768812

    assert expected_locked_periods_coefficient * halving == round(expected_staking_coefficient * log(2) * multiplier / 365)

    #
    # Sanity
    #

    # Sanity check ratio accuracy
    expected_scaled_ratio = str(expected_supply_ratio).replace('.', '')
    assert str(expected_total_supply) == expected_scaled_ratio

    # Sanity check denomination size
    expected_scale = 28
    assert len(str(expected_total_supply)) == expected_scale
    assert len(str(expected_initial_supply)) == expected_scale
    assert len(str(expected_reward_supply)) == expected_scale

    # Use same precision as economics class
    with localcontext() as ctx:
        ctx.prec = TokenEconomics._precision

        # Sanity check expected testing outputs
        assert Decimal(expected_total_supply) / expected_initial_supply == expected_supply_ratio
        assert expected_reward_supply == expected_total_supply - expected_initial_supply
        assert reward_saturation * 365 * multiplier == expected_locked_periods_coefficient * (1 - multiplier)
        assert int(365 ** 2 * reward_saturation * halving / log(2) / (1-multiplier)) == expected_staking_coefficient

    # After sanity checking, assemble expected test deployment parameters
    expected_deployment_parameters = (24,       # Hours in single period
                                      768812,   # Staking coefficient (k2)
                                      365,      # Locked periods coefficient (k1)
                                      365,      # Max periods that will be additionally rewarded (awarded_periods)
                                      30,       # Min amount of periods during which tokens can be locked
                                      15000000000000000000000,    # min locked NuNits
                                      4000000000000000000000000,  # max locked NuNits
                                      2)        # Min worker periods
    #
    # Token Economics
    #

    # Check creation
    e = TokenEconomics()

    with localcontext() as ctx:
        ctx.prec = TokenEconomics._precision

        # Check that total_supply calculated correctly
        assert Decimal(e.erc20_total_supply) / e.initial_supply == expected_supply_ratio
        assert e.erc20_total_supply == expected_total_supply

        # Check reward rates
        initial_rate = Decimal((e.erc20_total_supply - e.initial_supply) * (e.locked_periods_coefficient + 365) / e.staking_coefficient)
        assert initial_rate == Decimal((e.initial_inflation * e.initial_supply) / 365)

        initial_rate_small = (e.erc20_total_supply - e.initial_supply) * e.locked_periods_coefficient / e.staking_coefficient
        assert Decimal(initial_rate_small) == Decimal(initial_rate / 2)

        # Check reward supply
        assert Decimal(LOG2 / (e.token_halving * 365) * (e.erc20_total_supply - e.initial_supply)) == initial_rate
        assert e.reward_supply == expected_total_supply - expected_initial_supply

        # Check deployment parameters
        assert e.staking_deployment_parameters == expected_deployment_parameters
        assert e.erc20_initial_supply == expected_initial_supply
        assert e.erc20_reward_supply == expected_reward_supply


def test_economic_parameter_aliases():

    e = TokenEconomics()

    assert e.locked_periods_coefficient == 365
    assert int(e.staking_coefficient) == 768812
    assert e.maximum_locked_periods == 365

    deployment_params = e.staking_deployment_parameters
    assert isinstance(deployment_params, tuple)
    for parameter in deployment_params:
        assert isinstance(parameter, int)
