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
from nucypher.blockchain.eth.agents import StakingEscrowAgent, NucypherTokenAgent, PolicyManagerAgent, ContractAgency
from nucypher.blockchain.eth.signers.software import Web3Signer
from nucypher.crypto.powers import TransactingPower

# Experimental max error
from tests.contracts.integration.utils import prepare_staker, commit_to_next_period

MAX_ERROR_FIRST_PHASE = 1e-20
MAX_ERROR_SECOND_PHASE = 5e-3
MAX_PERIODS_SECOND_PHASE = 100


@pytest.mark.nightly
def test_reward(testerchain, agency, token_economics, test_registry):
    testerchain.time_travel(hours=1)
    staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=test_registry)
    token_agent = ContractAgency.get_agent(NucypherTokenAgent, registry=test_registry)
    _policy_agent = ContractAgency.get_agent(PolicyManagerAgent, registry=test_registry)
    origin = testerchain.etherbase_account
    ursula1 = testerchain.ursula_account(0)
    ursula2 = testerchain.ursula_account(1)
    origin_tpower = TransactingPower(signer=Web3Signer(client=testerchain.client), account=origin)
    ursula1_tpower = TransactingPower(signer=Web3Signer(client=testerchain.client), account=ursula1)
    ursula2_tpower = TransactingPower(signer=Web3Signer(client=testerchain.client), account=ursula2)

    # Prepare one staker
    prepare_staker(origin_tpower, staking_agent, token_agent, token_economics, ursula1, ursula1_tpower, token_economics.minimum_allowed_locked)
    prepare_staker(origin_tpower, staking_agent, token_agent, token_economics, ursula2, ursula2_tpower,
                    token_economics.minimum_allowed_locked * 3)  # 3x min

    ursulas_tpowers = [ursula1_tpower, ursula2_tpower]
    commit_to_next_period(staking_agent, ursulas_tpowers)
    testerchain.time_travel(periods=1)
    commit_to_next_period(staking_agent, ursulas_tpowers)

    assert staking_agent.calculate_staking_reward(staker_address=ursula1) == 0
    assert staking_agent.calculate_staking_reward(staker_address=ursula2) == 0

    # Get a reward
    switch = token_economics.first_phase_final_period()
    for i in range(1, switch + MAX_PERIODS_SECOND_PHASE):
        testerchain.time_travel(periods=1)
        commit_to_next_period(staking_agent, ursulas_tpowers)

        ursula1_rewards = staking_agent.calculate_staking_reward(staker_address=ursula1)
        ursula2_rewards = staking_agent.calculate_staking_reward(staker_address=ursula2)
        calculations_reward = token_economics.cumulative_rewards_at_period(i)
        error = abs((ursula1_rewards + ursula2_rewards - calculations_reward) / calculations_reward)
        if i <= switch:
            assert error < MAX_ERROR_FIRST_PHASE
        else:
            assert error < MAX_ERROR_SECOND_PHASE
