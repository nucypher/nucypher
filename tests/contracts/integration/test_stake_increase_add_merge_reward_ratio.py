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
import pytest

from tests.contracts.integration.increase import check_rewards_ratios_after_increase


@pytest.mark.skip(reason="This test depicts the known issue related to increasing stake and is expected to fail "
                         "- see Issue #2691.")
def test_rewards_ratios_after_increase_via_merge(testerchain, agency, token_economics, test_registry):
    check_rewards_ratios_after_increase(testerchain, agency, token_economics, test_registry,
                                        increase_callable=_increase_stake_via_merge,
                                        skip_problematic_assertions_after_increase=False)


def _increase_stake_via_merge(i, staking_agent, lock_periods, amount, ursula4_tpower):
    # increase ursula4 stake by min staking amount via merge so that stake ratio of ursula1 or ursula2: ursula 4 is 1:2
    _ = staking_agent.lock_and_create(transacting_power=ursula4_tpower,
                                      amount=amount,
                                      lock_periods=lock_periods)
    substake_0 = staking_agent.get_substake_info(staker_address=ursula4_tpower.account, stake_index=0)
    substake_1 = staking_agent.get_substake_info(staker_address=ursula4_tpower.account, stake_index=1)
    assert substake_0.last_period == substake_1.last_period

    _ = staking_agent.merge_stakes(transacting_power=ursula4_tpower,
                                   stake_index_1=0,
                                   stake_index_2=1)
    print(f">>> Increase ursula4 NU via merge in period {i}")
