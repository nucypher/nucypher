import os

import pytest

from nucypher.blockchain.eth.actors import Miner
from nucypher.blockchain.eth.agents import MinerAgent


@pytest.fixture(scope='module')
def miner(chain, mock_token_agent, mock_miner_agent):
    mock_token_agent.token_airdrop(amount=100000 * mock_token_agent._M)
    _origin, ursula, *everybody_else = chain.provider.w3.eth.accounts
    miner = Miner(miner_agent=mock_miner_agent, address=ursula)
    return miner


def test_miner_locking_tokens(chain, miner, mock_miner_agent):

    assert mock_miner_agent.min_allowed_locked < miner.token_balance(), "Insufficient miner balance"

    miner.stake(amount=mock_miner_agent.min_allowed_locked,    # Lock the minimum amount of tokens
                lock_periods=mock_miner_agent.min_locked_periods)   # ... for the fewest number of periods

    # Verify that the escrow is "approved" to receive tokens
    assert mock_miner_agent.token_agent.contract.functions.allowance(miner.address, mock_miner_agent.contract_address).call() == 0

    # Staking starts after one period
    assert mock_miner_agent.contract.functions.getLockedTokens(miner.address).call() == 0

    # Wait for it...
    chain.time_travel(periods=1)
    assert mock_miner_agent.contract.functions.getLockedTokens(miner.address).call() == mock_miner_agent.min_allowed_locked


def test_miner_collects_staking_reward_tokens(chain, miner, mock_token_agent, mock_miner_agent, mock_policy_agent):

    # Capture the current token balance of the miner
    initial_balance = miner.token_balance()
    assert mock_token_agent.get_balance(miner.address) == miner.token_balance()

    # Have other address lock tokens
    _origin, *everybody_else = chain.provider.w3.eth.accounts
    mock_miner_agent.spawn_random_miners(addresses=everybody_else)

    # ...wait out the lock period...
    for _ in range(28):
        chain.time_travel(periods=1)
        miner.confirm_activity()

    # ...wait more...
    chain.time_travel(periods=2)
    miner.mint()
    miner.collect_staking_reward()

    final_balance = mock_token_agent.get_balance(miner.address)
    assert final_balance > initial_balance


@pytest.mark.slow()
def test_sample_miners(chain, mock_miner_agent, mock_token_agent):
    mock_token_agent.token_airdrop(amount=100000 * mock_token_agent._M)

    # Have other address lock tokens
    _origin, ursula, *everybody_else = chain.provider.w3.eth.accounts
    mock_miner_agent.spawn_random_miners(addresses=everybody_else)

    chain.time_travel(periods=1)

    with pytest.raises(MinerAgent.NotEnoughUrsulas):
        mock_miner_agent.sample(quantity=100)  # Waay more than we have deployed

    miners = mock_miner_agent.sample(quantity=3)
    assert len(miners) == 3
    assert len(set(miners)) == 3


def test_publish_miner_datastore(miner):

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

    supposedly_the_same_miner_id = miner.miner_agent.contract.functions.getMinerId(miner.address, 1).call()
    assert another_mock_miner_id == supposedly_the_same_miner_id
