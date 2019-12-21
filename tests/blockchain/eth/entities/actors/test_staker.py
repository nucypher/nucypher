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
from eth_tester.exceptions import TransactionFailed

from nucypher.blockchain.eth.actors import Staker
from nucypher.blockchain.eth.agents import ContractAgency, StakingEscrowAgent
from nucypher.blockchain.eth.token import NU, Stake
from nucypher.crypto.powers import TransactingPower
from nucypher.utilities.sandbox.blockchain import token_airdrop
from nucypher.utilities.sandbox.constants import DEVELOPMENT_TOKEN_AIRDROP_AMOUNT, INSECURE_DEVELOPMENT_PASSWORD
from nucypher.utilities.sandbox.ursula import make_decentralized_ursulas


@pytest.mark.slow()
def test_staker_locking_tokens(testerchain, agency, staker, token_economics, mock_transacting_power_activation):
    token_agent, staking_agent, policy_agent = agency

    mock_transacting_power_activation(account=staker.checksum_address, password=INSECURE_DEVELOPMENT_PASSWORD)

    assert NU(token_economics.minimum_allowed_locked, 'NuNit') < staker.token_balance, "Insufficient staker balance"

    staker.initialize_stake(amount=NU(token_economics.minimum_allowed_locked, 'NuNit'),  # Lock the minimum amount of tokens
                            lock_periods=token_economics.minimum_locked_periods)

    # Verify that the escrow is "approved" to receive tokens
    allowance = token_agent.contract.functions.allowance(
        staker.checksum_address,
        staking_agent.contract_address).call()
    assert 0 == allowance

    # Staking starts after one period
    locked_tokens = staker.locked_tokens()
    assert 0 == locked_tokens

    locked_tokens = staker.locked_tokens(periods=1)
    assert token_economics.minimum_allowed_locked == locked_tokens


@pytest.mark.slow()
@pytest.mark.usefixtures("agency")
def test_staker_divides_stake(staker, token_economics):
    stake_value = NU(token_economics.minimum_allowed_locked*5, 'NuNit')
    new_stake_value = NU(token_economics.minimum_allowed_locked*2, 'NuNit')

    stake_index = 0
    staker.initialize_stake(amount=stake_value, lock_periods=int(token_economics.minimum_locked_periods))
    staker.divide_stake(target_value=new_stake_value, stake_index=stake_index+1, additional_periods=2)

    current_period = staker.staking_agent.get_current_period()
    expected_old_stake = (current_period + 1, current_period + 30, stake_value - new_stake_value)
    expected_new_stake = (current_period + 1, current_period + 32, new_stake_value)

    assert 3 == len(staker.stakes), 'A new stake was not added to this stakers stakes'
    assert expected_old_stake == staker.stakes[stake_index + 1].to_stake_info(), 'Old stake values are invalid'
    assert expected_new_stake == staker.stakes[stake_index + 2].to_stake_info(), 'New stake values are invalid'

    yet_another_stake_value = NU(token_economics.minimum_allowed_locked, 'NuNit')
    staker.divide_stake(target_value=yet_another_stake_value, stake_index=stake_index + 2, additional_periods=2)

    expected_new_stake = (current_period + 1, current_period + 32, new_stake_value - yet_another_stake_value)
    expected_yet_another_stake = Stake(first_locked_period=current_period + 1,
                                       final_locked_period=current_period + 34,
                                       value=yet_another_stake_value,
                                       checksum_address=staker.checksum_address,
                                       index=3,
                                       staking_agent=staker.staking_agent,
                                       economics=token_economics)

    assert 4 == len(staker.stakes), 'A new stake was not added after two stake divisions'
    assert expected_old_stake == staker.stakes[stake_index + 1].to_stake_info(), 'Old stake values are invalid after two stake divisions'
    assert expected_new_stake == staker.stakes[stake_index + 2].to_stake_info(), 'New stake values are invalid after two stake divisions'
    assert expected_yet_another_stake.value == staker.stakes[stake_index + 3].value, 'Third stake values are invalid'


def test_staker_manages_restaking(testerchain, test_registry, staker):

    # Enable Restaking
    receipt = staker.enable_restaking()
    assert receipt['status'] == 1

    # Enable Restaking Lock
    staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=test_registry)
    current_period = staking_agent.get_current_period()
    terminal_period = current_period + 2

    assert not staker.restaking_lock_enabled
    receipt = staker.enable_restaking_lock(release_period=terminal_period)
    assert receipt['status'] == 1
    assert staker.restaking_lock_enabled

    with pytest.raises((TransactionFailed, ValueError)):
      staker.disable_restaking()

    # Wait until terminal period
    testerchain.time_travel(periods=2)
    receipt = staker.disable_restaking()
    assert receipt['status'] == 1
    assert not staker.restaking_lock_enabled


@pytest.mark.slow()
def test_staker_collects_staking_reward(testerchain,
                                        test_registry,
                                        staker,
                                        blockchain_ursulas,
                                        agency,
                                        token_economics,
                                        mock_transacting_power_activation,
                                        ursula_decentralized_test_config):
    token_agent, staking_agent, policy_agent = agency

    # Capture the current token balance of the staker
    initial_balance = staker.token_balance
    assert token_agent.get_balance(staker.checksum_address) == initial_balance

    mock_transacting_power_activation(account=staker.checksum_address, password=INSECURE_DEVELOPMENT_PASSWORD)

    staker.initialize_stake(amount=NU(token_economics.minimum_allowed_locked, 'NuNit'),  # Lock the minimum amount of tokens
                            lock_periods=int(token_economics.minimum_locked_periods))    # ... for the fewest number of periods

    # Get an unused address for a new worker
    worker_address = testerchain.unassigned_accounts[-1]
    staker.set_worker(worker_address=worker_address)

    # Create this worker and bond it with the staker
    ursula = make_decentralized_ursulas(ursula_config=ursula_decentralized_test_config,
                                        stakers_addresses=[staker.checksum_address],
                                        workers_addresses=[worker_address],
                                        confirm_activity=False,
                                        registry=test_registry).pop()

    # ...wait out the lock period...
    for _ in range(token_economics.minimum_locked_periods):
        testerchain.time_travel(periods=1)
        ursula.transacting_power.activate(password=INSECURE_DEVELOPMENT_PASSWORD)
        ursula.confirm_activity()

    # ...wait more...
    testerchain.time_travel(periods=2)

    mock_transacting_power_activation(account=staker.checksum_address, password=INSECURE_DEVELOPMENT_PASSWORD)

    # Profit!
    staker.collect_staking_reward()

    final_balance = token_agent.get_balance(staker.checksum_address)
    assert final_balance > initial_balance


def test_staker_manages_winding_down(testerchain,
                                     test_registry,
                                     staker,
                                     token_economics,
                                     ursula_decentralized_test_config):
    # Get worker
    ursula = make_decentralized_ursulas(ursula_config=ursula_decentralized_test_config,
                                        stakers_addresses=[staker.checksum_address],
                                        workers_addresses=[staker.worker_address],
                                        confirm_activity=False,
                                        registry=test_registry).pop()

    # Enable winding down
    testerchain.time_travel(periods=1)
    base_duration = token_economics.minimum_locked_periods + 4
    receipt = staker.enable_winding_down()
    assert receipt['status'] == 1
    assert staker.locked_tokens(base_duration) != 0
    assert staker.locked_tokens(base_duration + 1) == 0
    ursula.confirm_activity()
    assert staker.locked_tokens(base_duration) != 0
    assert staker.locked_tokens(base_duration + 1) == 0

    # Disable winding down
    testerchain.time_travel(periods=1)
    receipt = staker.disable_winding_down()
    assert receipt['status'] == 1
    assert staker.locked_tokens(base_duration - 1) != 0
    assert staker.locked_tokens(base_duration) == 0
    ursula.confirm_activity()
    assert staker.locked_tokens(base_duration) != 0
    assert staker.locked_tokens(base_duration + 1) == 0
