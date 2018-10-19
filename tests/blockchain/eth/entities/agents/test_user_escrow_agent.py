import os

import maya
import pytest
from eth_utils import is_checksum_address

from nucypher.blockchain.eth.agents import UserEscrowAgent
from nucypher.blockchain.eth.constants import MIN_ALLOWED_LOCKED, MIN_LOCKED_PERIODS, MAX_MINTING_PERIODS, \
    DISPATCHER_SECRET_LENGTH
from nucypher.blockchain.eth.deployers import UserEscrowDeployer, UserEscrowProxyDeployer
from nucypher.blockchain.eth.registry import InMemoryAllocationRegistry

TEST_ALLOCATION = MIN_ALLOWED_LOCKED*10
registry = InMemoryAllocationRegistry()


@pytest.mark.usefixtures("three_agents")
@pytest.fixture(scope='module')
def agent(three_agents, testerchain):
    deployer_address, beneficiary_address, *everybody_else = testerchain.interface.w3.eth.accounts

    # Proxy
    proxy_secret = os.urandom(DISPATCHER_SECRET_LENGTH)
    proxy_deployer = UserEscrowProxyDeployer(deployer_address=deployer_address,
                                             secret_hash=proxy_secret)
    assert proxy_deployer.arm()
    proxy_deployer.deploy()

    # Escrow
    escrow_deployer = UserEscrowDeployer(deployer_address=deployer_address,
                                         allocation_registry=registry)
    assert escrow_deployer.arm()
    _txhash = escrow_deployer.deploy()

    escrow_deployer.initial_deposit(value=TEST_ALLOCATION, duration=MIN_LOCKED_PERIODS*10)
    assert escrow_deployer.principal_contract.functions.getLockedTokens().call() == TEST_ALLOCATION
    escrow_deployer.assign_beneficiary(beneficiary_address=beneficiary_address)
    escrow_deployer.enroll_principal_contract()
    assert escrow_deployer.principal_contract.functions.getLockedTokens().call() == TEST_ALLOCATION
    _agent = escrow_deployer.make_agent()

    _direct_agent = UserEscrowAgent(blockchain=testerchain,
                                    allocation_registry=registry,
                                    beneficiary=beneficiary_address)

    assert _direct_agent == _agent
    assert _direct_agent.contract.abi == _agent.contract.abi
    assert _direct_agent.contract.address == _agent.contract.address
    assert _agent.principal_contract.address == escrow_deployer.principal_contract.address
    assert _agent.principal_contract.abi == escrow_deployer.principal_contract.abi
    assert _direct_agent.contract.abi == escrow_deployer.principal_contract.abi
    assert _direct_agent.contract.address == escrow_deployer.principal_contract.address

    yield _agent
    testerchain.interface.registry.clear()


def test_user_escrow_agent_represents_beneficiary(agent, three_agents):
    token_agent, miner_agent, policy_agent = three_agents

    # Name
    assert agent.registry_contract_name == UserEscrowAgent.registry_contract_name

    # Not Equal to MinerAgent
    assert agent != miner_agent, "UserEscrow Agent is connected to the MinerEscrow's contract"
    assert agent.contract_address != miner_agent.contract_address, "UserEscrow and MinerEscrow agents represent the same contract"

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


def test_read_allocation(agent, three_agents):
    token_agent, miner_agent, policy_agent = three_agents
    balance = token_agent.get_balance(address=agent.principal_contract.address)
    assert balance == TEST_ALLOCATION
    allocation = agent.allocation
    assert allocation > 0
    assert allocation == TEST_ALLOCATION


def test_read_locked_tokens(agent, three_agents):
    token_agent, miner_agent, policy_agent = three_agents
    balance = token_agent.get_balance(address=agent.principal_contract.address)
    assert balance == TEST_ALLOCATION
    assert agent.principal_contract.functions.getLockedTokens().call() == TEST_ALLOCATION
    assert agent.locked_tokens == TEST_ALLOCATION


@pytest.mark.usesfixtures("three_agents")
def test_read_timestamp(agent):
    timestamp = agent.end_timestamp
    end_locktime = maya.MayaDT(timestamp)
    assert end_locktime.slang_time()
    now = maya.now()
    assert now < end_locktime, '{} is not in the future!'.format(end_locktime.slang_date())


@pytest.mark.usesfixtures("three_agents")
def test_deposit_as_miner(testerchain, agent, three_agents):
    old_locked_value = agent.principal_contract.functions.lockedValue().call()
    txhash = agent.deposit_as_miner(value=MIN_ALLOWED_LOCKED, periods=MIN_LOCKED_PERIODS)
    assert txhash
    new_locked_value = agent.principal_contract.functions.lockedValue().call()
    assert new_locked_value > old_locked_value


@pytest.mark.usesfixtures("three_agents")
def test_withdraw_as_miner(agent, testerchain):
    testerchain.time_travel(periods=1)

    txhash = agent.withdraw_as_miner(value=MIN_ALLOWED_LOCKED)
    assert txhash


def test_withdraw_eth(testerchain, agent, three_agents):
    token_agent, __proxy_contract, policy_agent = three_agents
    deployer_address, beneficiary_address, *everybody_else = testerchain.interface.w3.eth.accounts
    old_balance = testerchain.interface.w3.eth.getBalance(account=beneficiary_address)
    txhash = agent.withdraw_eth()
    assert txhash
    new_balance = testerchain.interface.w3.eth.getBalance(account=beneficiary_address)
    assert new_balance > old_balance


def test_withdraw_tokens(testerchain, agent, three_agents):
    token_agent, miner_agent, policy_agent = three_agents
    deployer_address, beneficiary_address, *everybody_else = testerchain.interface.w3.eth.accounts

    old_balance = token_agent.get_balance(address=beneficiary_address)
    agent.withdraw_tokens(value=agent.allocation)
    new_balance = token_agent.get_balance(address=beneficiary_address)
    assert new_balance > old_balance
