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
from eth_utils import keccak

from nucypher.blockchain.eth.agents import PolicyAgent
from nucypher.blockchain.eth.deployers import (
    NucypherTokenDeployer,
    StakingEscrowDeployer,
    PolicyManagerDeployer,
    DispatcherDeployer
)


def test_policy_manager_deployer(testerchain):
    origin, *everybody_else = testerchain.client.accounts

    token_deployer = NucypherTokenDeployer(blockchain=testerchain, deployer_address=origin)

    token_deployer.deploy()

    stakers_escrow_secret = os.urandom(DispatcherDeployer.DISPATCHER_SECRET_LENGTH)
    staking_escrow_deployer = StakingEscrowDeployer(deployer_address=origin, blockchain=testerchain)

    staking_escrow_deployer.deploy(secret_hash=keccak(stakers_escrow_secret))

    policy_manager_secret = os.urandom(DispatcherDeployer.DISPATCHER_SECRET_LENGTH)
    deployer = PolicyManagerDeployer(deployer_address=origin, blockchain=testerchain)

    deployment_txhashes = deployer.deploy(secret_hash=keccak(policy_manager_secret))
    assert len(deployment_txhashes) == 3

    for title, txhash in deployment_txhashes.items():
        receipt = testerchain.wait_for_receipt(txhash=txhash)
        assert receipt['status'] == 1, "Transaction Rejected {}:{}".format(title, txhash)

    # Create a PolicyAgent
    policy_agent = deployer.make_agent()

    # TODO: #1102 - Check that StakingEscrow contract address and public parameters are correct

    # Retrieve the PolicyAgent singleton
    some_policy_agent = PolicyAgent()
    assert policy_agent == some_policy_agent  # __eq__

    # Compare the contract address for equality
    assert policy_agent.contract_address == some_policy_agent.contract_address

