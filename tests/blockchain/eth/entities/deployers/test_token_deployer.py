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
from nucypher.blockchain.eth.interfaces import EthereumContractRegistry


def test_token_deployer_and_agent(testerchain):
    origin = testerchain.etherbase_account

    # Trying to get token from blockchain before it's been published fails
    with pytest.raises(EthereumContractRegistry.UnknownContract):
        NucypherTokenAgent(blockchain=testerchain)

    # The big day...
    deployer = NucypherTokenDeployer(blockchain=testerchain, deployer_address=origin)

    deployment_txhashes = deployer.deploy()

    for title, txhash in deployment_txhashes.items():
        receipt = testerchain.wait_for_receipt(txhash=txhash)
        assert receipt['status'] == 1, "Transaction Rejected {}:{}".format(title, txhash)

    # Create a token instance
    token_agent = deployer.make_agent()
    token_contract = token_agent.contract

    expected_token_supply = token_contract.functions.totalSupply().call()
    assert expected_token_supply == token_agent.contract.functions.totalSupply().call()

    # Retrieve the token from the blockchain
    same_token_agent = NucypherTokenAgent(blockchain=testerchain)

    # Compare the contract address for equality
    assert token_agent.contract_address == same_token_agent.contract_address
    assert token_agent == same_token_agent  # __eq__

    testerchain.interface.registry.clear()
