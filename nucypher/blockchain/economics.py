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
from math import log


class Economics:
    def __init__(
            self,
            initial_supply=10**9,
            initial_inflation=1.0,
            T_half=2.0,
            T_sat=1.0,
            small_staker_multiplier=0.5) -> None:
        """
        Calculate parameters to use in token issuer from high-level
        human-understandable parameters

        :param initial_supply: coins at t=0,
        :param initial_inflation: inflation in day 1 expressed in units of year**-1
            e.g. 1/365 of all coins in day 1 is 1 year**-1
        :param T_half: time for inflation halving in years
        :param T_sat: "saturation" time - if staking is longer than T_sat, the
            reward doesn't get higher
        :param small_staker_multiplier: what fraction of max reward rate do we
            pay to those who are about to unlock coins
        """

        # Saving input in case we'll need it
        self.input_params = dict(
                initial_supply=initial_supply,
                initial_inflation=initial_inflation,
                T_half=T_half,
                T_sat=T_sat,
                small_staker_multiplier=small_staker_multiplier)

        # Formula used in smart contract

        # * @dev Formula for mining in one period
        # (totalSupply - currentSupply) * (lockedValue / totalLockedValue) * (k1 + allLockedPeriods) / k2
        # if allLockedPeriods > awardedPeriods then allLockedPeriods = awardedPeriods
        # @param _miningCoefficient Mining coefficient (k2)
        # @param _lockedPeriodsCoefficient Locked blocks coefficient (k1)

        self.total_supply = initial_supply * (1 + initial_inflation * T_half / log(2))

        # kappa * log(2) / T_half === (k1 + allLockedPeriods) / k2
        # but also
        # kappa = (small_staker_multiplier +
        #           (1 - small_staker_multiplier) * min(T, T1) / T1)

        # In Issuer.sol, allLockedPeriods is min(T, T1) days already

        self.miningCoefficient = \
            365 ** 2 * T_sat * T_half / log(2) / (1 - small_staker_multiplier)

        self.lockedPeriodsCoefficent = \
            365 * T_sat * small_staker_multiplier / (1 - small_staker_multiplier)

        self.awardedPeriods = T_sat * 365
