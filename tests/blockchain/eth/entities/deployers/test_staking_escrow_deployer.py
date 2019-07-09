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

from nucypher.blockchain.eth.agents import StakingEscrowAgent
from nucypher.blockchain.eth.deployers import (NucypherTokenDeployer,
                                               StakingEscrowDeployer,
                                               DispatcherDeployer)
from nucypher.crypto.api import keccak_digest
from nucypher.utilities.sandbox.blockchain import STAKING_ESCROW_DEPLOYMENT_SECRET


@pytest.fixture(scope="module")
def staking_escrow_deployer(session_testerchain):
    testerchain = session_testerchain

    token_deployer = NucypherTokenDeployer(blockchain=testerchain,
                                           deployer_address=testerchain.etherbase_account)
    token_deployer.deploy()

    deployer = StakingEscrowDeployer(blockchain=testerchain,
                                     deployer_address=testerchain.etherbase_account)
    return deployer


def test_staking_escrow_deployment(session_testerchain, staking_escrow_deployer):
    testerchain = session_testerchain

    secret_hash = keccak_digest(bytes(STAKING_ESCROW_DEPLOYMENT_SECRET, encoding='utf-8'))
    deployment_receipts = staking_escrow_deployer.deploy(secret_hash=secret_hash)

    assert len(deployment_receipts) == 4

    for title, receipt in deployment_receipts.items():
        assert receipt['status'] == 1

    # TODO: #1102 - Check that token contract address and staking parameters are correct


def test_make_agent(staking_escrow_deployer):
    # Create a StakingEscrowAgent instance
    staking_agent = staking_escrow_deployer.make_agent()

    # Retrieve the StakingEscrowAgent singleton
    same_staking_agent = StakingEscrowAgent()
    assert staking_agent == same_staking_agent

    # Compare the contract address for equality
    assert staking_agent.contract_address == same_staking_agent.contract_address


def test_staking_escrow_has_dispatcher(staking_escrow_deployer, session_testerchain):

    # Let's get the "bare" StakingEscrow contract (i.e., unwrapped, no dispatcher)
    existing_bare_contract = session_testerchain.get_contract_by_name(name=staking_escrow_deployer.contract_name,
                                                                      proxy_name=DispatcherDeployer.contract_name,
                                                                      use_proxy_address=False)

    # This contract shouldn't be accessible directly through the deployer or the agent
    assert staking_escrow_deployer.contract_address != existing_bare_contract.address
    staking_agent = StakingEscrowAgent()
    assert staking_agent.contract_address != existing_bare_contract

    # The wrapped contract, on the other hand, points to the bare one.
    target = staking_escrow_deployer.contract.functions.target().call()
    assert target == existing_bare_contract.address


def test_upgrade(session_testerchain):
    wrong_secret = b"on second thoughts..."
    old_secret = bytes(STAKING_ESCROW_DEPLOYMENT_SECRET, encoding='utf-8')
    new_secret_hash = keccak_digest(b'new'+old_secret)

    deployer = StakingEscrowDeployer(blockchain=session_testerchain,
                                     deployer_address=session_testerchain.etherbase_account)

    with pytest.raises(deployer.ContractDeploymentError):
        deployer.upgrade(existing_secret_plaintext=wrong_secret,
                         new_secret_hash=new_secret_hash)

    receipts = deployer.upgrade(existing_secret_plaintext=old_secret,
                                new_secret_hash=new_secret_hash)

    for title, txhash in receipts.items():
        receipt = session_testerchain.wait_for_receipt(txhash=txhash)
        assert receipt['status'] == 1, "Transaction Rejected {}:{}".format(title, txhash)


def test_rollback(session_testerchain):
    old_secret = bytes('new'+STAKING_ESCROW_DEPLOYMENT_SECRET, encoding='utf-8')
    new_secret_hash = keccak_digest(b"third time's the charm")

    deployer = StakingEscrowDeployer(blockchain=session_testerchain,
                                     deployer_address=session_testerchain.etherbase_account)

    staking_agent = StakingEscrowAgent()
    current_target = staking_agent.contract.functions.target().call()

    # Let's do one more upgrade
    receipts = deployer.upgrade(existing_secret_plaintext=old_secret,
                                new_secret_hash=new_secret_hash)
    for title, txhash in receipts.items():
        receipt = session_testerchain.wait_for_receipt(txhash=txhash)
        assert receipt['status'] == 1, "Transaction Rejected {}:{}".format(title, txhash)

    old_target = current_target
    current_target = staking_agent.contract.functions.target().call()
    assert current_target != old_target

    # It's time to rollback. But first...
    wrong_secret = b"WRONG!!"
    with pytest.raises(deployer.ContractDeploymentError):
        deployer.rollback(existing_secret_plaintext=wrong_secret,
                          new_secret_hash=new_secret_hash)

    # OK, *now* is time for rollback
    old_secret = b"third time's the charm"
    new_secret_hash = keccak_digest(b"...maybe not.")
    txhash = deployer.rollback(existing_secret_plaintext=old_secret,
                               new_secret_hash=new_secret_hash)

    receipt = session_testerchain.wait_for_receipt(txhash=txhash)
    assert receipt['status'] == 1, "Transaction Rejected:{}".format(txhash)

    new_target = staking_agent.contract.functions.target().call()
    assert new_target != current_target
    assert new_target == old_target
