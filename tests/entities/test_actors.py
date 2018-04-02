import os
import random

import pytest

from nkms_eth.actors import Miner
from nkms_eth.agents import MinerAgent
from nkms_eth.deployers import PolicyManagerDeployer
from tests.utilities import spawn_miners


def test_miner_locking_tokens(testerchain, mock_token_deployer, mock_miner_agent):

    # Deploy the Policy manager
    policy_manager_deployer = PolicyManagerDeployer(miner_agent=mock_miner_agent)
    policy_manager_deployer.arm()
    policy_manager_deployer.deploy()

    mock_token_deployer._global_airdrop(amount=10000)    # weeee

    miner = Miner(miner_agent=mock_miner_agent, address=testerchain._chain.web3.eth.accounts[1])

    an_amount_of_tokens = 1000 * mock_token_deployer._M
    miner.stake(amount=an_amount_of_tokens, locktime=100)

    assert mock_miner_agent.read().getLockedTokens(miner.address) == an_amount_of_tokens

    testerchain.wait_time(mock_miner_agent._deployer._hours_per_period)

    assert mock_miner_agent.read().getAllLockedTokens() == an_amount_of_tokens


def test_mine_then_withdraw_tokens(testerchain, mock_token_deployer, token_agent, mock_miner_agent, mock_miner_escrow_deployer):
    """
    - Airdrop tokens to everyone
    - Create a Miner (Ursula)
    - Spawn additional miners
    - All miners lock tokens
    - Wait (with time)
    - Miner (Ursula) mints new tokens
    """

    mock_token_deployer._global_airdrop(amount=10000)

    _origin, *everybody = testerchain._chain.web3.eth.accounts
    ursula_address, *everyone_else = everybody

    miner = Miner(miner_agent=mock_miner_agent, address=ursula_address)
    initial_balance = miner.token_balance()

    amount = (10 + random.randrange(9000)) * mock_token_deployer._M
    miner.stake(amount=amount, locktime=3)

    testerchain.wait_time(mock_miner_agent._deployer._hours_per_period)
    assert mock_miner_agent.call().getLockedTokens(ursula_address) == amount

    spawn_miners(miner_agent=mock_miner_agent, addresses=everyone_else, locktime=1, m=mock_token_deployer._M)
    testerchain.wait_time(mock_miner_agent._deployer._hours_per_period*2)

    miner.confirm_activity()
    miner.mint()
    miner.collect_reward()

    final_balance = token_agent.balance(miner.address)
    assert final_balance > initial_balance


def test_sample_miners(testerchain, mock_token_deployer, mock_miner_agent):
    mock_token_deployer._global_airdrop(amount=10000)

    _origin, *everyone_else = testerchain._chain.web3.eth.accounts[1:]
    spawn_miners(addresses=everyone_else, locktime=100, miner_agent=mock_miner_agent, m=mock_token_deployer._M)

    testerchain.wait_time(mock_miner_agent._deployer._hours_per_period)

    with pytest.raises(MinerAgent.NotEnoughUrsulas):
        mock_miner_agent.sample(quantity=100)  # Waay more than we have deployed

    miners = mock_miner_agent.sample(quantity=3)
    assert len(miners) == 3
    assert len(set(miners)) == 3

#
# def test_publish_miner_ids(testerchain, mock_token_deployer, mock_miner_agent):
#     mock_token_deployer._global_airdrop(amount=10000)    # weeee
#
#     miner_addr = testerchain._chain.web3.eth.accounts[1]
#     miner = Miner(miner_agent=mock_miner_agent, address=miner_addr)
#
#     balance = miner.token_balance()
#     miner.lock(amount=balance, locktime=1)
#
#     # Publish Miner IDs to the DHT
#     mock_miner_id = os.urandom(32)
#     _txhash = miner.publish_miner_id(mock_miner_id)
#
#     # Fetch the miner Ids
#     stored_miner_ids = miner.fetch_miner_ids()
#
#     assert len(stored_miner_ids) == 1
#     assert mock_miner_id == stored_miner_ids[0]
#
#     # Repeat, with another miner ID
#     another_mock_miner_id = os.urandom(32)
#     _txhash = miner.publish_miner_id(another_mock_miner_id)
#
#     stored_miner_ids = miner.fetch_miner_ids()
#
#     assert len(stored_miner_ids) == 2
#     assert another_mock_miner_id == stored_miner_ids[1]
#
#     # TODO change encoding when v4 of web3.py is released
#     supposedly_the_same_miner_id = mock_miner_agent.call() \
#         .getMinerInfo(mock_miner_agent._deployer.MinerInfoField.MINER_ID.value,
#                       miner_addr,
#                       1).encode('latin-1')
#
#     assert another_mock_miner_id == supposedly_the_same_miner_id
#
