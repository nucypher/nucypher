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

from nucypher.blockchain.eth.agents import StakingEscrow


@pytest.mark.slow()
def test_deposit_tokens(testerchain, agency, token_economics):
    origin, someone, *everybody_else = testerchain.interface.w3.eth.accounts
    token_agent, staking_agent, policy_agent = agency

    agent = staking_agent
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
    assert agent.get_locked_tokens(staker_address=someone) == locked_tokens


@pytest.mark.slow()
def test_get_staker_population(agency, blockchain_ursulas):
    token_agent, staking_agent, policy_agent = agency
    agent = staking_agent
    assert agent.get_staker_population() == len(blockchain_ursulas)


@pytest.mark.slow()
def test_get_swarm(agency, blockchain_ursulas):
    token_agent, staking_agent, policy_agent = agency
    agent = staking_agent
    swarm = agent.swarm()
    swarm_addresses = list(swarm)
    assert len(swarm_addresses) == len(blockchain_ursulas)

    # Grab a staker address from the swarm
    staker_addr = swarm_addresses[0]
    assert isinstance(staker_addr, str)

    try:
        int(staker_addr, 16)  # Verify the address is hex
    except ValueError:
        pytest.fail()


@pytest.mark.slow()
def test_locked_tokens(agency, blockchain_ursulas, token_economics):
    token_agent, staking_agent, policy_agent = agency
    agent = staking_agent
    ursula = blockchain_ursulas[2]
    locked_amount = agent.get_locked_tokens(staker_address=ursula.checksum_address)
    assert token_economics.maximum_allowed_locked >= locked_amount >= token_economics.minimum_allowed_locked


@pytest.mark.slow()
def test_get_all_stakes(agency, blockchain_ursulas, token_economics):
    token_agent, staking_agent, policy_agent = agency
    agent = staking_agent
    ursula = blockchain_ursulas[2]
    all_stakes = list(agent.get_all_stakes(staker_address=ursula.checksum_address))
    assert len(all_stakes) == 1
    stake_info = all_stakes[0]
    assert len(stake_info) == 3
    start_period, end_period, value = stake_info
    assert end_period > start_period
    assert token_economics.maximum_allowed_locked > value > token_economics.minimum_allowed_locked


@pytest.mark.slow()
@pytest.mark.usefixtures("blockchain_ursulas")
def test_sample_stakers(agency):
    token_agent, staking_agent, policy_agent = agency
    agent = staking_agent
    stakers_population = agent.get_staker_population()

    with pytest.raises(StakingEscrow.NotEnoughStakers):
        agent.sample(quantity=stakers_population + 1, duration=1)  # One more than we have deployed

    stakers = agent.sample(quantity=3, duration=5)
    assert len(stakers) == 3       # Three...
    assert len(set(stakers)) == 3  # ...unique addresses


def test_get_current_period(agency):
    token_agent, staking_agent, policy_agent = agency
    agent = staking_agent
    testerchain = agent.blockchain
    start_period = agent.get_current_period()
    testerchain.time_travel(periods=1)
    end_period = agent.get_current_period()
    assert end_period > start_period


@pytest.mark.slow()
def test_confirm_activity(agency):
    token_agent, staking_agent, policy_agent = agency
    agent = staking_agent
    testerchain = agent.blockchain
    origin, someone, *everybody_else = testerchain.interface.w3.eth.accounts
    _txhash = agent.set_worker(node_address=someone, worker_address=someone)
    txhash = agent.confirm_activity(node_address=someone)
    testerchain = agent.blockchain
    receipt = testerchain.wait_for_receipt(txhash)
    assert receipt['status'] == 1, "Transaction Rejected"
    assert receipt['logs'][0]['address'] == agent.contract_address


@pytest.mark.skip('To be implemented')
def test_divide_stake(agency, token_economics):
    token_agent, staking_agent, policy_agent = agency
    agent = staking_agent
    testerchain = agent.blockchain
    origin, someone, *everybody_else = testerchain.interface.w3.eth.accounts

    stakes = list(agent.get_all_stakes(staker_address=someone))
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

    txhash = agent.divide_stake(staker_address=someone,
                                stake_index=1,
                                target_value=token_economics.minimum_allowed_locked,
                                periods=1)

    testerchain = agent.blockchain
    receipt = testerchain.wait_for_receipt(txhash)
    assert receipt['status'] == 1, "Transaction Rejected"
    assert receipt['logs'][0]['address'] == agent.contract_address

    stakes = list(agent.get_all_stakes(staker_address=someone))
    assert len(stakes) == 3


@pytest.mark.slow()
def test_collect_staking_reward(agency):
    token_agent, staking_agent, policy_agent = agency
    agent = staking_agent
    testerchain = agent.blockchain
    origin, someone, *everybody_else = testerchain.interface.w3.eth.accounts

    # Confirm Activity
    _txhash = agent.confirm_activity(node_address=someone)
    testerchain.time_travel(periods=2)

    # Mint
    _txhash = agent.mint(node_address=someone)

    old_balance = token_agent.get_balance(address=someone)

    txhash = agent.collect_staking_reward(checksum_address=someone)
    receipt = testerchain.wait_for_receipt(txhash)
    assert receipt['status'] == 1, "Transaction Rejected"
    assert receipt['logs'][-1]['address'] == agent.contract_address

    new_balance = token_agent.get_balance(address=someone)  # not the shoes
    assert new_balance > old_balance
