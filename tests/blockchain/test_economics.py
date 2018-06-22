from nucypher.blockchain.economics import Economics
from math import log


def test_economics():
    e = Economics(
            initial_supply=10**9, initial_inflation=1.0, T_half=2.0, T_sat=1.0,
            small_staker_multiplier=0.5)

    assert round(e.total_supply / 1e9, 2) == 3.89  # As per economics paper

    # * @dev Formula for mining in one period
    # (totalSupply - currentSupply) * (lockedValue / totalLockedValue) * (k1 + allLockedPeriods) / k2
    # if allLockedPeriods > awardedPeriods then allLockedPeriods = awardedPeriods
    # @param _miningCoefficient Mining coefficient (k2)
    # @param _lockedPeriodsCoefficient Locked blocks coefficient (k1)

    # Check that we have correct numbers in day 1
    initial_rate = \
        (e.total_supply - e.input_params['initial_supply']) * \
        (e.lockedPeriodsCoefficent + 365) / e.miningCoefficient

    assert round(initial_rate) == \
        round(e.input_params['initial_inflation'] * e.input_params['initial_supply'] / 365)

    initial_rate_small = \
        (e.total_supply - e.input_params['initial_supply']) * \
        e.lockedPeriodsCoefficent / e.miningCoefficient

    assert round(initial_rate_small) == round(initial_rate / 2)

    # Sanity check that total_supply calculated correctly
    assert round(
        log(2) / (e.input_params['T_half'] * 365) *
        (e.total_supply - e.input_params['initial_supply'])) == \
        round(initial_rate)
