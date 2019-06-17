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
from constant_sorrow import constants

from nucypher.blockchain.eth.agents import NucypherTokenAgent, StakingEscrowAgent, Agency
from nucypher.blockchain.eth.deployers import (NucypherTokenDeployer,
                                               StakingEscrowDeployer,
                                               PolicyManagerDeployer,
                                               ContractDeployer, DispatcherDeployer)


@pytest.mark.slow()
def test_deploy_ethereum_contracts(testerchain):

    origin, *everybody_else = testerchain.w3.eth.accounts

    #
    # Nucypher Token
    #
    token_deployer = NucypherTokenDeployer(blockchain=testerchain, deployer_address=origin)
    assert token_deployer.deployer_address == origin

    with pytest.raises(ContractDeployer.ContractDeploymentError):
        assert token_deployer.contract_address is constants.CONTRACT_NOT_DEPLOYED
    assert not token_deployer.is_deployed

    token_deployer.deploy()
    assert token_deployer.is_deployed
    assert len(token_deployer.contract_address) == 42

    token_agent = NucypherTokenAgent(blockchain=testerchain)
    assert len(token_agent.contract_address) == 42
    assert token_agent.contract_address == token_deployer.contract_address

    another_token_agent = token_deployer.make_agent()
    assert len(another_token_agent.contract_address) == 42
    assert another_token_agent.contract_address == token_deployer.contract_address == token_agent.contract_address

    #
    # Staker Escrow
    #
    stakers_escrow_secret = os.urandom(DispatcherDeployer.DISPATCHER_SECRET_LENGTH)
    staking_escrow_deployer = StakingEscrowDeployer(
        blockchain=testerchain,
        deployer_address=origin)
    assert staking_escrow_deployer.deployer_address == origin

    with pytest.raises(ContractDeployer.ContractDeploymentError):
        assert staking_escrow_deployer.contract_address is constants.CONTRACT_NOT_DEPLOYED
    assert not staking_escrow_deployer.is_deployed

    staking_escrow_deployer.deploy(secret_hash=testerchain.w3.keccak(stakers_escrow_secret))
    assert staking_escrow_deployer.is_deployed
    assert len(staking_escrow_deployer.contract_address) == 42

    staking_agent = StakingEscrowAgent(blockchain=testerchain)
    assert len(staking_agent.contract_address) == 42
    assert staking_agent.contract_address == staking_escrow_deployer.contract_address

    another_staking_agent = staking_escrow_deployer.make_agent()
    assert len(another_staking_agent.contract_address) == 42
    assert another_staking_agent.contract_address == staking_escrow_deployer.contract_address == staking_agent.contract_address


    #
    # Policy Manager
    #
    policy_manager_secret = os.urandom(DispatcherDeployer.DISPATCHER_SECRET_LENGTH)
    policy_manager_deployer = PolicyManagerDeployer(
        blockchain=testerchain,
        deployer_address=origin)

    assert policy_manager_deployer.deployer_address == origin

    with pytest.raises(ContractDeployer.ContractDeploymentError):
        assert policy_manager_deployer.contract_address is constants.CONTRACT_NOT_DEPLOYED
    assert not policy_manager_deployer.is_deployed

    policy_manager_deployer.deploy(secret_hash=testerchain.w3.keccak(policy_manager_secret))
    assert policy_manager_deployer.is_deployed
    assert len(policy_manager_deployer.contract_address) == 42

    policy_agent = policy_manager_deployer.make_agent()
    assert len(policy_agent.contract_address) == 42
    assert policy_agent.contract_address == policy_manager_deployer.contract_address

    another_policy_agent = policy_manager_deployer.make_agent()
    assert len(another_policy_agent.contract_address) == 42
    assert another_policy_agent.contract_address == policy_manager_deployer.contract_address == policy_agent.contract_address
