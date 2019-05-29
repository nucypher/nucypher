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

from nucypher.blockchain.eth.actors import Staker
from nucypher.blockchain.eth.agents import Agency
from nucypher.blockchain.eth.token import NU, Stake
from nucypher.utilities.sandbox.blockchain import token_airdrop
from nucypher.utilities.sandbox.constants import DEVELOPMENT_TOKEN_AIRDROP_AMOUNT


@pytest.fixture(scope='module')
def staker(testerchain, three_agents):
    token_agent, staker_agent, policy_agent = three_agents
    origin, *everybody_else = testerchain.interface.w3.eth.accounts
    token_airdrop(token_agent, origin=testerchain.etherbase_account, addresses=everybody_else, amount=DEVELOPMENT_TOKEN_AIRDROP_AMOUNT)
    staker = Staker(checksum_address=everybody_else[0], is_me=True)
    return staker


@pytest.mark.slow()
def test_staker_locking_tokens(testerchain, three_agents, staker, token_economics):
    token_agent, staker_agent, policy_agent = three_agents

    assert NU(token_economics.minimum_allowed_locked, 'NuNit') < staker.token_balance, "Insufficient staker balance"

    staker.initialize_stake(amount=NU(token_economics.minimum_allowed_locked, 'NuNit'),  # Lock the minimum amount of tokens
                           lock_periods=token_economics.minimum_locked_periods)

    # Verify that the escrow is "approved" to receive tokens
    allowance = token_agent.contract.functions.allowance(
        staker.checksum_address,
        staker_agent.contract_address).call()
    assert 0 == allowance

    # Staking starts after one period
    locked_tokens = staker_agent.contract.functions.getLockedTokens(staker.checksum_address).call()
    assert 0 == locked_tokens

    locked_tokens = staker_agent.contract.functions.getLockedTokens(staker.checksum_address, 1).call()
    assert token_economics.minimum_allowed_locked == locked_tokens


@pytest.mark.slow()
@pytest.mark.usefixtures("three_agents")
def test_staker_divides_stake(staker, token_economics):
    stake_value = NU(token_economics.minimum_allowed_locked*5, 'NuNit')
    new_stake_value = NU(token_economics.minimum_allowed_locked*2, 'NuNit')

    stake_index = 0
    staker.initialize_stake(amount=stake_value, lock_periods=int(token_economics.minimum_locked_periods))
    staker.divide_stake(target_value=new_stake_value, stake_index=stake_index+1, additional_periods=2)

    current_period = staker.staker_agent.get_current_period()
    expected_old_stake = (current_period + 1, current_period + 30, stake_value - new_stake_value)
    expected_new_stake = (current_period + 1, current_period + 32, new_stake_value)

    assert 3 == len(staker.stakes), 'A new stake was not added to this stakers stakes'
    assert expected_old_stake == staker.stakes[stake_index + 1].to_stake_info(), 'Old stake values are invalid'
    assert expected_new_stake == staker.stakes[stake_index + 2].to_stake_info(), 'New stake values are invalid'

    yet_another_stake_value = NU(token_economics.minimum_allowed_locked, 'NuNit')
    staker.divide_stake(target_value=yet_another_stake_value, stake_index=stake_index + 2, additional_periods=2)

    expected_new_stake = (current_period + 1, current_period + 32, new_stake_value - yet_another_stake_value)
    expected_yet_another_stake = Stake(start_period=current_period + 1,
                                       end_period=current_period + 34,
                                       value=yet_another_stake_value,
                                       staker=staker,
                                       index=3)

    assert 4 == len(staker.stakes), 'A new stake was not added after two stake divisions'
    assert expected_old_stake == staker.stakes[stake_index + 1].to_stake_info(), 'Old stake values are invalid after two stake divisions'
    assert expected_new_stake == staker.stakes[stake_index + 2].to_stake_info(), 'New stake values are invalid after two stake divisions'
    assert expected_yet_another_stake == staker.stakes[stake_index + 3], 'Third stake values are invalid'


@pytest.mark.slow()
@pytest.mark.usefixtures("blockchain_ursulas")
def test_staker_collects_staking_reward(testerchain, staker, three_agents, token_economics):
    token_agent, staker_agent, policy_agent = three_agents

    # Capture the current token balance of the staker
    initial_balance = staker.token_balance
    assert token_agent.get_balance(staker.checksum_address) == initial_balance

    staker.initialize_stake(amount=NU(token_economics.minimum_allowed_locked, 'NuNit'),  # Lock the minimum amount of tokens
                           lock_periods=int(token_economics.minimum_locked_periods))    # ... for the fewest number of periods
    staker.set_worker(worker_address=staker.checksum_public_address)

    # ...wait out the lock period...
    for _ in range(token_economics.minimum_locked_periods):
        testerchain.time_travel(periods=1)
        staker.confirm_activity()

    # ...wait more...
    testerchain.time_travel(periods=2)
    staker.collect_staking_reward()

    final_balance = token_agent.get_balance(staker.checksum_address)
    assert final_balance > initial_balance
