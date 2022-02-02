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
from nucypher.blockchain.economics import EconomicsFactory, Economics
from nucypher.blockchain.eth.agents import WorkLockAgent
from nucypher.blockchain.eth.constants import WORKLOCK_CONTRACT_NAME
from nucypher.blockchain.eth.deployers import WorklockDeployer


@pytest.fixture(scope='module')
def baseline_deployment(staking_escrow_stub_deployer, transacting_power):
    staking_escrow_stub_deployer.deploy(deployment_mode=constants.INIT, transacting_power=transacting_power)


@pytest.fixture(scope="module")
def worklock_deployer(baseline_deployment,
                      testerchain,
                      test_registry,
                      application_economics):
    worklock_deployer = WorklockDeployer(registry=test_registry, economics=application_economics)
    return worklock_deployer


@pytest.mark.skip()
def test_worklock_deployment(worklock_deployer,
                             baseline_deployment,
                             staking_escrow_stub_deployer,
                             deployment_progress,
                             test_registry,
                             testerchain,
                             transacting_power):

    # Deploy
    assert worklock_deployer.contract_name == WORKLOCK_CONTRACT_NAME
    deployment_receipts = worklock_deployer.deploy(progress=deployment_progress,
                                                   transacting_power=transacting_power)    # < ---- DEPLOY

    # deployment steps must match expected number of steps
    steps = worklock_deployer.deployment_steps
    assert deployment_progress.num_steps == len(steps) == len(deployment_receipts) == 3

    # Ensure every step is successful
    for step_title in steps:
        assert deployment_receipts[step_title]['status'] == 1

    # Ensure the correct staking escrow address is set
    staking_escrow_address = worklock_deployer.contract.functions.escrow().call()
    assert staking_escrow_stub_deployer.contract_address == staking_escrow_address


@pytest.mark.skip()
def test_make_agent(worklock_deployer, test_registry):

    agent = worklock_deployer.make_agent()

    # Retrieve the PolicyManagerAgent singleton
    another_worklock_agent = WorkLockAgent(registry=test_registry)
    assert agent == another_worklock_agent  # __eq__

    # Compare the contract address for equality
    assert agent.contract_address == another_worklock_agent.contract_address


@pytest.mark.skip()
def test_deployment_parameters(worklock_deployer, test_registry, application_economics):

    # Ensure restoration of deployment parameters
    agent = worklock_deployer.make_agent()
    params = agent.worklock_parameters()
    supply, start, end, end_cancellation, boost, locktime, min_bid = params
    assert application_economics.worklock_supply == supply
    assert application_economics.bidding_start_date == start
    assert application_economics.bidding_end_date == end
    assert application_economics.cancellation_end_date == end_cancellation
    assert application_economics.worklock_boosting_refund_rate == boost
    assert application_economics.worklock_commitment_duration == locktime
    assert application_economics.worklock_min_allowed_bid == min_bid
