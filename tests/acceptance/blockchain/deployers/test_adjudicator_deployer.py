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

from nucypher.blockchain.eth.agents import AdjudicatorAgent
from nucypher.blockchain.eth.deployers import (
    AdjudicatorDeployer,
    NucypherTokenDeployer,
    StakingEscrowDeployer,
)


def test_adjudicator_deployer(testerchain,
                              token_economics,
                              deployment_progress,
                              test_registry):

    origin = testerchain.etherbase_account

    token_deployer = NucypherTokenDeployer(deployer_address=origin, registry=test_registry)
    token_deployer.deploy()

    deployer = AdjudicatorDeployer(deployer_address=origin, registry=test_registry)
    deployment_receipts = deployer.deploy(progress=deployment_progress)

    # deployment steps must match expected number of steps
    assert deployment_progress.num_steps == len(deployer.deployment_steps) == len(deployment_receipts) == 2

    for step in deployer.deployment_steps:
        assert deployment_receipts[step]['status'] == 1

    # Create an AdjudicatorAgent instance
    adjudicator_agent = deployer.make_agent()

    # Check default Adjudicator deployment parameters
    assert adjudicator_agent.hash_algorithm == token_economics.hash_algorithm
    assert adjudicator_agent.base_penalty == token_economics.base_penalty
    assert adjudicator_agent.penalty_history_coefficient == token_economics.penalty_history_coefficient
    assert adjudicator_agent.percentage_penalty_coefficient == token_economics.percentage_penalty_coefficient
    assert adjudicator_agent.reward_coefficient == token_economics.reward_coefficient

    # Retrieve the AdjudicatorAgent singleton
    some_policy_agent = AdjudicatorAgent(registry=test_registry)
    assert adjudicator_agent == some_policy_agent  # __eq__

    # Compare the contract address for equality
    assert adjudicator_agent.contract_address == some_policy_agent.contract_address
