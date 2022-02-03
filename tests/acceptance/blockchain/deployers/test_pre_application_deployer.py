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

from nucypher.blockchain.eth.agents import WorkLockAgent, PREApplicationAgent
from nucypher.blockchain.eth.constants import PRE_APPLICATION_CONTRACT_NAME
from nucypher.blockchain.eth.deployers import PREApplicationDeployer


@pytest.fixture(scope="module")
def pre_application_deployer(testerchain,
                             test_registry,
                             application_economics,
                             threshold_staking):
    pre_application_deployer = PREApplicationDeployer(staking_interface=threshold_staking.address,
                                                      registry=test_registry,
                                                      economics=application_economics)
    return pre_application_deployer


def test_pre_application_deployment(pre_application_deployer,
                                    deployment_progress,
                                    test_registry,
                                    testerchain,
                                    transacting_power,
                                    threshold_staking):

    # Deploy
    assert pre_application_deployer.contract_name == PRE_APPLICATION_CONTRACT_NAME
    deployment_receipts = pre_application_deployer.deploy(progress=deployment_progress,
                                                          transacting_power=transacting_power)    # < ---- DEPLOY

    # deployment steps must match expected number of steps
    steps = pre_application_deployer.deployment_steps
    assert deployment_progress.num_steps == len(steps) == len(deployment_receipts) == 1

    # Ensure every step is successful
    for step_title in steps:
        assert deployment_receipts[step_title]['status'] == 1

    # Ensure the correct staking escrow address is set
    threshold_staking_address = pre_application_deployer.contract.functions.tStaking().call()
    assert threshold_staking.address == threshold_staking_address


def test_make_agent(pre_application_deployer, test_registry):

    agent = pre_application_deployer.make_agent()

    another_application_agent = PREApplicationAgent(registry=test_registry)
    assert agent == another_application_agent  # __eq__

    # Compare the contract address for equality
    assert agent.contract_address == another_application_agent.contract_address


def test_deployment_parameters(pre_application_deployer, test_registry, application_economics):

    # Ensure restoration of deployment parameters
    agent = pre_application_deployer.make_agent()
    assert agent.get_min_authorization() == application_economics.min_authorization
    assert agent.get_min_operator_seconds() == application_economics.min_operator_seconds
