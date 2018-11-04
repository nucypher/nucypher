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
import maya
import pytest

from nucypher.blockchain.eth import constants
from nucypher.blockchain.eth.actors import Miner
from nucypher.utilities.sandbox.blockchain import token_airdrop
from nucypher.utilities.sandbox.constants import DEVELOPMENT_TOKEN_AIRDROP_AMOUNT


@pytest.fixture(scope='module')
def miner(testerchain, three_agents):
    token_agent, miner_agent, policy_agent = three_agents
    origin, *everybody_else = testerchain.interface.w3.eth.accounts
    token_airdrop(token_agent, origin=origin, addresses=everybody_else, amount=DEVELOPMENT_TOKEN_AIRDROP_AMOUNT)
    miner = Miner(checksum_address=everybody_else[0], is_me=True)
    return miner


@pytest.mark.slow()
def test_miner_locking_tokens(testerchain, three_agents, miner):
    token_agent, miner_agent, policy_agent = three_agents
    # testerchain.ether_airdrop(amount=10000)

    assert constants.MIN_ALLOWED_LOCKED < miner.token_balance, "Insufficient miner balance"

    expiration = maya.now().add(days=constants.MIN_LOCKED_PERIODS)
    miner.initialize_stake(amount=int(constants.MIN_ALLOWED_LOCKED),  # Lock the minimum amount of tokens
                           expiration=expiration)

    # Verify that the escrow is "approved" to receive tokens
    allowance = token_agent.contract.functions.allowance(
        miner.checksum_public_address,
        miner_agent.contract_address).call()
    assert 0 == allowance

    # Staking starts after one period
    locked_tokens = miner_agent.contract.functions.getLockedTokens(miner.checksum_public_address).call()
    assert 0 == locked_tokens

    # testerchain.time_travel(periods=1)

    locked_tokens = miner_agent.contract.functions.getLockedTokens(miner.checksum_public_address, 1).call()
    assert constants.MIN_ALLOWED_LOCKED == locked_tokens


@pytest.mark.slow()
@pytest.mark.usefixtures("three_agents")
def test_miner_divides_stake(miner):
    current_period = miner.miner_agent.get_current_period()
    stake_value = int(constants.MIN_ALLOWED_LOCKED) * 5
    new_stake_value = int(constants.MIN_ALLOWED_LOCKED) * 2

    stake_index = len(list(miner.stakes))
    miner.initialize_stake(amount=stake_value, lock_periods=int(constants.MIN_LOCKED_PERIODS))
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
@pytest.mark.usefixtures("blockchain_ursulas")
def test_miner_collects_staking_reward(testerchain, miner, three_agents):
    token_agent, miner_agent, policy_agent = three_agents

    # Capture the current token balance of the miner
    initial_balance = miner.token_balance
    assert token_agent.get_balance(miner.checksum_public_address) == initial_balance

    miner.initialize_stake(amount=int(constants.MIN_ALLOWED_LOCKED),  # Lock the minimum amount of tokens
                           lock_periods=int(constants.MIN_LOCKED_PERIODS))   # ... for the fewest number of periods

    # ...wait out the lock period...
    for _ in range(28):
        testerchain.time_travel(periods=1)
        miner.confirm_activity()

    # ...wait more...
    testerchain.time_travel(periods=2)
    miner.mint()
    miner.collect_staking_reward(collector_address=miner.checksum_public_address)

    final_balance = token_agent.get_balance(miner.checksum_public_address)
    assert final_balance > initial_balance


