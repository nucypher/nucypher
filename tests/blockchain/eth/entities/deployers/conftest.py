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
from nucypher.blockchain.eth.deployers import (NucypherTokenDeployer,
                                               StakingEscrowDeployer)


@pytest.fixture(scope="module")
def token_deployer(testerchain, test_registry):

    token_deployer = NucypherTokenDeployer(registry=test_registry,
                                           deployer_address=testerchain.etherbase_account)
    return token_deployer


@pytest.fixture(scope="module")
def staking_escrow_deployer(testerchain, token_deployer, test_registry):
    token_deployer.deploy()

    staking_escrow_deployer = StakingEscrowDeployer(registry=test_registry,
                                                    deployer_address=testerchain.etherbase_account)
    return staking_escrow_deployer


@pytest.fixture(scope="function")
def deployment_progress():
    class DeploymentProgress:
        num_steps = 0

        def update(self, steps: int):
            self.num_steps += steps

    progress = DeploymentProgress()
    return progress
