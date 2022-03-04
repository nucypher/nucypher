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

from nucypher.blockchain.eth.agents import (
    ContractAgency,
    NucypherTokenAgent,
)
from nucypher.blockchain.eth.deployers import (
    BaseContractDeployer,
    NucypherTokenDeployer,
)
from nucypher.blockchain.eth.signers.software import Web3Signer
from nucypher.crypto.powers import TransactingPower


@pytest.mark.skip()
def test_deploy_ethereum_contracts(testerchain,
                                   deployment_progress,
                                   test_registry):

    origin, *everybody_else = testerchain.client.accounts
    tpower = TransactingPower(account=origin,
                              signer=Web3Signer(testerchain.client))

    #
    # Nucypher Token
    #
    token_deployer = NucypherTokenDeployer(registry=test_registry)

    with pytest.raises(BaseContractDeployer.ContractDeploymentError):
        assert token_deployer.contract_address is constants.CONTRACT_NOT_DEPLOYED
    assert not token_deployer.is_deployed()

    token_deployer.deploy(progress=deployment_progress, transacting_power=tpower)
    assert token_deployer.is_deployed()
    assert len(token_deployer.contract_address) == 42

    token_agent = NucypherTokenAgent(registry=test_registry)
    assert len(token_agent.contract_address) == 42
    assert token_agent.contract_address == token_deployer.contract_address

    another_token_agent = token_deployer.make_agent()
    assert len(another_token_agent.contract_address) == 42
    assert another_token_agent.contract_address == token_deployer.contract_address == token_agent.contract_address

    #
    # StakingEscrowStub
    #
    staking_escrow_deployer = StakingEscrowDeployer(registry=test_registry)

    with pytest.raises(BaseContractDeployer.ContractDeploymentError):
        assert staking_escrow_deployer.contract_address is constants.CONTRACT_NOT_DEPLOYED
    assert not staking_escrow_deployer.is_deployed()

    staking_escrow_deployer.deploy(progress=deployment_progress, transacting_power=tpower)
    assert not staking_escrow_deployer.is_deployed()
    assert len(staking_escrow_deployer.contract_address) == 42

    # StakingEscrow
    staking_escrow_deployer = StakingEscrowDeployer(registry=test_registry)

    with pytest.raises(BaseContractDeployer.ContractDeploymentError):
        assert staking_escrow_deployer.contract_address is constants.CONTRACT_NOT_DEPLOYED
    assert not staking_escrow_deployer.is_deployed()

    staking_escrow_deployer.deploy(progress=deployment_progress,
                                   deployment_mode=constants.FULL,
                                   transacting_power=tpower)
    assert staking_escrow_deployer.is_deployed()
    assert len(staking_escrow_deployer.contract_address) == 42

    staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=test_registry)
    assert len(staking_agent.contract_address) == 42
    assert staking_agent.contract_address == staking_escrow_deployer.contract_address

    another_staking_agent = staking_escrow_deployer.make_agent()
    assert len(another_staking_agent.contract_address) == 42
    assert another_staking_agent.contract_address == staking_escrow_deployer.contract_address == staking_agent.contract_address

    # overall deployment steps must match aggregated individual expected number of steps
    all_deployment_transactions = token_deployer.deployment_steps + staking_escrow_deployer.init_steps + \
                                  staking_escrow_deployer.deployment_steps
    assert deployment_progress.num_steps == len(all_deployment_transactions)
