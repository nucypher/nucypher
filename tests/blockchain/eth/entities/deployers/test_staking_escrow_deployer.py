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

from nucypher.blockchain.eth.agents import StakingEscrowAgent
from nucypher.blockchain.eth.deployers import NucypherTokenDeployer, StakingEscrowDeployer, DispatcherDeployer


def test_staking_escrow_deployer_and_agent(testerchain):
    origin, *everybody_else = testerchain.client.accounts

    # The big day...
    token_deployer = NucypherTokenDeployer(blockchain=testerchain, deployer_address=origin)
    token_deployer.deploy()

    secret_hash = os.urandom(DispatcherDeployer.DISPATCHER_SECRET_LENGTH)
    deployer = StakingEscrowDeployer(blockchain=testerchain,
                                     deployer_address=origin)
    deployment_txhashes = deployer.deploy(secret_hash=secret_hash)

    assert len(deployment_txhashes) == 4

    for title, txhash in deployment_txhashes.items():
        receipt = testerchain.wait_for_receipt(txhash=txhash)
        assert receipt['status'] == 1, "Transaction Rejected {}:{}".format(title, txhash)

    # Create a StakingEscrowAgent instance
    staking_agent = deployer.make_agent()

    # TODO: #1102 - Check that token contract address and staking parameters are correct

    # Retrieve the StakingEscrowAgent singleton
    same_staking_agent = StakingEscrowAgent()
    assert staking_agent == same_staking_agent

    # Compare the contract address for equality
    assert staking_agent.contract_address == same_staking_agent.contract_address

    testerchain.registry.clear()
