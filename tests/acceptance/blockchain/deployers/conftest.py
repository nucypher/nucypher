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

from nucypher.blockchain.eth.deployers import (AdjudicatorDeployer, NucypherTokenDeployer, PolicyManagerDeployer,
                                               StakingEscrowDeployer, StakingInterfaceDeployer, WorklockDeployer)


@pytest.fixture(scope="module")
def token_deployer(testerchain, test_registry):
    token_deployer = NucypherTokenDeployer(registry=test_registry,
                                           deployer_address=testerchain.etherbase_account)
    return token_deployer


@pytest.fixture(scope="module")
def worklock_deployer(token_deployer,
                      testerchain,
                      test_registry,
                      token_economics):
    token_deployer.deploy()
    worklock_deployer = WorklockDeployer(registry=test_registry,
                                         economics=token_economics,
                                         deployer_address=testerchain.etherbase_account)
    return worklock_deployer


@pytest.fixture(scope="module")
def policy_manager_deployer(worklock_deployer, testerchain, test_registry):
    worklock_deployer.deploy()
    policy_manager_deployer = PolicyManagerDeployer(registry=test_registry,
                                                    deployer_address=testerchain.etherbase_account)
    return policy_manager_deployer


@pytest.fixture(scope="module")
def adjudicator_deployer(policy_manager_deployer, testerchain, test_registry):
    policy_manager_deployer.deploy()
    adjudicator_deployer = AdjudicatorDeployer(registry=test_registry,
                                               deployer_address=testerchain.etherbase_account)
    return adjudicator_deployer


@pytest.fixture(scope="module")
def staking_escrow_deployer(testerchain, adjudicator_deployer, test_registry):
    adjudicator_deployer.deploy()
    staking_escrow_deployer = StakingEscrowDeployer(registry=test_registry,
                                                    deployer_address=testerchain.etherbase_account)
    return staking_escrow_deployer


@pytest.fixture(scope="module")
def staking_interface_deployer(staking_escrow_deployer, testerchain, test_registry):
    staking_escrow_deployer.deploy()
    staking_interface_deployer = StakingInterfaceDeployer(registry=test_registry,
                                                          deployer_address=testerchain.etherbase_account)
    return staking_interface_deployer


@pytest.fixture(scope="function")
def deployment_progress():
    class DeploymentProgress:
        num_steps = 0

        def update(self, steps: int):
            self.num_steps += steps

    progress = DeploymentProgress()
    return progress
