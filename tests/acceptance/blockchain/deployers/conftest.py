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

from nucypher.blockchain.eth.deployers import NucypherTokenDeployer
from nucypher.blockchain.eth.signers.software import Web3Signer
from nucypher.crypto.powers import TransactingPower


@pytest.fixture(scope="module")
def token_deployer(testerchain, test_registry):
    token_deployer = NucypherTokenDeployer(registry=test_registry)
    return token_deployer


@pytest.fixture(scope="module")
def transacting_power(testerchain, test_registry):
    tpower = TransactingPower(account=testerchain.etherbase_account,
                              signer=Web3Signer(testerchain.client))
    return tpower


@pytest.fixture(scope="function")
def deployment_progress():
    class DeploymentProgress:
        num_steps = 0

        def update(self, steps: int):
            self.num_steps += steps

    progress = DeploymentProgress()
    return progress
