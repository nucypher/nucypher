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

import maya
import pytest
from eth_tester.exceptions import TransactionFailed
from eth_utils import is_checksum_address, to_wei

from nucypher.blockchain.eth.agents import PreallocationEscrowAgent
from nucypher.blockchain.eth.interfaces import BlockchainInterface
from nucypher.blockchain.eth.deployers import PreallocationEscrowDeployer, StakingInterfaceDeployer, DispatcherDeployer
from nucypher.blockchain.eth.registry import InMemoryAllocationRegistry
from nucypher.crypto.powers import TransactingPower
from nucypher.utilities.sandbox.constants import INSECURE_DEVELOPMENT_PASSWORD

TEST_DURATION = 60*60
TEST_ALLOCATION_REGISTRY = InMemoryAllocationRegistry()


@pytest.fixture(scope='module')
def allocation_value(token_economics):
    allocation = token_economics.minimum_allowed_locked * 10
    return allocation


@pytest.fixture(scope='function')
def agent(testerchain, test_registry, allocation_value, agency) -> PreallocationEscrowAgent:
    deployer_address, beneficiary_address, *everybody_else = testerchain.client.accounts

    # Mock Powerup consumption (Deployer)
    testerchain.transacting_power = TransactingPower(password=INSECURE_DEVELOPMENT_PASSWORD,
                                                     account=deployer_address)
    testerchain.transacting_power.activate()

    # Escrow
    escrow_deployer = PreallocationEscrowDeployer(deployer_address=deployer_address,
                                                  registry=test_registry,
                                                  allocation_registry=TEST_ALLOCATION_REGISTRY)

    _receipt = escrow_deployer.deploy()

    escrow_deployer.initial_deposit(value=allocation_value, duration_seconds=TEST_DURATION)
    assert escrow_deployer.contract.functions.getLockedTokens().call() == allocation_value
    escrow_deployer.assign_beneficiary(checksum_address=beneficiary_address)
    escrow_deployer.enroll_principal_contract()
    assert escrow_deployer.contract.functions.getLockedTokens().call() == allocation_value
    agent = escrow_deployer.make_agent()

    direct_agent = PreallocationEscrowAgent(registry=test_registry,
                                            allocation_registry=TEST_ALLOCATION_REGISTRY,
                                            beneficiary=beneficiary_address)

    assert direct_agent == agent
    assert direct_agent.contract.abi == agent.contract.abi
    assert direct_agent.contract.address == agent.contract.address
    assert agent.principal_contract.address == escrow_deployer.contract.address
    assert agent.principal_contract.abi == escrow_deployer.contract.abi
    assert direct_agent.contract.abi == escrow_deployer.contract.abi
    assert direct_agent.contract.address == escrow_deployer.contract.address

    yield agent
    TEST_ALLOCATION_REGISTRY.clear()


def test_preallocation_escrow_agent_represents_beneficiary(agent, agency):
    token_agent, staking_agent, policy_agent = agency

    # Name
    assert agent.registry_contract_name == PreallocationEscrowAgent.registry_contract_name

    # Not Equal to StakingEscrow
    assert agent != staking_agent, "PreallocationEscrow Agent is connected to the StakingEscrow's contract"
    assert agent.contract_address != staking_agent.contract_address, "PreallocationEscrow and StakingEscrow agents represent the same contract"

    # Interface Target Accuracy
    assert agent.principal_contract.address == agent.interface_contract.address
    assert agent.principal_contract.abi != agent.interface_contract.abi

    assert agent.principal_contract.address == agent.contract.address
    assert agent.principal_contract.abi == agent.contract.abi


def test_read_beneficiary(testerchain, agent):
    deployer_address, beneficiary_address, *everybody_else = testerchain.client.accounts
    beneficiary = agent.beneficiary
    assert beneficiary == beneficiary_address
    assert is_checksum_address(beneficiary)


def test_read_allocation(agent, agency, allocation_value):
    token_agent, staking_agent, policy_agent = agency
    balance = token_agent.get_balance(address=agent.principal_contract.address)
    assert balance == allocation_value
    allocation = agent.unvested_tokens
    assert allocation > 0
    assert allocation == allocation_value


@pytest.mark.usefixtures("agency")
def test_read_timestamp(agent):
    timestamp = agent.end_timestamp
    end_locktime = maya.MayaDT(timestamp)
    assert end_locktime.slang_time()
    now = maya.now()
    assert now < end_locktime, '{} is not in the future!'.format(end_locktime.slang_date())


@pytest.mark.slow()
def test_deposit_and_withdraw_as_staker(testerchain, agent, agency, allocation_value, token_economics):
    token_agent, staking_agent, policy_agent = agency

    assert staking_agent.get_locked_tokens(staker_address=agent.contract_address) == 0
    assert staking_agent.get_locked_tokens(staker_address=agent.contract_address, periods=1) == 0
    assert agent.unvested_tokens == allocation_value
    assert token_agent.get_balance(address=agent.contract_address) == allocation_value

    # Mock Powerup consumption (Beneficiary)
    testerchain.transacting_power = TransactingPower(password=INSECURE_DEVELOPMENT_PASSWORD,
                                                     account=agent.beneficiary)
    testerchain.transacting_power.activate()

    # Move the tokens to the StakingEscrow
    receipt = agent.deposit_as_staker(amount=token_economics.minimum_allowed_locked, lock_periods=token_economics.minimum_locked_periods)
    assert receipt  # TODO

    # Owner sets a worker in StakingEscrow via PreallocationEscrow
    worker = testerchain.ursula_account(0)
    _receipt = agent.set_worker(worker_address=worker)

    assert token_agent.get_balance(address=agent.contract_address) == allocation_value - token_economics.minimum_allowed_locked
    assert agent.unvested_tokens == allocation_value
    assert staking_agent.get_locked_tokens(staker_address=agent.contract_address) == 0
    assert staking_agent.get_locked_tokens(staker_address=agent.contract_address, periods=1) == token_economics.minimum_allowed_locked
    assert staking_agent.get_locked_tokens(staker_address=agent.contract_address, periods=token_economics.minimum_locked_periods) == token_economics.minimum_allowed_locked
    assert staking_agent.get_locked_tokens(staker_address=agent.contract_address, periods=token_economics.minimum_locked_periods+1) == 0

    # Mock Powerup consumption (Beneficiary-Worker)
    testerchain.transacting_power = TransactingPower(password=INSECURE_DEVELOPMENT_PASSWORD,
                                                     account=worker)
    testerchain.transacting_power.activate()

    for _ in range(token_economics.minimum_locked_periods):
        staking_agent.confirm_activity(worker_address=worker)
        testerchain.time_travel(periods=1)
    testerchain.time_travel(periods=1)

    # Mock Powerup consumption (Beneficiary)
    testerchain.transacting_power = TransactingPower(password=INSECURE_DEVELOPMENT_PASSWORD,
                                                     account=agent.beneficiary)
    testerchain.transacting_power.activate()

    agent.mint()

    assert staking_agent.get_locked_tokens(staker_address=agent.contract_address) == 0
    assert token_agent.get_balance(address=agent.contract_address) == allocation_value - token_economics.minimum_allowed_locked
    receipt = agent.withdraw_as_staker(value=token_economics.minimum_allowed_locked)
    assert receipt['status'] == 1, "Transaction Rejected"
    assert token_agent.get_balance(address=agent.contract_address) == allocation_value

    # Release worker
    _receipt = agent.release_worker()

    receipt = agent.withdraw_as_staker(value=staking_agent.owned_tokens(staker_address=agent.contract_address))
    assert receipt['status'] == 1, "Transaction Rejected"
    assert token_agent.get_balance(address=agent.contract_address) > allocation_value


def test_collect_policy_reward(testerchain, agent, agency, token_economics):
    _token_agent, staking_agent, policy_agent = agency
    deployer_address, beneficiary_address, author, ursula, *everybody_else = testerchain.client.accounts

    # Mock Powerup consumption (Beneficiary)
    testerchain.transacting_power = TransactingPower(password=INSECURE_DEVELOPMENT_PASSWORD,
                                                     account=agent.beneficiary)
    testerchain.transacting_power.activate()

    _receipt = agent.deposit_as_staker(amount=token_economics.minimum_allowed_locked,
                                       lock_periods=token_economics.minimum_locked_periods)

    # Owner sets a worker in StakingEscrow via PreallocationEscrow
    worker = testerchain.ursula_account(0)
    _receipt = agent.set_worker(worker_address=worker)

    testerchain.time_travel(periods=1)

    # Mock Powerup consumption (Alice)
    testerchain.transacting_power = TransactingPower(password=INSECURE_DEVELOPMENT_PASSWORD,
                                                     account=author)
    testerchain.transacting_power.activate()

    _receipt = policy_agent.create_policy(policy_id=os.urandom(16),
                                          author_address=author,
                                          value=to_wei(1, 'ether'),
                                          periods=2,
                                          first_period_reward=0,
                                          node_addresses=[agent.contract_address])

    # Mock Powerup consumption (Beneficiary-Worker)
    testerchain.transacting_power = TransactingPower(password=INSECURE_DEVELOPMENT_PASSWORD,
                                                     account=worker)
    testerchain.transacting_power.activate()

    _receipt = staking_agent.confirm_activity(worker_address=worker)
    testerchain.time_travel(periods=2)
    _receipt = staking_agent.confirm_activity(worker_address=worker)

    old_balance = testerchain.client.get_balance(account=agent.beneficiary)

    # Mock Powerup consumption (Beneficiary)
    testerchain.transacting_power = TransactingPower(password=INSECURE_DEVELOPMENT_PASSWORD,
                                                     account=agent.beneficiary)
    testerchain.transacting_power.activate()

    receipt = agent.collect_policy_reward(collector_address=agent.beneficiary)
    assert receipt['status'] == 1, "Transaction Rejected"
    assert testerchain.client.get_balance(account=agent.beneficiary) > old_balance


def test_withdraw_tokens(testerchain, agent, agency, allocation_value):
    token_agent, staking_agent, policy_agent = agency
    deployer_address, beneficiary_address, *everybody_else = testerchain.client.accounts

    # Mock Powerup consumption (Beneficiary)
    testerchain.transacting_power = TransactingPower(password=INSECURE_DEVELOPMENT_PASSWORD,
                                                     account=agent.beneficiary)
    testerchain.transacting_power.activate()

    assert token_agent.get_balance(address=agent.contract_address) == agent.unvested_tokens
    with pytest.raises((TransactionFailed, ValueError)):
        agent.withdraw_tokens(value=allocation_value)
    testerchain.time_travel(seconds=TEST_DURATION)

    receipt = agent.withdraw_tokens(value=allocation_value)
    assert receipt['status'] == 1, "Transaction Rejected"
    assert token_agent.get_balance(address=agent.contract_address) == 0
    assert token_agent.get_balance(address=beneficiary_address) == allocation_value
