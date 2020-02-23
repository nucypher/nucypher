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
import os

import pytest
from eth_utils import keccak
from constant_sorrow import constants

from nucypher.blockchain.eth.actors import Staker
from nucypher.blockchain.eth.agents import NucypherTokenAgent, StakingEscrowAgent, ContractAgency
from nucypher.blockchain.eth.deployers import (NucypherTokenDeployer,
                                               StakingEscrowDeployer,
                                               PolicyManagerDeployer,
                                               AdjudicatorDeployer,
                                               BaseContractDeployer,
                                               DispatcherDeployer)
from nucypher.crypto.powers import TransactingPower
from nucypher.utilities.sandbox.blockchain import token_airdrop
from nucypher.utilities.sandbox.constants import DEVELOPMENT_TOKEN_AIRDROP_AMOUNT, INSECURE_DEVELOPMENT_PASSWORD


@pytest.mark.slow()
def test_deploy_idle_network(testerchain, deployment_progress, test_registry):
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

    token_agent = NucypherTokenAgent(registry=test_registry)
    assert token_agent.contract_address == token_deployer.contract_address

    another_token_agent = token_deployer.make_agent()
    assert another_token_agent.contract_address == token_deployer.contract_address == token_agent.contract_address

    #
    # StakingEscrow - in IDLE mode, i.e. without activation steps (approve_funding and initialize)
    #
    stakers_escrow_secret = os.urandom(DispatcherDeployer._secret_length)
    staking_escrow_deployer = StakingEscrowDeployer(registry=test_registry, deployer_address=origin)
    assert staking_escrow_deployer.deployer_address == origin

    with pytest.raises(BaseContractDeployer.ContractDeploymentError):
        assert staking_escrow_deployer.contract_address is constants.CONTRACT_NOT_DEPLOYED
    assert not staking_escrow_deployer.is_deployed()

    staking_escrow_deployer.deploy(secret_hash=keccak(stakers_escrow_secret),
                                   progress=deployment_progress,
                                   deployment_mode=constants.IDLE)
    assert staking_escrow_deployer.is_deployed()

    staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=test_registry)
    assert staking_agent.contract_address == staking_escrow_deployer.contract_address

    # The contract has no tokens yet
    assert token_agent.get_balance(staking_agent.contract_address) == 0

    #
    # Policy Manager
    #
    policy_manager_secret = os.urandom(DispatcherDeployer._secret_length)
    policy_manager_deployer = PolicyManagerDeployer(registry=test_registry, deployer_address=origin)

    assert policy_manager_deployer.deployer_address == origin

    with pytest.raises(BaseContractDeployer.ContractDeploymentError):
        assert policy_manager_deployer.contract_address is constants.CONTRACT_NOT_DEPLOYED
    assert not policy_manager_deployer.is_deployed()

    policy_manager_deployer.deploy(secret_hash=keccak(policy_manager_secret), progress=deployment_progress)
    assert policy_manager_deployer.is_deployed()

    policy_agent = policy_manager_deployer.make_agent()
    assert policy_agent.contract_address == policy_manager_deployer.contract_address

    #
    # Adjudicator
    #
    adjudicator_secret = os.urandom(DispatcherDeployer._secret_length)
    adjudicator_deployer = AdjudicatorDeployer(registry=test_registry, deployer_address=origin)

    assert adjudicator_deployer.deployer_address == origin

    with pytest.raises(BaseContractDeployer.ContractDeploymentError):
        assert adjudicator_deployer.contract_address is constants.CONTRACT_NOT_DEPLOYED
    assert not adjudicator_deployer.is_deployed()

    adjudicator_deployer.deploy(secret_hash=keccak(adjudicator_secret), progress=deployment_progress)
    assert adjudicator_deployer.is_deployed()

    adjudicator_agent = adjudicator_deployer.make_agent()
    assert adjudicator_agent.contract_address == adjudicator_deployer.contract_address


