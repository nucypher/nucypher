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

from nucypher.blockchain.eth.signers.software import Web3Signer
from nucypher.crypto.powers import TransactingPower
from nucypher.blockchain.eth.deployers import (
    AdjudicatorDeployer,
    NucypherTokenDeployer,
    PolicyManagerDeployer,
    StakingEscrowDeployer,
    StakingInterfaceDeployer
)
from constant_sorrow.constants import (FULL, INIT)


@pytest.fixture(scope="module")
def token_deployer(testerchain, test_registry):
    token_deployer = NucypherTokenDeployer(registry=test_registry)
    return token_deployer


@pytest.fixture(scope="module")
def transacting_power(testerchain, test_registry):
    tpower = TransactingPower(account=testerchain.etherbase_account,
                              signer=Web3Signer(testerchain.client))
    return tpower


@pytest.fixture(scope="module")
def staking_escrow_stub_deployer(testerchain, token_deployer, test_registry, transacting_power):
    token_deployer.deploy(transacting_power=transacting_power)
    staking_escrow_deployer = StakingEscrowDeployer(registry=test_registry)
    return staking_escrow_deployer


@pytest.fixture(scope="module")
def staking_escrow_deployer(testerchain,
                            staking_escrow_stub_deployer,
                            threshold_staking,
                            test_registry,
                            transacting_power):
    staking_escrow_stub_deployer.deploy(deployment_mode=INIT, transacting_power=transacting_power)
    staking_escrow_deployer = StakingEscrowDeployer(staking_interface=threshold_staking.address,
                                                    registry=test_registry)
    return staking_escrow_deployer


@pytest.fixture(scope="module")
def staking_interface_deployer(staking_escrow_deployer, testerchain, test_registry, threshold_staking):
    staking_interface_deployer = StakingInterfaceDeployer(staking_interface=threshold_staking.address,
                                                          registry=test_registry)
    return staking_interface_deployer


@pytest.fixture(scope="function")
def deployment_progress():
    class DeploymentProgress:
        num_steps = 0

        def update(self, steps: int):
            self.num_steps += steps

    progress = DeploymentProgress()
    return progress
