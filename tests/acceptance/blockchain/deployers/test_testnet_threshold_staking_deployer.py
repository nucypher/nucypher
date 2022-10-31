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

from nucypher.blockchain.eth.agents import TestnetThresholdStakingAgent
from nucypher.blockchain.eth.constants import TESTNET_THRESHOLD_STAKING_CONTRACT_NAME
from nucypher.blockchain.eth.deployers import TestnetThresholdStakingDeployer


@pytest.fixture(scope="module")
def testnet_staking_deployer(testerchain,
                             test_registry,
                             application_economics,
                             threshold_staking):
    testnet_staking_deployer = TestnetThresholdStakingDeployer(registry=test_registry, economics=application_economics)
    return testnet_staking_deployer


def test_testnet_staking_deployment(testnet_staking_deployer,
                                    test_registry,
                                    testerchain,
                                    transacting_power,
                                    threshold_staking):

    # Deploy
    assert testnet_staking_deployer.contract_name == TESTNET_THRESHOLD_STAKING_CONTRACT_NAME
    deployment_receipts = testnet_staking_deployer.deploy(transacting_power=transacting_power)    # < ---- DEPLOY

    # deployment steps must match expected number of steps
    steps = testnet_staking_deployer.deployment_steps
    assert len(steps) == len(deployment_receipts) == 1

    # Ensure every step is successful
    for step_title in steps:
        assert deployment_receipts[step_title]['status'] == 1


def test_make_agent(testnet_staking_deployer, test_registry):

    agent = testnet_staking_deployer.make_agent()

    another_application_agent = TestnetThresholdStakingAgent(registry=test_registry)
    assert agent == another_application_agent  # __eq__

    # Compare the contract address for equality
    assert agent.contract_address == another_application_agent.contract_address

