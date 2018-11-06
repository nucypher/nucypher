"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""
import os

import pytest
from constant_sorrow import constants

from nucypher.blockchain.eth.agents import NucypherTokenAgent, MinerAgent
from nucypher.blockchain.eth.constants import DISPATCHER_SECRET_LENGTH
from nucypher.blockchain.eth.deployers import (NucypherTokenDeployer,
                                               MinerEscrowDeployer,
                                               PolicyManagerDeployer,
                                               ContractDeployer)


@pytest.mark.slow()
def test_deploy_ethereum_contracts(testerchain):

    origin, *everybody_else = testerchain.interface.w3.eth.accounts

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
    # Miner Escrow
    #
    miners_escrow_secret = os.urandom(DISPATCHER_SECRET_LENGTH)
    miner_escrow_deployer = MinerEscrowDeployer(
        blockchain=testerchain,
        deployer_address=origin,
        secret_hash=testerchain.interface.w3.sha3(miners_escrow_secret))
    assert miner_escrow_deployer.deployer_address == origin

    with pytest.raises(ContractDeployer.ContractDeploymentError):
        assert miner_escrow_deployer.contract_address is constants.CONTRACT_NOT_DEPLOYED
    assert not miner_escrow_deployer.is_deployed

    miner_escrow_deployer.deploy()
    assert miner_escrow_deployer.is_deployed
    assert len(miner_escrow_deployer.contract_address) == 42

    miner_agent = MinerAgent(blockchain=testerchain)
    assert len(miner_agent.contract_address) == 42
    assert miner_agent.contract_address == miner_escrow_deployer.contract_address

    another_miner_agent = miner_escrow_deployer.make_agent()
    assert len(another_miner_agent.contract_address) == 42
    assert another_miner_agent.contract_address == miner_escrow_deployer.contract_address == miner_agent.contract_address


    #
    # Policy Manager
    #
    policy_manager_secret = os.urandom(DISPATCHER_SECRET_LENGTH)
    policy_manager_deployer = PolicyManagerDeployer(
        blockchain=testerchain,
        deployer_address=origin,
        secret_hash=testerchain.interface.w3.sha3(policy_manager_secret))
    assert policy_manager_deployer.deployer_address == origin

    with pytest.raises(ContractDeployer.ContractDeploymentError):
        assert policy_manager_deployer.contract_address is constants.CONTRACT_NOT_DEPLOYED
    assert not policy_manager_deployer.is_deployed

    policy_manager_deployer.deploy()
    assert policy_manager_deployer.is_deployed
    assert len(policy_manager_deployer.contract_address) == 42

    policy_agent = policy_manager_deployer.make_agent()
    assert len(policy_agent.contract_address) == 42
    assert policy_agent.contract_address == policy_manager_deployer.contract_address

    another_policy_agent = policy_manager_deployer.make_agent()
    assert len(another_policy_agent.contract_address) == 42
    assert another_policy_agent.contract_address == policy_manager_deployer.contract_address == policy_agent.contract_address
