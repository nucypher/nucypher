import maya
import pytest
from constant_sorrow import constants

from nucypher.blockchain.eth.actors import Miner, PolicyAuthor
from tests.blockchain.eth.utilities import token_airdrop


class TestMiner:

    @pytest.fixture(scope='class')
    def miner(self, testerchain, three_agents):
        token_agent, miner_agent, policy_agent = three_agents
        origin, *everybody_else = testerchain.interface.w3.eth.accounts
        token_airdrop(token_agent=token_agent, origin=origin, addresses=everybody_else, amount=1000000*constants.M)
        miner = Miner(miner_agent=miner_agent, ether_address=everybody_else[0])
        return miner

    def test_miner_locking_tokens(self, testerchain, three_agents, miner):
        token_agent, miner_agent, policy_agent = three_agents
        testerchain.ether_airdrop(amount=10000)
        assert constants.MIN_ALLOWED_LOCKED < miner.token_balance, "Insufficient miner balance"

        expiration = maya.now().add(days=constants.MIN_LOCKED_PERIODS)
        miner.stake(amount=int(constants.MIN_ALLOWED_LOCKED),         # Lock the minimum amount of tokens
                    expiration=expiration)

        # Verify that the escrow is "approved" to receive tokens
        allowance = miner_agent.token_agent.contract.functions.allowance(
            miner.ether_address,
            miner_agent.contract_address).call()
        assert 0 == allowance

        # Staking starts after one period
        locked_tokens = miner_agent.contract.functions.getLockedTokens(miner.ether_address).call()
        assert 0 == locked_tokens
        locked_tokens = miner_agent.contract.functions.getLockedTokens(miner.ether_address, 1).call()
        assert constants.MIN_ALLOWED_LOCKED == locked_tokens

    @pytest.mark.usefixtures("three_agents")
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
    @pytest.mark.usefixtures("mining_ursulas")
    def test_miner_collects_staking_reward(self, testerchain, miner, three_agents):
        token_agent, miner_agent, policy_agent = three_agents

        # Capture the current token balance of the miner
        initial_balance = miner.token_balance
        assert token_agent.get_balance(miner.ether_address) == initial_balance

        miner.stake(amount=int(constants.MIN_ALLOWED_LOCKED),         # Lock the minimum amount of tokens
                    lock_periods=int(constants.MIN_LOCKED_PERIODS))   # ... for the fewest number of periods

        # ...wait out the lock period...
        for _ in range(28):
            testerchain.time_travel(periods=1)
            miner.confirm_activity()

        # ...wait more...
        testerchain.time_travel(periods=2)
        miner.mint()
        miner.collect_staking_reward()

        final_balance = token_agent.get_balance(miner.ether_address)
        assert final_balance > initial_balance


class TestPolicyAuthor:

    @pytest.fixture(scope='class')
    def author(self, testerchain, three_agents):
        token_agent, miner_agent, policy_agent = three_agents
        token_agent.ether_airdrop(amount=100000 * constants.M)
        _origin, ursula, alice, *everybody_else = testerchain.interface.w3.eth.accounts
        miner = PolicyAuthor(ether_address=alice, policy_agent=policy_agent)
        return miner

    def test_create_policy_author(self, testerchain, three_agents):
        token_agent, miner_agent, policy_agent = three_agents
        _origin, ursula, alice, *everybody_else = testerchain.interface.w3.eth.accounts
        policy_author = PolicyAuthor(policy_agent=policy_agent, ether_address=alice)
        assert policy_author.ether_address == alice
