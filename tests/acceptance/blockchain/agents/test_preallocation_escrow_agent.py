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
import maya
import os
import pytest
from eth_tester.exceptions import TransactionFailed
from eth_utils import is_checksum_address, to_wei

from nucypher.blockchain.eth.agents import PreallocationEscrowAgent
from nucypher.blockchain.eth.deployers import PreallocationEscrowDeployer
from nucypher.blockchain.eth.registry import InMemoryAllocationRegistry
from nucypher.blockchain.eth.token import NU
from tests.utils.blockchain import token_airdrop
from tests.constants import INSECURE_DEVELOPMENT_PASSWORD

TEST_LOCK_DURATION_IN_SECONDS = 60 * 60 * 24  # 1 day
TEST_ALLOCATION_REGISTRY = InMemoryAllocationRegistry()


@pytest.fixture(scope='module')
def allocation_value(token_economics):
    allocation = token_economics.minimum_allowed_locked * 10
    return allocation


@pytest.fixture(scope='function')
def agent(testerchain, test_registry, allocation_value, agency,
          mock_transacting_power_activation) -> PreallocationEscrowAgent:
    deployer_address, beneficiary_address, *everybody_else = testerchain.client.accounts

    escrow_deployer = PreallocationEscrowDeployer(deployer_address=deployer_address,
                                                  registry=test_registry,
                                                  allocation_registry=TEST_ALLOCATION_REGISTRY)

    mock_transacting_power_activation(account=deployer_address, password=INSECURE_DEVELOPMENT_PASSWORD)
    _receipt = escrow_deployer.deploy()

    escrow_deployer.initial_deposit(value=allocation_value, duration_seconds=TEST_LOCK_DURATION_IN_SECONDS)
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
    assert agent.contract_name == PreallocationEscrowAgent.contract_name

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


def test_deposit_and_withdraw_as_staker(testerchain, agent, agency, allocation_value, token_economics,
                                        mock_transacting_power_activation):
    token_agent, staking_agent, policy_agent = agency

    assert staking_agent.get_locked_tokens(staker_address=agent.contract_address) == 0
    assert staking_agent.get_locked_tokens(staker_address=agent.contract_address, periods=1) == 0
    assert agent.unvested_tokens == allocation_value
    assert token_agent.get_balance(address=agent.contract_address) == allocation_value

    mock_transacting_power_activation(account=agent.beneficiary, password=INSECURE_DEVELOPMENT_PASSWORD)

    # Move the tokens to the StakingEscrow
    receipt = agent.deposit_as_staker(amount=token_economics.minimum_allowed_locked, lock_periods=token_economics.minimum_locked_periods)
    assert receipt['status'] == 1, "Transaction Rejected"

    # Owner bonds a worker in StakingEscrow via PreallocationEscrow
    worker = testerchain.ursula_account(0)
    _receipt = agent.bond_worker(worker_address=worker)

    # Owner enables winding down
    receipt = agent.set_winding_down(value=True)
    assert receipt['status'] == 1, "Transaction Rejected"

    assert token_agent.get_balance(address=agent.contract_address) == allocation_value - token_economics.minimum_allowed_locked
    assert agent.unvested_tokens == allocation_value
    assert staking_agent.get_locked_tokens(staker_address=agent.contract_address) == 0
    assert staking_agent.get_locked_tokens(staker_address=agent.contract_address, periods=1) == token_economics.minimum_allowed_locked
    assert staking_agent.get_locked_tokens(staker_address=agent.contract_address, periods=token_economics.minimum_locked_periods) == token_economics.minimum_allowed_locked
    assert staking_agent.get_locked_tokens(staker_address=agent.contract_address, periods=token_economics.minimum_locked_periods+1) == 0

    mock_transacting_power_activation(account=worker, password=INSECURE_DEVELOPMENT_PASSWORD)

    for _ in range(token_economics.minimum_locked_periods):
        staking_agent.commit_to_next_period(worker_address=worker)
        testerchain.time_travel(periods=1)
    testerchain.time_travel(periods=1)

    mock_transacting_power_activation(account=agent.beneficiary, password=INSECURE_DEVELOPMENT_PASSWORD)
    agent.mint()

    assert staking_agent.get_locked_tokens(staker_address=agent.contract_address) == 0
    assert token_agent.get_balance(address=agent.contract_address) == allocation_value - token_economics.minimum_allowed_locked
    receipt = agent.withdraw_as_staker(value=token_economics.minimum_allowed_locked)
    assert receipt['status'] == 1, "Transaction Rejected"
    assert token_agent.get_balance(address=agent.contract_address) == allocation_value

    # Release worker
    _receipt = agent.release_worker()

    expected_rewards = staking_agent.owned_tokens(staker_address=agent.contract_address)
    assert expected_rewards > 0
    receipt = agent.withdraw_as_staker(value=expected_rewards)
    assert receipt['status'] == 1, "Transaction Rejected"
    assert token_agent.get_balance(address=agent.contract_address) == allocation_value + expected_rewards


def test_collect_policy_fees(testerchain, agent, agency, token_economics, mock_transacting_power_activation):
    _token_agent, staking_agent, policy_agent = agency
    deployer_address, beneficiary_address, author, ursula, *everybody_else = testerchain.client.accounts

    mock_transacting_power_activation(account=agent.beneficiary, password=INSECURE_DEVELOPMENT_PASSWORD)

    _receipt = agent.deposit_as_staker(amount=token_economics.minimum_allowed_locked,
                                       lock_periods=token_economics.minimum_locked_periods)

    # Owner bonds a worker in StakingEscrow via PreallocationEscrow
    worker = testerchain.ursula_account(0)
    _receipt = agent.bond_worker(worker_address=worker)

    testerchain.time_travel(periods=1)

    mock_transacting_power_activation(account=author, password=INSECURE_DEVELOPMENT_PASSWORD)
    now = testerchain.w3.eth.getBlock('latest').timestamp
    policy_id = os.urandom(16)
    _receipt = policy_agent.create_policy(policy_id=policy_id,
                                          author_address=author,
                                          value=to_wei(1, 'ether'),
                                          end_timestamp=now + token_economics.hours_per_period * 60 * 60,
                                          node_addresses=[agent.contract_address])

    mock_transacting_power_activation(account=worker, password=INSECURE_DEVELOPMENT_PASSWORD)
    staking_agent.commit_to_next_period(worker_address=worker)
    testerchain.time_travel(periods=2)
    staking_agent.commit_to_next_period(worker_address=worker)

    old_balance = testerchain.client.get_balance(account=agent.beneficiary)

    mock_transacting_power_activation(account=agent.beneficiary, password=INSECURE_DEVELOPMENT_PASSWORD)

    receipt = agent.collect_policy_fee()
    assert receipt['status'] == 1, "Transaction Rejected"
    receipt = agent.withdraw_eth()
    assert receipt['status'] == 1, "Transaction Rejected"
    assert testerchain.client.get_balance(account=agent.beneficiary) > old_balance


def test_beneficiary_withdraws_tokens(testerchain,
                                      agent,
                                      agency,
                                      allocation_value,
                                      mock_transacting_power_activation,
                                      token_economics):
    token_agent, staking_agent, policy_agent = agency
    deployer_address, beneficiary_address, *everybody_else = testerchain.client.accounts

    contract_address = agent.contract_address
    assert token_agent.get_balance(address=contract_address) == agent.unvested_tokens == agent.initial_locked_amount

    # Trying to withdraw the tokens now fails, obviously
    initial_amount = token_agent.get_balance(address=contract_address)
    with pytest.raises((TransactionFailed, ValueError)):
        agent.withdraw_tokens(value=initial_amount)

    # Let's deposit some of them (30% of initial amount)
    staked_amount = 3 * initial_amount // 10
    mock_transacting_power_activation(account=agent.beneficiary, password=INSECURE_DEVELOPMENT_PASSWORD)
    _receipt = agent.deposit_as_staker(amount=staked_amount, lock_periods=token_economics.minimum_locked_periods)

    # Trying to withdraw the remaining fails too:
    # The locked amount is equal to the initial deposit (100% of the tokens).
    # Since 30% are staked, the locked amount is reduced by that 30% when withdrawing,
    # which results in an effective lock of 70%. However, the contract also has 70%, which means that, effectively,
    # the beneficiary can only withdraw 0 tokens.
    assert agent.available_balance == 0
    with pytest.raises((TransactionFailed, ValueError)):
        agent.withdraw_tokens(value=initial_amount - staked_amount)
    agent.withdraw_tokens(value=0)

    # Now let's assume the contract has more tokens (e.g., coming from staking rewards).
    # The beneficiary should be able to collect this excess.
    mocked_rewards = NU.from_nunits(1000)
    token_airdrop(token_agent=token_agent,
                  amount=mocked_rewards,
                  origin=deployer_address,
                  addresses=[contract_address])
    assert agent.available_balance == mocked_rewards
    agent.withdraw_tokens(value=int(mocked_rewards))

    # Once the lock passes, the beneficiary can withdraw what's left
    testerchain.time_travel(seconds=TEST_LOCK_DURATION_IN_SECONDS)
    receipt = agent.withdraw_tokens(value=initial_amount - staked_amount)
    assert receipt['status'] == 1, "Transaction Rejected"
    assert token_agent.get_balance(address=contract_address) == 0
    assert token_agent.get_balance(address=beneficiary_address) == initial_amount - staked_amount + mocked_rewards
