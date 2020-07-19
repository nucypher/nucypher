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

from tests.constants import INSECURE_DEVELOPMENT_PASSWORD

# Experimental max error
MAX_ERROR_FIRST_PHASE = 1e-20
MAX_ERROR_SECOND_PHASE = 3e-5
MAX_PERIODS_SECOND_PHASE = 100


@pytest.mark.nightly
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
                                           spender_address=staking_agent.contract_address,
                                           sender_address=ursula)
    _txhash = staking_agent.deposit_tokens(amount=token_economics.minimum_allowed_locked,
                                           lock_periods=100 * token_economics.maximum_rewarded_periods,
                                           sender_address=ursula,
                                           staker_address=ursula)

    _txhash = staking_agent.bond_worker(staker_address=ursula, worker_address=ursula)
    _txhash = staking_agent.set_restaking(staker_address=ursula, value=False)

    _txhash = staking_agent.commit_to_next_period(worker_address=ursula)
    testerchain.time_travel(periods=1)
    _txhash = staking_agent.commit_to_next_period(worker_address=ursula)
    assert staking_agent.calculate_staking_reward(staker_address=ursula) == 0

    # Get a reward
    switch = token_economics.first_phase_final_period()
    for i in range(1, switch + MAX_PERIODS_SECOND_PHASE):
        testerchain.time_travel(periods=1)
        _txhash = staking_agent.commit_to_next_period(worker_address=ursula)
        contract_reward = staking_agent.calculate_staking_reward(staker_address=ursula)
        calculations_reward = token_economics.cumulative_rewards_at_period(i)
        error = abs((contract_reward - calculations_reward) / calculations_reward)
        if i <= switch:
            assert error < MAX_ERROR_FIRST_PHASE
        else:
            assert error < MAX_ERROR_SECOND_PHASE
