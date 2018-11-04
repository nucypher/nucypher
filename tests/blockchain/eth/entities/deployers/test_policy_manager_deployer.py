"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""
import os

from nucypher.blockchain.eth.agents import PolicyAgent
from nucypher.blockchain.eth.constants import DISPATCHER_SECRET_LENGTH
from nucypher.blockchain.eth.deployers import NucypherTokenDeployer, MinerEscrowDeployer, PolicyManagerDeployer


def test_policy_manager_deployer(testerchain):
    origin, *everybody_else = testerchain.interface.w3.eth.accounts

    token_deployer = NucypherTokenDeployer(blockchain=testerchain, deployer_address=origin)

    token_deployer.deploy()

    token_agent = token_deployer.make_agent()  # 1: Token

    miners_escrow_secret = os.urandom(DISPATCHER_SECRET_LENGTH)
    miner_escrow_deployer = MinerEscrowDeployer(
        deployer_address=origin,
        secret_hash=testerchain.interface.w3.sha3(miners_escrow_secret))

    miner_escrow_deployer.deploy()

    miner_agent = miner_escrow_deployer.make_agent()  # 2 Miner Escrow

    policy_manager_secret = os.urandom(DISPATCHER_SECRET_LENGTH)
    deployer = PolicyManagerDeployer(
        deployer_address=origin,
        secret_hash=testerchain.interface.w3.sha3(policy_manager_secret))

    deployment_txhashes = deployer.deploy()
    assert len(deployment_txhashes) == 3

    for title, txhash in deployment_txhashes.items():
        receipt = testerchain.wait_for_receipt(txhash=txhash)
        assert receipt['status'] == 1, "Transaction Rejected {}:{}".format(title, txhash)

    # Create a token instance
    policy_agent = deployer.make_agent()
    policy_manager_contract = policy_agent.contract

    # Retrieve the token from the blockchain
    some_policy_agent = PolicyAgent()
    assert some_policy_agent.contract.address == policy_manager_contract.address

    # Compare the contract address for equality
    assert policy_agent.contract_address == some_policy_agent.contract_address
    assert policy_agent == some_policy_agent  # __eq__
