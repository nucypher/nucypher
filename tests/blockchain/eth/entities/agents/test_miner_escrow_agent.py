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

from nucypher.blockchain.eth.agents import MinerAgent


@pytest.mark.slow()
def test_deposit_tokens(testerchain, three_agents, token_economics):
    origin, someone, *everybody_else = testerchain.interface.w3.eth.accounts
    token_agent, miner_agent, policy_agent = three_agents

    agent = miner_agent
    locked_tokens = token_economics.minimum_allowed_locked * 5

    _txhash = token_agent.approve_transfer(amount=token_economics.minimum_allowed_locked * 10,  # Approve
                                           target_address=agent.contract_address,
                                           sender_address=someone)

    _txhash = token_agent.transfer(amount=token_economics.minimum_allowed_locked * 10,      # Transfer
                                   target_address=someone,
                                   sender_address=origin)


    #
    # Deposit
    #

    txhash = agent.deposit_tokens(amount=locked_tokens,
                                  lock_periods=token_economics.minimum_locked_periods,
                                  sender_address=someone)

    # Check the receipt for the contract address success code
    receipt = testerchain.wait_for_receipt(txhash)
    assert receipt['status'] == 1, "Transaction Rejected"
    assert receipt['logs'][2]['address'] == agent.contract_address

    testerchain.time_travel(periods=1)
    balance = token_agent.get_balance(address=someone)
    assert balance == locked_tokens
    assert agent.get_locked_tokens(miner_address=someone) == locked_tokens


@pytest.mark.slow()
def test_get_miner_population(three_agents, blockchain_ursulas):
    token_agent, miner_agent, policy_agent = three_agents
    agent = miner_agent
    assert agent.get_miner_population() == len(blockchain_ursulas)


@pytest.mark.slow()
def test_get_swarm(three_agents, blockchain_ursulas):
    token_agent, miner_agent, policy_agent = three_agents
    agent = miner_agent
    swarm = agent.swarm()
    swarm_addresses = list(swarm)
    assert len(swarm_addresses) == len(blockchain_ursulas)

    # Grab a miner address from the swarm
    miner_addr = swarm_addresses[0]
    assert isinstance(miner_addr, str)

    try:
        int(miner_addr, 16)  # Verify the address is hex
    except ValueError:
        pytest.fail()


@pytest.mark.slow()
def test_locked_tokens(three_agents, blockchain_ursulas, token_economics):
    token_agent, miner_agent, policy_agent = three_agents
    agent = miner_agent
    ursula = blockchain_ursulas[2]
    locked_amount = agent.get_locked_tokens(miner_address=ursula.checksum_address)
    assert token_economics.maximum_allowed_locked >= locked_amount >= token_economics.minimum_allowed_locked


@pytest.mark.slow()
def test_get_all_stakes(three_agents, blockchain_ursulas, token_economics):
    token_agent, miner_agent, policy_agent = three_agents
    agent = miner_agent
    ursula = blockchain_ursulas[2]
    all_stakes = list(agent.get_all_stakes(miner_address=ursula.checksum_address))
    assert len(all_stakes) == 1
    stake_info = all_stakes[0]
    assert len(stake_info) == 3
    start_period, end_period, value = stake_info
    assert end_period > start_period
    assert token_economics.maximum_allowed_locked > value > token_economics.minimum_allowed_locked


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


def test_divide_stake(three_agents, token_economics):
    token_agent, miner_agent, policy_agent = three_agents
    agent = miner_agent
    testerchain = agent.blockchain
    origin, someone, *everybody_else = testerchain.interface.w3.eth.accounts

    stakes = list(agent.get_all_stakes(miner_address=someone))
    assert len(stakes) == 1

    # Approve
    _txhash = token_agent.approve_transfer(amount=token_economics.minimum_allowed_locked*2,
                                           target_address=agent.contract_address,
                                           sender_address=someone)

    # Deposit
    _txhash = agent.deposit_tokens(amount=token_economics.minimum_allowed_locked*2,
                                   lock_periods=token_economics.minimum_locked_periods,
                                   sender_address=someone)

    # Confirm Activity
    _txhash = agent.confirm_activity(node_address=someone)
    testerchain.time_travel(periods=1)

    txhash = agent.divide_stake(miner_address=someone,
                                stake_index=1,
                                target_value=token_economics.minimum_allowed_locked,
                                periods=1)

    testerchain = agent.blockchain
    receipt = testerchain.wait_for_receipt(txhash)
    assert receipt['status'] == 1, "Transaction Rejected"
    assert receipt['logs'][0]['address'] == agent.contract_address

    stakes = list(agent.get_all_stakes(miner_address=someone))
    assert len(stakes) == 3


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

    txhash = agent.collect_staking_reward(checksum_address=someone)
    receipt = testerchain.wait_for_receipt(txhash)
    assert receipt['status'] == 1, "Transaction Rejected"
    assert receipt['logs'][-1]['address'] == agent.contract_address

    new_balance = token_agent.get_balance(address=someone)  # not the shoes
    assert new_balance > old_balance
