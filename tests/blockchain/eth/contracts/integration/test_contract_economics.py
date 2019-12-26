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
from nucypher.crypto.powers import TransactingPower
from nucypher.utilities.sandbox.constants import INSECURE_DEVELOPMENT_PASSWORD


# Experimental max error
MAX_ERROR = 0.0004751
MAX_PERIODS = 100


@pytest.mark.slow
def test_reward(testerchain, agency, token_economics, mock_transacting_power_activation):
    testerchain.time_travel(hours=1)
    token_agent, staking_agent, _policy_agent = agency
    origin = testerchain.etherbase_account
    ursula = testerchain.ursula_account(0)

    # Prepare one staker
    _txhash = token_agent.transfer(amount=token_economics.minimum_allowed_locked,
                                   target_address=ursula,
                                   sender_address=origin)
    mock_transacting_power_activation(account=ursula, password=INSECURE_DEVELOPMENT_PASSWORD)
    _txhash = token_agent.approve_transfer(amount=token_economics.minimum_allowed_locked,
                                           target_address=staking_agent.contract_address,
                                           sender_address=ursula)
    _txhash = staking_agent.deposit_tokens(amount=token_economics.minimum_allowed_locked,
                                           lock_periods=100 * token_economics.maximum_rewarded_periods,
                                           sender_address=ursula)
    _txhash = staking_agent.set_worker(staker_address=ursula, worker_address=ursula)
    _txhash = staking_agent.set_restaking(staker_address=ursula, value=False)

    # Get a reward for one period
    _txhash = staking_agent.confirm_activity(worker_address=ursula)
    testerchain.time_travel(periods=1)
    _txhash = staking_agent.confirm_activity(worker_address=ursula)
    assert staking_agent.calculate_staking_reward(staker_address=ursula) == 0
    testerchain.time_travel(periods=1)
    _txhash = staking_agent.confirm_activity(worker_address=ursula)

    contract_reward = staking_agent.calculate_staking_reward(staker_address=ursula)
    calculations_reward = token_economics.cumulative_rewards_at_period(1)
    error = (contract_reward - calculations_reward) / calculations_reward
    assert error > 0
    assert error < MAX_ERROR

    # Get a reward for other periods
    for i in range(1, MAX_PERIODS):
        testerchain.time_travel(periods=1)
        _txhash = staking_agent.confirm_activity(worker_address=ursula)
        contract_reward = staking_agent.calculate_staking_reward(staker_address=ursula)
        calculations_reward = token_economics.cumulative_rewards_at_period(i + 1)
        next_error = (contract_reward - calculations_reward) / calculations_reward
        assert next_error > 0
        assert next_error < error
        error = next_error
