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
from constant_sorrow import constants

from nucypher.blockchain.eth.agents import AdjudicatorAgent, ContractAgency, NucypherTokenAgent, StakingEscrowAgent
from nucypher.blockchain.eth.deployers import (AdjudicatorDeployer, BaseContractDeployer, NucypherTokenDeployer,
                                               PolicyManagerDeployer, StakingEscrowDeployer)


def test_deploy_ethereum_contracts(testerchain,
                                   deployment_progress,
                                   test_registry):

    origin, *everybody_else = testerchain.client.accounts

    #
    # Nucypher Token
    #
    token_deployer = NucypherTokenDeployer(registry=test_registry, deployer_address=origin)
    assert token_deployer.deployer_address == origin

    with pytest.raises(BaseContractDeployer.ContractDeploymentError):
        assert token_deployer.contract_address is constants.CONTRACT_NOT_DEPLOYED
    assert not token_deployer.is_deployed()

    token_deployer.deploy(progress=deployment_progress)
    assert token_deployer.is_deployed()
    assert len(token_deployer.contract_address) == 42

    token_agent = NucypherTokenAgent(registry=test_registry)
    assert len(token_agent.contract_address) == 42
    assert token_agent.contract_address == token_deployer.contract_address

    another_token_agent = token_deployer.make_agent()
    assert len(another_token_agent.contract_address) == 42
    assert another_token_agent.contract_address == token_deployer.contract_address == token_agent.contract_address

    #
    # Policy Manager
    #
    policy_manager_deployer = PolicyManagerDeployer(
        registry=test_registry,
        deployer_address=origin)

    assert policy_manager_deployer.deployer_address == origin

    with pytest.raises(BaseContractDeployer.ContractDeploymentError):
        assert policy_manager_deployer.contract_address is constants.CONTRACT_NOT_DEPLOYED
    assert not policy_manager_deployer.is_deployed()

    policy_manager_deployer.deploy(progress=deployment_progress)
    assert policy_manager_deployer.is_deployed()
    assert len(policy_manager_deployer.contract_address) == 42

    policy_agent = policy_manager_deployer.make_agent()
    assert len(policy_agent.contract_address) == 42
    assert policy_agent.contract_address == policy_manager_deployer.contract_address

    another_policy_agent = policy_manager_deployer.make_agent()
    assert len(another_policy_agent.contract_address) == 42
    assert another_policy_agent.contract_address == policy_manager_deployer.contract_address == policy_agent.contract_address

    #
    # Adjudicator
    #
    adjudicator_deployer = AdjudicatorDeployer(
        registry=test_registry,
        deployer_address=origin)

    assert adjudicator_deployer.deployer_address == origin

    with pytest.raises(BaseContractDeployer.ContractDeploymentError):
        assert adjudicator_deployer.contract_address is constants.CONTRACT_NOT_DEPLOYED
    assert not adjudicator_deployer.is_deployed()

    adjudicator_deployer.deploy(progress=deployment_progress)
    assert adjudicator_deployer.is_deployed()
    assert len(adjudicator_deployer.contract_address) == 42

    adjudicator_agent = adjudicator_deployer.make_agent()
    assert len(adjudicator_agent.contract_address) == 42
    assert adjudicator_agent.contract_address == adjudicator_deployer.contract_address

    another_adjudicator_agent = AdjudicatorAgent(registry=test_registry)
    assert len(another_adjudicator_agent.contract_address) == 42
    assert another_adjudicator_agent.contract_address == adjudicator_deployer.contract_address == adjudicator_agent.contract_address

    # overall deployment steps must match aggregated individual expected number of steps
    all_deployment_transactions = token_deployer.deployment_steps + policy_manager_deployer.deployment_steps + \
                                  adjudicator_deployer.deployment_steps
    assert deployment_progress.num_steps == len(all_deployment_transactions)

    #
    # StakingEscrow
    #
    staking_escrow_deployer = StakingEscrowDeployer(
        registry=test_registry,
        deployer_address=origin)
    assert staking_escrow_deployer.deployer_address == origin

    with pytest.raises(BaseContractDeployer.ContractDeploymentError):
        assert staking_escrow_deployer.contract_address is constants.CONTRACT_NOT_DEPLOYED
    assert not staking_escrow_deployer.is_deployed()

    staking_escrow_deployer.deploy(progress=deployment_progress)
    assert staking_escrow_deployer.is_deployed()
    assert len(staking_escrow_deployer.contract_address) == 42

    staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=test_registry)
    assert len(staking_agent.contract_address) == 42
    assert staking_agent.contract_address == staking_escrow_deployer.contract_address

    another_staking_agent = staking_escrow_deployer.make_agent()
    assert len(another_staking_agent.contract_address) == 42
    assert another_staking_agent.contract_address == staking_escrow_deployer.contract_address == staking_agent.contract_address
