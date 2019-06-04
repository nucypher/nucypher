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
from nucypher.blockchain.eth.deployers import UserEscrowDeployer, UserEscrowProxyDeployer, DispatcherDeployer
from nucypher.blockchain.eth.registry import InMemoryAllocationRegistry

TEST_DURATION = 60*60
TEST_ALLOCATION_REGISTRY = InMemoryAllocationRegistry()


@pytest.fixture(scope='module')
def allocation_value(token_economics):
    allocation = token_economics.minimum_allowed_locked * 10
    return allocation


@pytest.mark.usefixtures("three_agents")
@pytest.fixture(scope='module')
def proxy_deployer(testerchain) -> UserEscrowAgent:
    deployer_address, beneficiary_address, *everybody_else = testerchain.interface.w3.eth.accounts

    # Proxy
    proxy_secret = os.urandom(DispatcherDeployer.DISPATCHER_SECRET_LENGTH)
    proxy_deployer = UserEscrowProxyDeployer(deployer_address=deployer_address)

    proxy_deployer.deploy( secret_hash=proxy_secret)
    yield proxy_deployer


@pytest.mark.usefixtures(["three_agents", "proxy_deployer"])
@pytest.fixture(scope='function')
def agent(testerchain, proxy_deployer, allocation_value) -> UserEscrowAgent:
    deployer_address, beneficiary_address, *everybody_else = testerchain.interface.w3.eth.accounts

    # Escrow
    escrow_deployer = UserEscrowDeployer(deployer_address=deployer_address,
                                         allocation_registry=TEST_ALLOCATION_REGISTRY)

    _txhash = escrow_deployer.deploy()

    escrow_deployer.initial_deposit(value=allocation_value, duration=TEST_DURATION)
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


def test_user_escrow_agent_represents_beneficiary(agent, three_agents):
    token_agent, staker_agent, policy_agent = three_agents

    # Name
    assert agent.registry_contract_name == UserEscrowAgent.registry_contract_name

    # Not Equal to StakerAgent
    assert agent != staker_agent, "UserEscrow Agent is connected to the StakerEscrow's contract"
    assert agent.contract_address != staker_agent.contract_address, "UserEscrow and StakerEscrow agents represent the same contract"

    # Proxy Target Accuracy
    assert agent.principal_contract.address == agent.proxy_contract.address
    assert agent.principal_contract.abi != agent.proxy_contract.abi

    assert agent.principal_contract.address == agent.contract.address
    assert agent.principal_contract.abi == agent.contract.abi


def test_read_beneficiary(testerchain, agent):
    deployer_address, beneficiary_address, *everybody_else = testerchain.interface.w3.eth.accounts
    benficiary = agent.beneficiary
    assert benficiary == beneficiary_address
    assert is_checksum_address(benficiary)


def test_read_allocation(agent, three_agents, allocation_value):
    token_agent, staker_agent, policy_agent = three_agents
    balance = token_agent.get_balance(address=agent.principal_contract.address)
    assert balance == allocation_value
    allocation = agent.unvested_tokens
    assert allocation > 0
    assert allocation == allocation_value


@pytest.mark.usesfixtures("three_agents")
def test_read_timestamp(agent):
    timestamp = agent.end_timestamp
    end_locktime = maya.MayaDT(timestamp)
    assert end_locktime.slang_time()
    now = maya.now()
    assert now < end_locktime, '{} is not in the future!'.format(end_locktime.slang_date())


@pytest.mark.slow()
@pytest.mark.usesfixtures("three_agents")
def test_deposit_and_withdraw_as_staker(testerchain, agent, three_agents, allocation_value, token_economics):
    token_agent, staker_agent, policy_agent = three_agents

    assert staker_agent.get_locked_tokens(staker_address=agent.contract_address) == 0
    assert staker_agent.get_locked_tokens(staker_address=agent.contract_address, periods=1) == 0
    assert agent.unvested_tokens == allocation_value
    assert token_agent.get_balance(address=agent.contract_address) == allocation_value

    # Move the tokens to the StakerEscrow
    txhash = agent.deposit_as_staker(value=token_economics.minimum_allowed_locked, periods=token_economics.minimum_locked_periods)
    assert txhash  # TODO
    _txhash = agent.set_worker(worker_address=agent.beneficiary)

    assert token_agent.get_balance(address=agent.contract_address) == allocation_value - token_economics.minimum_allowed_locked
    assert agent.unvested_tokens == allocation_value
    assert staker_agent.get_locked_tokens(staker_address=agent.contract_address) == 0
    assert staker_agent.get_locked_tokens(staker_address=agent.contract_address, periods=1) == token_economics.minimum_allowed_locked
    assert staker_agent.get_locked_tokens(staker_address=agent.contract_address, periods=token_economics.minimum_locked_periods) == token_economics.minimum_allowed_locked
    assert staker_agent.get_locked_tokens(staker_address=agent.contract_address, periods=token_economics.minimum_locked_periods+1) == 0

    for _ in range(token_economics.minimum_locked_periods):
        agent.confirm_activity()
        testerchain.time_travel(periods=1)
    testerchain.time_travel(periods=1)
    agent.mint()

    assert staker_agent.get_locked_tokens(staker_address=agent.contract_address) == 0
    assert token_agent.get_balance(address=agent.contract_address) == allocation_value - token_economics.minimum_allowed_locked
    txhash = agent.withdraw_as_staker(value=token_economics.minimum_allowed_locked)
    assert txhash  # TODO
    assert token_agent.get_balance(address=agent.contract_address) == allocation_value

    # Release worker
    _txhash = agent.set_worker(worker_address=testerchain.etherbase_account)

    txhash = agent.withdraw_as_staker(value=staker_agent.owned_tokens(address=agent.contract_address))
    assert txhash
    assert token_agent.get_balance(address=agent.contract_address) > allocation_value


def test_collect_policy_reward(testerchain, agent, three_agents, token_economics):
    _token_agent, __proxy_contract, policy_agent = three_agents
    deployer_address, beneficiary_address, author, ursula, *everybody_else = testerchain.interface.w3.eth.accounts

    _txhash = agent.deposit_as_staker(value=token_economics.minimum_allowed_locked, periods=token_economics.minimum_locked_periods)
    _txhash = agent.set_worker(worker_address=agent.beneficiary)
    testerchain.time_travel(periods=1)

    _txhash = policy_agent.create_policy(policy_id=os.urandom(16),
                                         author_address=author,
                                         value=to_wei(1, 'ether'),
                                         periods=2,
                                         initial_reward=0,
                                         node_addresses=[agent.contract_address])

    _txhash = agent.confirm_activity()
    testerchain.time_travel(periods=2)
    _txhash = agent.confirm_activity()

    old_balance = testerchain.interface.w3.eth.getBalance(account=agent.beneficiary)
    txhash = agent.collect_policy_reward()
    assert txhash  # TODO
    assert testerchain.interface.w3.eth.getBalance(account=agent.beneficiary) > old_balance


def test_withdraw_tokens(testerchain, agent, three_agents, allocation_value):
    token_agent, staker_agent, policy_agent = three_agents
    deployer_address, beneficiary_address, *everybody_else = testerchain.interface.w3.eth.accounts

    assert token_agent.get_balance(address=agent.contract_address) == agent.unvested_tokens
    with pytest.raises((TransactionFailed, ValueError)):
        agent.withdraw_tokens(value=allocation_value)
    testerchain.time_travel(seconds=TEST_DURATION)

    txhash = agent.withdraw_tokens(value=allocation_value)
    assert txhash  # TODO
    assert token_agent.get_balance(address=agent.contract_address) == 0
    assert token_agent.get_balance(address=beneficiary_address) == allocation_value
