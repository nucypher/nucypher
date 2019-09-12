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
from eth_utils import is_checksum_address

from nucypher.blockchain.eth.agents import WorkLockAgent, StakingEscrowAgent, ContractAgency
from nucypher.blockchain.eth.deployers import (
    WorkLockDeployer,
    NucypherTokenDeployer,
    StakingEscrowDeployer,
    PolicyManagerDeployer,
    AdjudicatorDeployer,
    UserEscrowProxyDeployer
)
from nucypher.blockchain.eth.registry import BaseContractRegistry
from nucypher.utilities.sandbox.constants import INSECURE_DEPLOYMENT_SECRET_HASH


def test_worklock_deployer(testerchain, test_registry, token_economics):
    origin = testerchain.etherbase_account

    token_deployer = NucypherTokenDeployer(deployer_address=origin, registry=test_registry)
    token_deployer.deploy()

    staking_escrow_deployer = StakingEscrowDeployer(deployer_address=origin, registry=test_registry)
    staking_escrow_deployer.deploy(secret_hash=INSECURE_DEPLOYMENT_SECRET_HASH)

    policy_manager_deployer = PolicyManagerDeployer(deployer_address=origin, registry=test_registry)
    policy_manager_deployer.deploy(secret_hash=INSECURE_DEPLOYMENT_SECRET_HASH)

    adjudicator_deployer = AdjudicatorDeployer(deployer_address=origin, registry=test_registry)
    adjudicator_deployer.deploy(secret_hash=INSECURE_DEPLOYMENT_SECRET_HASH)

    user_escrow_proxy_deployer = UserEscrowProxyDeployer(deployer_address=origin, registry=test_registry)
    user_escrow_proxy_deployer.deploy(secret_hash=INSECURE_DEPLOYMENT_SECRET_HASH)

    # Trying to get agent from registry before it's been published fails
    with pytest.raises(BaseContractRegistry.UnknownContract):
        WorkLockAgent(registry=test_registry)

    # Create WorkLock Deployer
    deployer = WorkLockDeployer(registry=test_registry,
                                economics=token_economics,
                                deployer_address=origin)

    # Deploy WorkLock
    deployment_receipts = deployer.deploy()
    assert len(deployment_receipts) == 2

    # Verify contract is bonded to escrow
    staking_escrow = ContractAgency.get_agent(StakingEscrowAgent, registry=test_registry)
    assert staking_escrow.contract.functions.workLock().call() == deployer.contract_address

    assert deployer.contract
    assert is_checksum_address(deployer.contract_address)
    assert deployer.contract.address == deployer.contract_address
    agent = WorkLockAgent(registry=test_registry)
    assert agent.contract_address == deployer.contract.address == deployer.contract_address
    assert WorkLockDeployer.contract_name in test_registry.read()
