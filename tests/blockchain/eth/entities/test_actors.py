import math
import os

import maya
import pytest

from nucypher.blockchain.eth.actors import Miner, PolicyAuthor
from constant_sorrow import constants
from tests.blockchain.eth.utilities import token_airdrop


class TestMiner:

    @pytest.fixture(scope='class')
    def miner(self, testerchain, mock_token_agent, mock_miner_agent):
        origin, *everybody_else = testerchain.interface.w3.eth.accounts
        token_airdrop(mock_token_agent, origin=origin, addresses=everybody_else, amount=1000000*constants.M)
        miner = Miner(miner_agent=mock_miner_agent, ether_address=everybody_else[0])
        return miner

    @pytest.mark.usefixtures("mock_policy_agent")
    def test_miner_locking_tokens(self, testerchain, miner, mock_miner_agent):

        testerchain.ether_airdrop(amount=10000)
        assert constants.MIN_ALLOWED_LOCKED < miner.token_balance, "Insufficient miner balance"

        expiration = maya.now().add(days=constants.MIN_LOCKED_PERIODS)
        miner.stake(amount=int(constants.MIN_ALLOWED_LOCKED),         # Lock the minimum amount of tokens
                    expiration=expiration)

        # Verify that the escrow is "approved" to receive tokens
        allowance = mock_miner_agent.token_agent.contract.functions.allowance(
            miner.ether_address,
            mock_miner_agent.contract_address).call()
        assert 0 == allowance

        # Staking starts after one period
        locked_tokens = mock_miner_agent.contract.functions.getLockedTokens(miner.ether_address).call()
        assert 0 == locked_tokens
        locked_tokens = mock_miner_agent.contract.functions.getLockedTokens(miner.ether_address, 1).call()
        assert constants.MIN_ALLOWED_LOCKED == locked_tokens

    @pytest.mark.usefixtures("mock_policy_agent")
    def test_miner_divides_stake(self, miner):
        current_period = miner.miner_agent.get_current_period()
        stake_value = int(constants.MIN_ALLOWED_LOCKED) * 5
        new_stake_value = int(constants.MIN_ALLOWED_LOCKED) * 2

        stake_index = len(list(miner.stakes))
        miner.stake(amount=stake_value, lock_periods=int(constants.MIN_LOCKED_PERIODS))
        miner.divide_stake(target_value=new_stake_value, stake_index=stake_index, additional_periods=2)

        stakes = list(miner.stakes)
        expected_old_stake = (current_period + 1, current_period + 30, stake_value - new_stake_value)
        expected_new_stake = (current_period + 1, current_period + 32, new_stake_value)

        assert stake_index + 2 == len(stakes), 'A new stake was not added to this miners stakes'
        assert expected_old_stake == stakes[stake_index], 'Old stake values are invalid'
        assert expected_new_stake == stakes[stake_index + 1], 'New stake values are invalid'

        yet_another_stake_value = int(constants.MIN_ALLOWED_LOCKED)
        miner.divide_stake(target_value=yet_another_stake_value, stake_index=stake_index + 1, additional_periods=2)

        stakes = list(miner.stakes)
        expected_new_stake = (current_period + 1, current_period + 32, new_stake_value - yet_another_stake_value)
        expected_yet_another_stake = (current_period + 1, current_period + 34, yet_another_stake_value)

        assert stake_index + 3 == len(stakes), 'A new stake was not added after two stake divisions'
        assert expected_old_stake == stakes[stake_index], 'Old stake values are invalid after two stake divisions'
        assert expected_new_stake == stakes[stake_index + 1], 'New stake values are invalid after two stake divisions'
        assert expected_yet_another_stake == stakes[stake_index + 2], 'Third stake values are invalid'

    @pytest.mark.slow()
    @pytest.mark.usefixtures("mock_policy_agent")
    def test_miner_collects_staking_reward(self, deployed_testerchain, miner, mock_token_agent, mock_miner_agent):

        # Capture the current token balance of the miner
        initial_balance = miner.token_balance
        assert mock_token_agent.get_balance(miner.ether_address) == initial_balance

        miner.stake(amount=int(constants.MIN_ALLOWED_LOCKED),         # Lock the minimum amount of tokens
                    lock_periods=int(constants.MIN_LOCKED_PERIODS))   # ... for the fewest number of periods

        # Have other address lock tokens
        _origin, ursula, *everybody_else = deployed_testerchain.interface.w3.eth.accounts
        mock_miner_agent.spawn_random_miners(addresses=everybody_else)

        # ...wait out the lock period...
        for _ in range(28):
            deployed_testerchain.time_travel(periods=1)
            miner.confirm_activity()

        # ...wait more...
        deployed_testerchain.time_travel(periods=2)
        miner.mint()
        miner.collect_staking_reward()

        final_balance = mock_token_agent.get_balance(miner.ether_address)
        assert final_balance > initial_balance


class TestPolicyAuthor:

    @pytest.fixture(scope='class')
    def author(self, deployed_testerchain, mock_token_agent, mock_policy_agent):
        mock_token_agent.ether_airdrop(amount=100000 * constants.M)
        _origin, ursula, alice, *everybody_else = deployed_testerchain.interface.w3.eth.accounts
        miner = PolicyAuthor(ether_address=alice, policy_agent=mock_policy_agent)
        return miner

    def test_create_policy_author(self, deployed_testerchain, mock_policy_agent):
        _origin, ursula, alice, *everybody_else = deployed_testerchain.interface.w3.eth.accounts
        policy_author = PolicyAuthor(policy_agent=mock_policy_agent, ether_address=alice)
        assert policy_author.ether_address == alice
