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
from eth_utils import keccak

from nucypher.blockchain.eth.agents import WorkLockAgent, ContractAgency
from nucypher.blockchain.eth.constants import WORKLOCK_CONTRACT_NAME
from nucypher.blockchain.eth.deployers import WorklockDeployer, StakingInterfaceDeployer, AdjudicatorDeployer
from nucypher.utilities.sandbox.constants import STAKING_ESCROW_DEPLOYMENT_SECRET, INSECURE_DEPLOYMENT_SECRET_HASH, \
    POLICY_MANAGER_DEPLOYMENT_SECRET


@pytest.fixture(scope="module")
def worklock_deployer(staking_escrow_deployer,
                      policy_manager_deployer,
                      adjudicator_deployer,
                      staking_interface_deployer,
                      testerchain,
                      test_registry,
                      token_economics):

    # Set the stage
    adjudicator_deployer.deploy(secret_hash=INSECURE_DEPLOYMENT_SECRET_HASH)
    staking_interface_deployer.deploy(secret_hash=INSECURE_DEPLOYMENT_SECRET_HASH)

    # Now the worklock itself
    worklock_deployer = WorklockDeployer(registry=test_registry,
                                         economics=token_economics,
                                         deployer_address=testerchain.etherbase_account)
    return worklock_deployer


def test_worklock_deployment(worklock_deployer, staking_escrow_deployer, deployment_progress):

    assert worklock_deployer.contract_name == WORKLOCK_CONTRACT_NAME

    deployment_receipts = worklock_deployer.deploy(progress=deployment_progress)

    # deployment steps must match expected number of steps
    steps = worklock_deployer.deployment_steps
    assert deployment_progress.num_steps == len(steps) == len(deployment_receipts) == 2

    # Ensure every step is successful
    for step_title in steps:
        assert deployment_receipts[step_title]['status'] == 1

    # Ensure the correct staking escrow address is set
    staking_escrow_address = worklock_deployer.contract.functions.escrow().call()
    assert staking_escrow_deployer.contract_address == staking_escrow_address


def test_make_agent(worklock_deployer, test_registry):

    agent = worklock_deployer.make_agent()

    # Retrieve the PolicyManagerAgent singleton
    another_worklock_agent = WorkLockAgent(registry=test_registry)
    assert agent == another_worklock_agent  # __eq__

    # Compare the contract address for equality
    assert agent.contract_address == another_worklock_agent.contract_address


def test_deployment_parameters(policy_manager_deployer, staking_escrow_deployer, test_registry):

    escrow_address = policy_manager_deployer.contract.functions.escrow().call()
    assert staking_escrow_deployer.contract_address == escrow_address

    worklock_agent = ContractAgency.get_agent(WorkLockAgent, registry=test_registry)
    seconds_per_period = worklock_agent.worklock_parameters()[0]
