import os

import pytest

from nucypher.blockchain.eth.actors import Miner, PolicyAuthor
from constant_sorrow import constants


class TestMiner:

    @pytest.fixture(scope='class')
    def miner(self, testerchain, mock_token_agent, mock_miner_agent):
        mock_token_agent.token_airdrop(amount=100000 * constants.M)
        _origin, ursula, *everybody_else = testerchain.interface.w3.eth.accounts
        miner = Miner(miner_agent=mock_miner_agent, ether_address=ursula)
        return miner

    def test_miner_locking_tokens(self, testerchain, miner, mock_miner_agent):

        assert constants.MIN_ALLOWED_LOCKED < miner.token_balance(), "Insufficient miner balance"

        miner.stake(amount=constants.MIN_ALLOWED_LOCKED,         # Lock the minimum amount of tokens
                    lock_periods=constants.MIN_LOCKED_PERIODS)   # ... for the fewest number of periods

        # Verify that the escrow is "approved" to receive tokens
        assert mock_miner_agent.token_agent.contract.functions.allowance(miner.ether_address, mock_miner_agent.contract_address).call() == 0

        # Staking starts after one period
        assert mock_miner_agent.contract.functions.getLockedTokens(miner.ether_address).call() == 0

        # Wait for it...
        testerchain.time_travel(periods=1)
        assert mock_miner_agent.contract.functions.getLockedTokens(miner.ether_address).call() == constants.MIN_ALLOWED_LOCKED


    @pytest.mark.slow()
    @pytest.mark.usefixtures("mock_policy_agent")
    def test_miner_collects_staking_reward_tokens(self, testerchain, miner, mock_token_agent, mock_miner_agent):

        # Capture the current token balance of the miner
        initial_balance = miner.token_balance()
        assert mock_token_agent.get_balance(miner.ether_address) == miner.token_balance()

        miner.stake(amount=constants.MIN_ALLOWED_LOCKED,         # Lock the minimum amount of tokens
                    lock_periods=constants.MIN_LOCKED_PERIODS)   # ... for the fewest number of periods

        # Have other address lock tokens
        _origin, ursula, *everybody_else = testerchain.interface.w3.eth.accounts
        mock_miner_agent.spawn_random_miners(addresses=everybody_else)

        # ...wait out the lock period...
        for _ in range(28):
            testerchain.time_travel(periods=1)
            miner.confirm_activity()

        # ...wait more...
        testerchain.time_travel(periods=2)
        miner.mint()
        miner.collect_staking_reward()

        final_balance = mock_token_agent.get_balance(miner.ether_address)
        assert final_balance > initial_balance

    def test_publish_miner_datastore(self, miner):

        # Publish Miner IDs to the DHT
        some_data = os.urandom(32)
        _txhash = miner._publish_datastore(data=some_data)

        # Fetch the miner Ids
        stored_miner_id = miner._read_datastore(refresh=True)
        assert len(stored_miner_id) == 32

        # Repeat, with another miner ID
        another_mock_miner_id = os.urandom(32)
        _txhash = miner._publish_datastore(data=another_mock_miner_id)

        stored_miner_id = miner._read_datastore(refresh=True)

        assert another_mock_miner_id == stored_miner_id

        supposedly_the_same_miner_id = miner.miner_agent.contract.functions.getMinerId(miner.ether_address, 1).call()
        assert another_mock_miner_id == supposedly_the_same_miner_id


class TestPolicyAuthor:

    @pytest.fixture(scope='class')
    def author(self, testerchain, mock_token_agent, mock_policy_agent):
        mock_token_agent.ether_airdrop(amount=100000 * constants.M)
        _origin, ursula, alice, *everybody_else = testerchain.interface.w3.eth.accounts
        miner = PolicyAuthor(ether_address=alice, policy_agent=mock_policy_agent)
        return miner

    def test_create_policy_author(self, testerchain, mock_policy_agent):
        _origin, ursula, alice, *everybody_else = testerchain.interface.w3.eth.accounts

        policy_author = PolicyAuthor(policy_agent=mock_policy_agent, ether_address=alice)
        assert policy_author.ether_address == alice
