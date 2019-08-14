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
from eth_utils import is_checksum_address, to_wei

from eth_tester.exceptions import TransactionFailed
from nucypher.blockchain.eth.agents import UserEscrowAgent
from nucypher.blockchain.eth.interfaces import BlockchainInterface
from nucypher.blockchain.eth.deployers import UserEscrowDeployer, UserEscrowProxyDeployer, DispatcherDeployer
from nucypher.blockchain.eth.registry import InMemoryAllocationRegistry
from nucypher.crypto.powers import TransactingPower
from nucypher.utilities.sandbox.constants import INSECURE_DEVELOPMENT_PASSWORD

TEST_DURATION = 60*60
TEST_ALLOCATION_REGISTRY = InMemoryAllocationRegistry()


@pytest.fixture(scope='module')
def allocation_value(token_economics):
    allocation = token_economics.minimum_allowed_locked * 10
    return allocation


@pytest.fixture(scope='module')
def proxy_deployer(testerchain, agency) -> UserEscrowAgent:
    deployer_address, beneficiary_address, *everybody_else = testerchain.client.accounts

    # Proxy
    proxy_secret = os.urandom(DispatcherDeployer.DISPATCHER_SECRET_LENGTH)
    proxy_deployer = UserEscrowProxyDeployer(deployer_address=deployer_address, blockchain=testerchain)

    proxy_deployer.deploy(secret_hash=proxy_secret)
    yield proxy_deployer


@pytest.fixture(scope='function')
def agent(testerchain, proxy_deployer, allocation_value, agency) -> UserEscrowAgent:
    deployer_address, beneficiary_address, *everybody_else = testerchain.client.accounts

    # Mock Powerup consumption (Deployer)
    testerchain.transacting_power = TransactingPower(password=INSECURE_DEVELOPMENT_PASSWORD,
                                                     account=deployer_address)
    testerchain.transacting_power.activate()

    # Escrow
    escrow_deployer = UserEscrowDeployer(deployer_address=deployer_address,
                                         blockchain=testerchain,
                                         allocation_registry=TEST_ALLOCATION_REGISTRY)

    _txhash = escrow_deployer.deploy()

    escrow_deployer.initial_deposit(value=allocation_value, lock_periods=TEST_DURATION)
    assert escrow_deployer.contract.functions.getLockedTokens().call() == allocation_value
    escrow_deployer.assign_beneficiary(beneficiary_address=beneficiary_address)
    escrow_deployer.enroll_principal_contract()
    assert escrow_deployer.contract.functions.getLockedTokens().call() == allocation_value
    _agent = escrow_deployer.make_agent()

    _direct_agent = UserEscrowAgent(blockchain=testerchain,
                                    allocation_registry=TEST_ALLOCATION_REGISTRY,
                                    beneficiary=beneficiary_address)

    assert _direct_agent == _agent
    assert _direct_agent.contract.abi == _agent.contract.abi
    assert _direct_agent.contract.address == _agent.contract.address
    assert _agent.principal_contract.address == escrow_deployer.contract.address
    assert _agent.principal_contract.abi == escrow_deployer.contract.abi
    assert _direct_agent.contract.abi == escrow_deployer.contract.abi
    assert _direct_agent.contract.address == escrow_deployer.contract.address

    yield _agent
    TEST_ALLOCATION_REGISTRY.clear()


def test_user_escrow_agent_represents_beneficiary(agent, agency):
    token_agent, staking_agent, policy_agent = agency

    # Name
    assert agent.registry_contract_name == UserEscrowAgent.registry_contract_name

    # Not Equal to StakingEscrow
    assert agent != staking_agent, "UserEscrow Agent is connected to the StakingEscrow's contract"
    assert agent.contract_address != staking_agent.contract_address, "UserEscrow and StakingEscrow agents represent the same contract"

    # Proxy Target Accuracy
    assert agent.principal_contract.address == agent.proxy_contract.address
    assert agent.principal_contract.abi != agent.proxy_contract.abi

    assert agent.principal_contract.address == agent.contract.address
    assert agent.principal_contract.abi == agent.contract.abi


def test_read_beneficiary(testerchain, agent):
    deployer_address, beneficiary_address, *everybody_else = testerchain.client.accounts
    benficiary = agent.beneficiary
    assert benficiary == beneficiary_address
    assert is_checksum_address(benficiary)


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
    receipt = agent.deposit_as_staker(value=token_economics.minimum_allowed_locked, periods=token_economics.minimum_locked_periods)
    assert receipt  # TODO

    # User sets a worker in StakingEscrow via UserEscrow
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
    txhash = agent.withdraw_as_staker(value=token_economics.minimum_allowed_locked)
    assert txhash  # TODO
    assert token_agent.get_balance(address=agent.contract_address) == allocation_value

    # Release worker
    _txhash = agent.set_worker(worker_address=BlockchainInterface.NULL_ADDRESS)

    txhash = agent.withdraw_as_staker(value=staking_agent.owned_tokens(staker_address=agent.contract_address))
    assert txhash
    assert token_agent.get_balance(address=agent.contract_address) > allocation_value


def test_collect_policy_reward(testerchain, agent, agency, token_economics):
    _token_agent, staking_agent, policy_agent = agency
    deployer_address, beneficiary_address, author, ursula, *everybody_else = testerchain.client.accounts

    # Mock Powerup consumption (Beneficiary)
    testerchain.transacting_power = TransactingPower(password=INSECURE_DEVELOPMENT_PASSWORD,
                                                     account=agent.beneficiary)
    testerchain.transacting_power.activate()

    _txhash = agent.deposit_as_staker(value=token_economics.minimum_allowed_locked, periods=token_economics.minimum_locked_periods)

    # User sets a worker in StakingEscrow via UserEscrow
    worker = testerchain.ursula_account(0)
    _receipt = agent.set_worker(worker_address=worker)

    testerchain.time_travel(periods=1)

    # Mock Powerup consumption (Alice)
    testerchain.transacting_power = TransactingPower(password=INSECURE_DEVELOPMENT_PASSWORD,
                                                     account=author)
    testerchain.transacting_power.activate()

    _txhash = policy_agent.create_policy(policy_id=os.urandom(16),
                                         author_address=author,
                                         value=to_wei(1, 'ether'),
                                         periods=2,
                                         first_period_reward=0,
                                         node_addresses=[agent.contract_address])

    # Mock Powerup consumption (Beneficiary-Worker)
    testerchain.transacting_power = TransactingPower(password=INSECURE_DEVELOPMENT_PASSWORD,
                                                     account=worker)
    testerchain.transacting_power.activate()

    _txhash = staking_agent.confirm_activity(worker_address=worker)
    testerchain.time_travel(periods=2)
    _txhash = staking_agent.confirm_activity(worker_address=worker)

    old_balance = testerchain.client.get_balance(account=agent.beneficiary)

    # Mock Powerup consumption (Beneficiary)
    testerchain.transacting_power = TransactingPower(password=INSECURE_DEVELOPMENT_PASSWORD,
                                                     account=agent.beneficiary)
    testerchain.transacting_power.activate()

    txhash = agent.collect_policy_reward()
    assert txhash  # TODO
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

    txhash = agent.withdraw_tokens(value=allocation_value)
    assert txhash  # TODO
    assert token_agent.get_balance(address=agent.contract_address) == 0
    assert token_agent.get_balance(address=beneficiary_address) == allocation_value
