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
from eth_utils import keccak

from nucypher.blockchain.eth.agents import StakingEscrowAgent
from nucypher.blockchain.eth.deployers import (StakingEscrowDeployer,
                                               DispatcherDeployer)
from nucypher.utilities.sandbox.blockchain import STAKING_ESCROW_DEPLOYMENT_SECRET


def test_staking_escrow_deployment(staking_escrow_deployer, deployment_progress):
    secret_hash = keccak(text=STAKING_ESCROW_DEPLOYMENT_SECRET)
    deployment_receipts = staking_escrow_deployer.deploy(secret_hash=secret_hash, progress=deployment_progress)

    # deployment steps must match expected number of steps
    assert deployment_progress.num_steps == len(staking_escrow_deployer.deployment_steps) == len(deployment_receipts) == 4

    for step in staking_escrow_deployer.deployment_steps:
        assert deployment_receipts[step]['status'] == 1


def test_make_agent(staking_escrow_deployer, test_registry):
    # Create a StakingEscrowAgent instance
    staking_agent = staking_escrow_deployer.make_agent()

    # Retrieve the StakingEscrowAgent singleton
    same_staking_agent = StakingEscrowAgent(registry=test_registry)
    assert staking_agent == same_staking_agent

    # Compare the contract staker_address for equality
    assert staking_agent.contract_address == same_staking_agent.contract_address


def test_deployment_parameters(staking_escrow_deployer,
                               token_deployer,
                               token_economics,
                               test_registry):

    token_address = staking_escrow_deployer.contract.functions.token().call()
    assert token_deployer.contract_address == token_address

    staking_agent = StakingEscrowAgent(registry=test_registry)
    params = staking_agent.staking_parameters()
    assert token_economics.staking_deployment_parameters[1:] == params[1:]
    assert token_economics.staking_deployment_parameters[0]*60*60 == params[0]  # FIXME: Do we really want this?


def test_staking_escrow_has_dispatcher(staking_escrow_deployer, testerchain, test_registry):

    # Let's get the "bare" StakingEscrow contract (i.e., unwrapped, no dispatcher)
    existing_bare_contract = testerchain.get_contract_by_name(registry=test_registry,
                                                              name=staking_escrow_deployer.contract_name,
                                                              proxy_name=DispatcherDeployer.contract_name,
                                                              use_proxy_address=False)

    # This contract shouldn't be accessible directly through the deployer or the agent
    assert staking_escrow_deployer.contract_address != existing_bare_contract.address
    staking_agent = StakingEscrowAgent(registry=test_registry)
    assert staking_agent.contract_address != existing_bare_contract

    # The wrapped contract, on the other hand, points to the bare one.
    target = staking_escrow_deployer.contract.functions.target().call()
    assert target == existing_bare_contract.address


def test_upgrade(testerchain, test_registry):
    wrong_secret = b"on second thoughts..."
    old_secret = bytes(STAKING_ESCROW_DEPLOYMENT_SECRET, encoding='utf-8')
    new_secret_hash = keccak(b'new'+old_secret)

    deployer = StakingEscrowDeployer(registry=test_registry,
                                     deployer_address=testerchain.etherbase_account)

    with pytest.raises(deployer.ContractDeploymentError):
        deployer.upgrade(existing_secret_plaintext=wrong_secret,
                         new_secret_hash=new_secret_hash)

    receipts = deployer.upgrade(existing_secret_plaintext=old_secret,
                                new_secret_hash=new_secret_hash)

    for title, receipt in receipts.items():
        assert receipt['status'] == 1


def test_rollback(testerchain, test_registry):
    old_secret = bytes('new'+STAKING_ESCROW_DEPLOYMENT_SECRET, encoding='utf-8')
    new_secret_hash = keccak(text="third time's the charm")

    deployer = StakingEscrowDeployer(registry=test_registry,
                                     deployer_address=testerchain.etherbase_account)

    staking_agent = StakingEscrowAgent(registry=test_registry)
    current_target = staking_agent.contract.functions.target().call()

    # Let's do one more upgrade
    receipts = deployer.upgrade(existing_secret_plaintext=old_secret,
                                new_secret_hash=new_secret_hash)
    for title, receipt in receipts.items():
        assert receipt['status'] == 1

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
    new_secret_hash = keccak(text="...maybe not.")
    receipt = deployer.rollback(existing_secret_plaintext=old_secret,
                                new_secret_hash=new_secret_hash)

    assert receipt['status'] == 1

    new_target = staking_agent.contract.functions.target().call()
    assert new_target != current_target
    assert new_target == old_target
