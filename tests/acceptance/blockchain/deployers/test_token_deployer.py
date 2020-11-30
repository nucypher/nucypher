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

from nucypher.blockchain.eth.agents import NucypherTokenAgent
from nucypher.blockchain.eth.deployers import NucypherTokenDeployer
from nucypher.blockchain.eth.interfaces import BaseContractRegistry


def test_token_deployer_and_agent(testerchain, deployment_progress, test_registry):

    origin = testerchain.etherbase_account

    # Trying to get token from blockchain before it's been published should fail
    with pytest.raises(BaseContractRegistry.UnknownContract):
        NucypherTokenAgent(registry=test_registry)

    # The big day...
    deployer = NucypherTokenDeployer(registry=test_registry, deployer_address=origin)

    deployment_receipts = deployer.deploy(progress=deployment_progress)

    for title, receipt in deployment_receipts.items():
        assert receipt['status'] == 1

    # deployment steps must match expected number of steps
    assert deployment_progress.num_steps == len(deployer.deployment_steps) == 1

    # Create a token instance
    token_agent = deployer.make_agent()
    token_contract = token_agent.contract

    expected_token_supply = token_contract.functions.totalSupply().call()
    assert expected_token_supply == token_agent.contract.functions.totalSupply().call()

    # Retrieve the token from the blockchain
    same_token_agent = NucypherTokenAgent(registry=test_registry)

    # Compare the contract address for equality
    assert token_agent.contract_address == same_token_agent.contract_address
    assert token_agent == same_token_agent  # __eq__
