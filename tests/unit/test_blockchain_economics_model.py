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

from nucypher.blockchain.economics import LOG2, StandardTokenEconomics


def test_rough_economics():
    """
    Formula for staking in one period:
    (totalSupply - currentSupply) * (lockedValue / totalLockedValue) * (k1 + allLockedPeriods) / d / k2

    d - Coefficient which modifies the rate at which the maximum issuance decays
    k1 - Numerator of the locking duration coefficient
    k2 - Denominator of the locking duration coefficient

    if allLockedPeriods > awarded_periods then allLockedPeriods = awarded_periods
    kappa * log(2) / halving_delay === (k1 + allLockedPeriods) / d / k2

    kappa = small_stake_multiplier + (1 - small_stake_multiplier) * min(T, T1) / T1
    where allLockedPeriods == min(T, T1)
    """

    e = StandardTokenEconomics(initial_supply=int(1e9),
                               first_phase_supply=1829579800,
                               first_phase_duration=5,
                               decay_half_life=2,
                               reward_saturation=1,
                               small_stake_multiplier=Decimal(0.5))

    assert float(round(e.erc20_total_supply / Decimal(1e9), 2)) == 3.89  # As per economics paper

    # Check that we have correct numbers in day 1 of the second phase
    initial_rate = (e.erc20_total_supply - int(e.first_phase_total_supply)) \
        * (e.lock_duration_coefficient_1 + 365) \
        / (e.issuance_decay_coefficient * e.lock_duration_coefficient_2)
    assert int(initial_rate) == int(e.first_phase_max_issuance)

    initial_rate_small = (e.erc20_total_supply - int(e.first_phase_total_supply))\
        * e.lock_duration_coefficient_1 \
        / (e.issuance_decay_coefficient * e.lock_duration_coefficient_2)
    assert int(initial_rate_small) == int(initial_rate / 2)

    # Sanity check that total and reward supply calculated correctly
    assert int(LOG2 / (e.token_halving * 365) * (e.erc20_total_supply - int(e.first_phase_total_supply))) == int(initial_rate)
    assert int(e.reward_supply) == int(e.erc20_total_supply - Decimal(int(1e9)))

    with localcontext() as ctx:  # TODO: Needs follow up - why the sudden failure (python 3.8.0)?
        ctx.prec = 18  # Perform a high precision calculation
        # Sanity check for lock_duration_coefficient_1 (k1), issuance_decay_coefficient (d) and lock_duration_coefficient_2 (k2)
        expected = e.lock_duration_coefficient_1 * e.token_halving
        result = e.issuance_decay_coefficient * e.lock_duration_coefficient_2 * LOG2 * e.small_stake_multiplier / 365
        assert expected == result


def test_economic_parameter_aliases():

    e = StandardTokenEconomics()

    assert e.lock_duration_coefficient_1 == 365
    assert e.lock_duration_coefficient_2 == 2 * 365
    assert int(e.issuance_decay_coefficient) == 1053
    assert e.maximum_rewarded_periods == 365

    deployment_params = e.staking_deployment_parameters
    assert isinstance(deployment_params, tuple)
    for parameter in deployment_params:
        assert isinstance(parameter, int)
