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
def test_rewards_ratios_after_increase(testerchain, agency, token_economics, test_registry):
    check_rewards_ratios_after_increase(testerchain, agency, token_economics, test_registry,
                                        increase_callable=_increase_stake,
                                        skip_problematic_assertions_after_increase=False)


def _increase_stake(i, staking_agent, lock_periods, amount, ursula4_tpower):
    # increase ursula4 stake by min staking amount so that stake ratio of ursula1 or ursula2: ursula 4 is 1:2
    staking_agent.lock_and_increase(transacting_power=ursula4_tpower,
                                    amount=amount,
                                    stake_index=0)
    print(f">>> Increase ursula4 NU in period {i}")
