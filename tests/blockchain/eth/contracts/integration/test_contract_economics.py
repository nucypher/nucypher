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


# Experimental max error
MAX_ERROR = 0.0004751
MAX_PERIODS = 100


@pytest.mark.slow
def test_reward(testerchain, three_agents, token_economics):
    testerchain.time_travel(hours=1)
    token_agent, miner_agent, _policy_agent = three_agents
    origin = testerchain.etherbase_account
    ursula = testerchain.ursula_account(0)

    # Prepare one staker
    _txhash = token_agent.transfer(amount=token_economics.minimum_allowed_locked,
                                   target_address=ursula,
                                   sender_address=origin)
    _txhash = token_agent.approve_transfer(amount=token_economics.minimum_allowed_locked,
                                           target_address=miner_agent.contract_address,
                                           sender_address=ursula)
    _txhash = miner_agent.deposit_tokens(amount=token_economics.minimum_allowed_locked,
                                         lock_periods=100 * token_economics.maximum_locked_periods,
                                         sender_address=ursula)

    # Get a reward for one period
    _txhash = miner_agent.confirm_activity(node_address=ursula)
    testerchain.time_travel(periods=1)
    _txhash = miner_agent.confirm_activity(node_address=ursula)
    assert miner_agent.calculate_staking_reward(checksum_address=ursula) == 0
    testerchain.time_travel(periods=1)
    _txhash = miner_agent.confirm_activity(node_address=ursula)

    contract_reward = miner_agent.calculate_staking_reward(checksum_address=ursula)
    calculations_reward = token_economics.cumulative_rewards_at_period(1)
    error = (contract_reward - calculations_reward) / calculations_reward
    assert error < MAX_ERROR

    # Get a reward for ten periods
    for i in range(1, MAX_PERIODS):
        testerchain.time_travel(periods=1)
        _txhash = miner_agent.confirm_activity(node_address=ursula)
        contract_reward = miner_agent.calculate_staking_reward(checksum_address=ursula)
        calculations_reward = token_economics.cumulative_rewards_at_period(i + 1)
        next_error = (contract_reward - calculations_reward) / calculations_reward
        assert next_error < error
        error = next_error
