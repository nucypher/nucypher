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


import maya
import pytest

from nucypher.blockchain.eth.actors import Miner
from nucypher.blockchain.eth.constants import MIN_ALLOWED_LOCKED, MIN_LOCKED_PERIODS
from nucypher.blockchain.eth.utils import NU, Stake
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

    assert NU(MIN_ALLOWED_LOCKED, 'NUWei') < miner.token_balance, "Insufficient miner balance"

    expiration = maya.now().add(days=MIN_LOCKED_PERIODS)
    miner.initialize_stake(amount=NU(MIN_ALLOWED_LOCKED, 'NUWei'),  # Lock the minimum amount of tokens
                           expiration=expiration)

    # Verify that the escrow is "approved" to receive tokens
    allowance = token_agent.contract.functions.allowance(
        miner.checksum_public_address,
        miner_agent.contract_address).call()
    assert 0 == allowance

    # Staking starts after one period
    locked_tokens = miner_agent.contract.functions.getLockedTokens(miner.checksum_public_address).call()
    assert 0 == locked_tokens

    locked_tokens = miner_agent.contract.functions.getLockedTokens(miner.checksum_public_address, 1).call()
    assert MIN_ALLOWED_LOCKED == locked_tokens


@pytest.mark.slow()
@pytest.mark.usefixtures("three_agents")
def test_miner_divides_stake(miner):
    stake_value = NU(MIN_ALLOWED_LOCKED*5, 'NUWei')
    new_stake_value = NU(MIN_ALLOWED_LOCKED*2, 'NUWei')

    stake_index = 0
    miner.initialize_stake(amount=stake_value, lock_periods=int(MIN_LOCKED_PERIODS))
    miner.divide_stake(target_value=new_stake_value, stake_index=stake_index+1, additional_periods=2)

    current_period = miner.miner_agent.get_current_period()
    expected_old_stake = (current_period + 1, current_period + 30, stake_value - new_stake_value)
    expected_new_stake = (current_period + 1, current_period + 32, new_stake_value)

    assert 3 == len(miner.stakes), 'A new stake was not added to this miners stakes'
    assert expected_old_stake == miner.stakes[stake_index+1].to_stake_info(), 'Old stake values are invalid'
    assert expected_new_stake == miner.stakes[stake_index + 2].to_stake_info(), 'New stake values are invalid'

    yet_another_stake_value = NU(MIN_ALLOWED_LOCKED, 'NUWei')
    miner.divide_stake(target_value=yet_another_stake_value, stake_index=stake_index + 2, additional_periods=2)

    expected_new_stake = (current_period + 1, current_period + 32, new_stake_value - yet_another_stake_value)
    expected_yet_another_stake = Stake(start_period=current_period + 1,
                                       end_period=current_period + 34,
                                       value=yet_another_stake_value,
                                       owner=miner)

    assert 4 == len(miner.stakes), 'A new stake was not added after two stake divisions'
    assert expected_old_stake == miner.stakes[stake_index + 1].to_stake_info(), 'Old stake values are invalid after two stake divisions'
    assert expected_new_stake == miner.stakes[stake_index + 2].to_stake_info(), 'New stake values are invalid after two stake divisions'
    assert expected_yet_another_stake == miner.stakes[stake_index + 3], 'Third stake values are invalid'


@pytest.mark.slow()
@pytest.mark.usefixtures("blockchain_ursulas")
def test_miner_collects_staking_reward(testerchain, miner, three_agents):
    token_agent, miner_agent, policy_agent = three_agents

    # Capture the current token balance of the miner
    initial_balance = miner.token_balance
    assert token_agent.get_balance(miner.checksum_public_address) == initial_balance

    miner.initialize_stake(amount=NU(MIN_ALLOWED_LOCKED, 'NUWei'),  # Lock the minimum amount of tokens
                           lock_periods=int(MIN_LOCKED_PERIODS))    # ... for the fewest number of periods

    # ...wait out the lock period...
    for _ in range(MIN_LOCKED_PERIODS):
        testerchain.time_travel(periods=1)
        miner.confirm_activity()

    # ...wait more...
    testerchain.time_travel(periods=2)
    miner.collect_staking_reward()

    final_balance = token_agent.get_balance(miner.checksum_public_address)
    assert final_balance > initial_balance
