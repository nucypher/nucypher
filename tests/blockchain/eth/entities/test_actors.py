import os
import random

import pytest

from nkms.blockchain.eth.actors import Miner
from nkms.blockchain.eth.agents import MinerAgent


def test_miner_locking_tokens(chain, mock_token_deployer, mock_miner_agent):

    miner = Miner(miner_agent=mock_miner_agent, address=chain.provider.w3.eth.accounts[1])

    an_amount_of_tokens = 1000 * mock_token_deployer._M
    miner.stake(amount=an_amount_of_tokens, locktime=mock_miner_agent._deployer._min_release_periods, auto_switch_lock=False)

    # Verify that the escrow is allowed to receive tokens
    # assert mock_miner_agent.token_agent.read().allowance(miner.address, mock_miner_agent.contract_address) == 0

    # Stake starts after one period
    # assert miner.token_balance() == 0
    # assert mock_miner_agent.read().getLockedTokens(miner.address) == 0

    # Wait for it...
    chain.time_travel(mock_miner_agent._deployer._hours_per_period)

    assert mock_miner_agent.read().getLockedTokens(miner.address) == an_amount_of_tokens


def test_mine_then_withdraw_tokens(chain, mock_token_deployer, token_agent, mock_miner_agent, mock_miner_escrow_deployer):
    """
    - Airdrop tokens to everyone
    - Create a Miner (Ursula)
    - Spawn additional miners
    - All miners lock tokens
    - Wait (with time)
    - Miner (Ursula) mints new tokens
    """

    _origin, *everybody = chain.provider.w3.eth.accounts

    ursula_address, *everyone_else = everybody

    miner = Miner(miner_agent=mock_miner_agent, address=ursula_address)

    # Miner has no locked tokens
    assert miner.locked_tokens == 0

    # Capture the initial token balance of the miner
    initial_balance = miner.token_balance()
    assert token_agent.get_balance(miner.address) == miner.token_balance()

    # Stake a random amount of tokens
    # stake_amount = (10 + random.randrange(9000)) * mock_token_deployer._M
    half_of_stake = initial_balance // 2

    miner.stake(amount=half_of_stake,
                locktime=1,
                auto_switch_lock=True)

    # Ensure the miner has the right amount of staked tokens
    assert miner.locked_tokens == half_of_stake

    # Ensure the MinerEscrow contract is allowed to receive tokens form Alice
    # assert miner.token_agent.read().allowance(miner.address, miner.miner_agent.contract_address) == half_of_stake

    # Blockchain staking starts after one period
    # assert mock_miner_agent.read().getAllLockedTokens() == 0

    # Wait for it...
    # chain.wait_time(2)

    # Have other address lock tokens
    chain.spawn_miners(miner_agent=mock_miner_agent,
                             addresses=everyone_else,
                             locktime=1,
                             m=mock_token_deployer._M)

    # The miner starts unlocking periods...


    # ...wait more...
    chain.time_travel(mock_miner_agent._deployer._hours_per_period)

    # miner.confirm_activity()

    # ...wait more...
    chain.time_travel(mock_miner_agent._deployer._hours_per_period)

    miner.mint()
    miner.collect_staking_reward()

    final_balance = token_agent.get_balance(miner.address)
    assert final_balance > initial_balance


def test_sample_miners(chain, mock_miner_agent):

    _origin, *everyone_else = chain.provider.w3.eth.accounts[1:]

    chain.spawn_miners(addresses=everyone_else, locktime=100,
                              miner_agent=mock_miner_agent, m=mock_miner_agent.token_agent._deployer._M)

    chain.time_travel(mock_miner_agent._deployer._hours_per_period)

    with pytest.raises(MinerAgent.NotEnoughUrsulas):
        mock_miner_agent.sample(quantity=100)  # Waay more than we have deployed

    miners = mock_miner_agent.sample(quantity=3)
    assert len(miners) == 3
    assert len(set(miners)) == 3


def test_publish_miner_datastore(chain, mock_miner_agent):

    miner_addr = chain.provider.w3.eth.accounts[1]

    miner = Miner(miner_agent=mock_miner_agent, address=miner_addr)

    balance = miner.token_balance()
    miner.stake(amount=balance, locktime=1)

    # Publish Miner IDs to the DHT
    some_data = os.urandom(32)
    _txhash = miner.publish_data(some_data)

    # Fetch the miner Ids
    stored_miner_ids = miner.fetch_data()

    assert len(stored_miner_ids) == 1
    assert some_data == stored_miner_ids[0]

    # Repeat, with another miner ID
    another_mock_miner_id = os.urandom(32)
    _txhash = miner.publish_data(another_mock_miner_id)

    stored_miner_ids = miner.fetch_data()

    assert len(stored_miner_ids) == 2
    assert another_mock_miner_id == stored_miner_ids[1]

    # TODO change encoding when v4 of web3.py is released
    supposedly_the_same_miner_id = mock_miner_agent.read() \
        .getMinerInfo(mock_miner_agent._deployer.MinerInfoField.MINER_ID.value,
                      miner_addr,
                      1).encode('latin-1')

    assert another_mock_miner_id == supposedly_the_same_miner_id

