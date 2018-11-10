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
import pytest

from nucypher.blockchain.eth.agents import MinerAgent
from nucypher.blockchain.eth.constants import MIN_ALLOWED_LOCKED, MAX_ALLOWED_LOCKED, \
    MIN_LOCKED_PERIODS


@pytest.mark.slow()
def test_deposit_tokens(testerchain, three_agents):
    origin, someone, *everybody_else = testerchain.interface.w3.eth.accounts
    token_agent, miner_agent, policy_agent = three_agents

    agent = miner_agent

    _txhash = token_agent.transfer(amount=MIN_ALLOWED_LOCKED * 2,      # Transfer
                                   target_address=someone,
                                   sender_address=origin)

    _txhash = token_agent.approve_transfer(amount=MIN_ALLOWED_LOCKED,  # Approve
                                           target_address=agent.contract_address,
                                           sender_address=someone)

    #
    # Deposit
    #
    txhash = agent.deposit_tokens(amount=MIN_ALLOWED_LOCKED,
                                  lock_periods=MIN_LOCKED_PERIODS,
                                  sender_address=someone)

    # Check the receipt for the contract address success code
    receipt = testerchain.wait_for_receipt(txhash)
    assert receipt['status'] == 1, "Transaction Rejected"
    assert receipt['logs'][1]['address'] == agent.contract_address

    testerchain.time_travel(periods=1)
    assert agent.get_locked_tokens(miner_address=someone) == MIN_ALLOWED_LOCKED
    balance = token_agent.get_balance(address=someone)
    assert balance == MIN_ALLOWED_LOCKED


@pytest.mark.slow()
def test_get_miner_population(three_agents, blockchain_ursulas):
    token_agent, miner_agent, policy_agent = three_agents
    agent = miner_agent
    assert agent.get_miner_population() == len(blockchain_ursulas) + 1


@pytest.mark.slow()
def test_get_swarm(three_agents, blockchain_ursulas):
    token_agent, miner_agent, policy_agent = three_agents
    agent = miner_agent
    swarm = agent.swarm()
    swarm_addresses = list(swarm)
    assert len(swarm_addresses) == len(blockchain_ursulas) + 1

    # Grab a miner address from the swarm
    miner_addr = swarm_addresses[0]
    assert isinstance(miner_addr, str)

    try:
        int(miner_addr, 16)  # Verify the address is hex
    except ValueError:
        pytest.fail()


@pytest.mark.slow()
def test_locked_tokens(three_agents, blockchain_ursulas):
    token_agent, miner_agent, policy_agent = three_agents
    agent = miner_agent
    ursula = blockchain_ursulas.pop()
    locked_amount = agent.get_locked_tokens(miner_address=ursula.checksum_public_address)
    assert MAX_ALLOWED_LOCKED > locked_amount > MIN_ALLOWED_LOCKED


@pytest.mark.slow()
def test_get_all_stakes(three_agents, blockchain_ursulas):
    token_agent, miner_agent, policy_agent = three_agents
    agent = miner_agent
    ursula = blockchain_ursulas.pop()
    all_stakes = list(agent.get_all_stakes(miner_address=ursula.checksum_public_address))
    assert len(all_stakes) == 1
    stake_info = all_stakes[0]
    assert len(stake_info) == 3
    start_period, end_period, value = stake_info
    assert end_period > start_period
    assert MAX_ALLOWED_LOCKED > value > MIN_ALLOWED_LOCKED


def get_stake_info(three_agents):
    assert False


@pytest.mark.slow()
@pytest.mark.usefixtures("blockchain_ursulas")
def test_sample_miners(three_agents):
    token_agent, miner_agent, policy_agent = three_agents
    agent = miner_agent
    miners_population = agent.get_miner_population()

    with pytest.raises(MinerAgent.NotEnoughMiners):
        agent.sample(quantity=miners_population + 1, duration=1)  # One more than we have deployed

    miners = agent.sample(quantity=3, duration=5)
    assert len(miners) == 3       # Three...
    assert len(set(miners)) == 3  # ...unique addresses


def test_get_current_period(three_agents):
    token_agent, miner_agent, policy_agent = three_agents
    agent = miner_agent
    testerchain = agent.blockchain
    start_period = agent.get_current_period()
    testerchain.time_travel(periods=1)
    end_period = agent.get_current_period()
    assert end_period > start_period


@pytest.mark.slow()
def test_confirm_activity(three_agents):
    token_agent, miner_agent, policy_agent = three_agents
    agent = miner_agent
    testerchain = agent.blockchain
    origin, someone, *everybody_else = testerchain.interface.w3.eth.accounts
    txhash = agent.confirm_activity(node_address=someone)
    testerchain = agent.blockchain
    receipt = testerchain.wait_for_receipt(txhash)
    assert receipt['status'] == 1, "Transaction Rejected"
    assert receipt['logs'][0]['address'] == agent.contract_address


@pytest.mark.skip('To be implemented')
def test_divide_stake(three_agents):
    token_agent, miner_agent, policy_agent = three_agents
    agent = miner_agent
    testerchain = agent.blockchain
    origin, someone, *everybody_else = testerchain.interface.w3.eth.accounts
    token_agent = agent.token_agent

    stakes = list(agent.get_all_stakes(miner_address=someone))
    assert len(stakes) == 1

    # Approve
    _txhash = token_agent.approve_transfer(amount=MIN_ALLOWED_LOCKED*2,
                                           target_address=agent.contract_address,
                                           sender_address=someone)

    # Deposit
    _txhash = agent.deposit_tokens(amount=MIN_ALLOWED_LOCKED*2,
                                   lock_periods=MIN_LOCKED_PERIODS,
                                   sender_address=someone)

    # Confirm Activity
    _txhash = agent.confirm_activity(node_address=someone)
    testerchain.time_travel(periods=1)

    txhash = agent.divide_stake(miner_address=someone,
                                stake_index=1,
                                target_value=MIN_ALLOWED_LOCKED,
                                periods=1)

    testerchain = agent.blockchain
    receipt = testerchain.wait_for_receipt(txhash)
    assert receipt['status'] == 1, "Transaction Rejected"
    assert receipt['logs'][0]['address'] == agent.contract_address

    stakes = list(agent.get_all_stakes(miner_address=someone))
    assert len(stakes) == 2


@pytest.mark.slow()
def test_collect_staking_reward(three_agents):
    token_agent, miner_agent, policy_agent = three_agents
    agent = miner_agent
    testerchain = agent.blockchain
    origin, someone, *everybody_else = testerchain.interface.w3.eth.accounts

    # Confirm Activity
    _txhash = agent.confirm_activity(node_address=someone)
    testerchain.time_travel(periods=1)

    old_balance = token_agent.get_balance(address=someone)

    txhash = agent.collect_staking_reward(collector_address=someone)
    receipt = testerchain.wait_for_receipt(txhash)
    assert receipt['status'] == 1, "Transaction Rejected"
    assert receipt['logs'][-1]['address'] == agent.contract_address

    new_balance = token_agent.get_balance(address=someone)  # not the shoes
    assert new_balance > old_balance
