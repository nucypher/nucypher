


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
