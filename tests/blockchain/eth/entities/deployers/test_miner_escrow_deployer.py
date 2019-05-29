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
import os

from nucypher.blockchain.eth.agents import StakerAgent
from nucypher.blockchain.eth.deployers import NucypherTokenDeployer, StakerEscrowDeployer


def test_token_deployer_and_agent(testerchain):
    origin, *everybody_else = testerchain.interface.w3.eth.accounts

    # The big day...
    token_deployer = NucypherTokenDeployer(blockchain=testerchain, deployer_address=origin)

    token_deployer.deploy()

    secret_hash = os.urandom(32)
    deployer = StakerEscrowDeployer(blockchain=testerchain,
                                   deployer_address=origin)

    deployment_txhashes = deployer.deploy(secret_hash=secret_hash)

    for title, txhash in deployment_txhashes.items():
        receipt = testerchain.wait_for_receipt(txhash=txhash)
        assert receipt['status'] == 1, "Transaction Rejected {}:{}".format(title, txhash)

    # Create a token instance
    staker_agent = deployer.make_agent()
    staker_escrow_contract = staker_agent.contract

    expected_token_supply = staker_escrow_contract.functions.totalSupply().call()
    assert expected_token_supply == staker_agent.contract.functions.totalSupply().call()

    # Retrieve the token from the blockchain
    same_staker_agent = StakerAgent()

    # Compare the contract address for equality
    assert staker_agent.contract_address == same_staker_agent.contract_address
    assert staker_agent == same_staker_agent  # __eq__

    testerchain.interface.registry.clear()
