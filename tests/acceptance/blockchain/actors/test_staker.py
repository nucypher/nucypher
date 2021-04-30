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
from eth_tester.exceptions import TransactionFailed

from nucypher.blockchain.eth.agents import NucypherTokenAgent, StakingEscrowAgent, ContractAgency
from nucypher.blockchain.eth.signers.software import Web3Signer
from nucypher.blockchain.eth.token import NU, Stake
from nucypher.blockchain.eth.utils import datetime_at_period
from nucypher.crypto.powers import TransactingPower
from tests.constants import FEE_RATE_RANGE, DEVELOPMENT_TOKEN_AIRDROP_AMOUNT
from tests.utils.blockchain import token_airdrop
from tests.utils.ursula import make_decentralized_ursulas


def test_staker_locking_tokens(testerchain, agency, staker, token_economics, test_registry):
    token_agent = ContractAgency.get_agent(NucypherTokenAgent, registry=test_registry)
    staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=test_registry)

    assert NU(token_economics.minimum_allowed_locked, 'NuNit') < staker.token_balance, "Insufficient staker balance"

    # Make sure staking handles existing token allowance
    staker.token_agent.approve_transfer(1000000000, staking_agent.contract_address, staker.transacting_power)

    staker.initialize_stake(amount=NU(token_economics.minimum_allowed_locked, 'NuNit'),
                            # Lock the minimum amount of tokens
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


@pytest.mark.usefixtures("agency")
def test_staker_divides_stake(staker, token_economics):
    stake_value = NU(token_economics.minimum_allowed_locked * 5, 'NuNit')
    new_stake_value = NU(token_economics.minimum_allowed_locked * 2, 'NuNit')

    stake_index = 0
    duration = int(token_economics.minimum_locked_periods)
    staker.initialize_stake(amount=stake_value, lock_periods=duration)
    stake = staker.stakes[stake_index + 1]

    # Can't use additional periods and expiration together
    with pytest.raises(ValueError):
        staker.divide_stake(target_value=new_stake_value, stake=stake, additional_periods=2, expiration=maya.now())

    staker.divide_stake(target_value=new_stake_value, stake=stake, additional_periods=2)

    current_period = staker.staking_agent.get_current_period()
    expected_old_stake = (current_period + 1, current_period + duration, stake_value - new_stake_value)
    expected_new_stake = (current_period + 1, current_period + duration + 2, new_stake_value)

    assert 3 == len(staker.stakes), 'A new stake was not added to this stakers stakes'
    assert expected_old_stake == staker.stakes[stake_index + 1].to_stake_info(), 'Old stake values are invalid'
    assert expected_new_stake == staker.stakes[stake_index + 2].to_stake_info(), 'New stake values are invalid'

    # Provided stake must be part of current stakes
    new_stake_value = NU.from_nunits(token_economics.minimum_allowed_locked)
    with pytest.raises(ValueError):
        staker.divide_stake(target_value=new_stake_value, stake=stake, additional_periods=2)
    stake = staker.stakes[stake_index + 1]
    stake.index = len(staker.stakes)
    with pytest.raises(ValueError):
        staker.divide_stake(target_value=new_stake_value, stake=stake, additional_periods=2)

    yet_another_stake_value = NU(token_economics.minimum_allowed_locked, 'NuNit')
    stake = staker.stakes[stake_index + 2]

    # New expiration date must extend stake duration
    origin_stake = stake
    new_expiration = datetime_at_period(period=origin_stake.final_locked_period,
                                        seconds_per_period=token_economics.seconds_per_period,
                                        start_of_period=True)
    with pytest.raises(ValueError):
        staker.divide_stake(target_value=yet_another_stake_value, stake=stake, expiration=new_expiration)

    new_expiration = datetime_at_period(period=origin_stake.final_locked_period + 2,
                                        seconds_per_period=token_economics.seconds_per_period,
                                        start_of_period=True)
    staker.divide_stake(target_value=yet_another_stake_value, stake=stake, expiration=new_expiration)

    expected_new_stake = (current_period + 1, current_period + duration + 2, new_stake_value)
    expected_yet_another_stake = Stake(first_locked_period=current_period + 1,
                                       final_locked_period=current_period + duration + 4,
                                       value=yet_another_stake_value,
                                       checksum_address=staker.checksum_address,
                                       index=3,
                                       staking_agent=staker.staking_agent,
                                       economics=token_economics)

    assert 4 == len(staker.stakes), 'A new stake was not added after two stake divisions'
    assert expected_old_stake == staker.stakes[
        stake_index + 1].to_stake_info(), 'Old stake values are invalid after two stake divisions'
    assert expected_new_stake == staker.stakes[
        stake_index + 2].to_stake_info(), 'New stake values are invalid after two stake divisions'
    assert expected_yet_another_stake.value == staker.stakes[stake_index + 3].value, 'Third stake values are invalid'


@pytest.mark.usefixtures("agency")
def test_staker_prolongs_stake(staker, token_economics):
    stake_index = 0
    origin_stake = staker.stakes[stake_index]

    # Can't use additional periods and expiration together
    new_expiration = datetime_at_period(period=origin_stake.final_locked_period + 3,
                                        seconds_per_period=token_economics.seconds_per_period,
                                        start_of_period=True)
    with pytest.raises(ValueError):
        staker.prolong_stake(stake=origin_stake, additional_periods=3, expiration=new_expiration)

    staker.prolong_stake(stake=origin_stake, additional_periods=3)

    stake = staker.stakes[stake_index]
    assert stake.first_locked_period == origin_stake.first_locked_period
    assert stake.final_locked_period == origin_stake.final_locked_period + 3
    assert stake.value == origin_stake.value

    # Provided stake must be part of current stakes
    with pytest.raises(ValueError):
        staker.prolong_stake(stake=origin_stake, additional_periods=2)
    stake.index = len(staker.stakes)
    with pytest.raises(ValueError):
        staker.prolong_stake(stake=stake, additional_periods=2)
    stake.index = stake_index

    # New expiration date must extend stake duration
    origin_stake = stake
    new_expiration = datetime_at_period(period=origin_stake.final_locked_period,
                                        seconds_per_period=token_economics.seconds_per_period,
                                        start_of_period=True)
    with pytest.raises(ValueError):
        staker.prolong_stake(stake=origin_stake, expiration=new_expiration)

    new_expiration = origin_stake.unlock_datetime
    staker.prolong_stake(stake=origin_stake, expiration=new_expiration)

    stake = staker.stakes[stake_index]
    assert stake.first_locked_period == origin_stake.first_locked_period
    assert stake.final_locked_period == origin_stake.final_locked_period + 1
    assert stake.value == origin_stake.value


@pytest.mark.usefixtures("agency")
def test_staker_increases_stake(staker, token_economics):
    stake_index = 0
    origin_stake = staker.stakes[stake_index]
    additional_amount = NU.from_nunits(token_economics.minimum_allowed_locked // 100)

    with pytest.raises(ValueError):
        staker.increase_stake(stake=origin_stake)
    # Can't use amount and entire balance flag together
    with pytest.raises(ValueError):
        staker.increase_stake(stake=origin_stake, amount=additional_amount, entire_balance=True)

    staker.increase_stake(stake=origin_stake, amount=additional_amount)

    stake = staker.stakes[stake_index]
    assert stake.first_locked_period == origin_stake.first_locked_period
    assert stake.final_locked_period == origin_stake.final_locked_period
    assert stake.value == origin_stake.value + additional_amount

    # Provided stake must be part of current stakes
    with pytest.raises(ValueError):
        staker.increase_stake(stake=origin_stake, amount=additional_amount)
    stake.index = len(staker.stakes)
    with pytest.raises(ValueError):
        staker.increase_stake(stake=stake, amount=additional_amount)
    stake.index = stake_index

    # Try to increase again using entire balance
    origin_stake = stake
    balance = staker.token_balance
    staker.increase_stake(stake=stake, entire_balance=True)

    stake = staker.stakes[stake_index]
    assert stake.first_locked_period == origin_stake.first_locked_period
    assert stake.final_locked_period == origin_stake.final_locked_period
    assert stake.value == origin_stake.value + balance


def test_staker_merges_stakes(agency, staker):
    stake_index_1 = 0
    stake_index_2 = 3
    origin_stake_1 = staker.stakes[stake_index_1]
    origin_stake_2 = staker.stakes[stake_index_2]
    assert origin_stake_2.final_locked_period == origin_stake_1.final_locked_period

    staker.merge_stakes(stake_1=origin_stake_1, stake_2=origin_stake_2)

    stake = staker.stakes[stake_index_1]
    assert stake.final_locked_period == origin_stake_1.final_locked_period
    assert stake.value == origin_stake_1.value + origin_stake_2.value

    # Provided stakes must be part of current stakes
    with pytest.raises(ValueError):
        staker.merge_stakes(stake_1=origin_stake_1, stake_2=stake)
    with pytest.raises(ValueError):
        staker.merge_stakes(stake_1=stake, stake_2=origin_stake_2)
    stake.index = len(staker.stakes)
    with pytest.raises(ValueError):
        staker.merge_stakes(stake_1=stake, stake_2=staker.stakes[1])
    with pytest.raises(ValueError):
        staker.merge_stakes(stake_1=staker.stakes[1], stake_2=stake)


def test_remove_inactive_stake(agency, staker):
    stake_index = 3
    staker.refresh_stakes()
    original_stakes = list(staker.stakes)
    unused_stake = original_stakes[stake_index]
    assert unused_stake.final_locked_period == 1

    staker.remove_inactive_stake(stake=unused_stake)

    stakes = staker.stakes
    assert stakes == original_stakes[:-1]


def test_staker_manages_restaking(testerchain, test_registry, staker):
    # Enable Restaking
    receipt = staker.enable_restaking()
    assert receipt['status'] == 1

    receipt = staker.disable_restaking()
    assert receipt['status'] == 1


def test_staker_collects_staking_reward(testerchain,
                                        test_registry,
                                        staker,
                                        blockchain_ursulas,
                                        agency,
                                        token_economics,
                                        ursula_decentralized_test_config):
    token_agent = ContractAgency.get_agent(NucypherTokenAgent, registry=test_registry)

    tpower = TransactingPower(account=testerchain.etherbase_account,
                              signer=Web3Signer(testerchain.client))

    # Give more tokens to staker
    token_airdrop(token_agent=token_agent,
                  transacting_power=tpower,
                  addresses=[staker.checksum_address],
                  amount=DEVELOPMENT_TOKEN_AIRDROP_AMOUNT)

    staker.initialize_stake(amount=NU(token_economics.minimum_allowed_locked, 'NuNit'),  # Lock the minimum amount of tokens
                            lock_periods=int(token_economics.minimum_locked_periods))    # ... for the fewest number of periods

    # Get an unused address for a new worker
    worker_address = testerchain.unassigned_accounts[-1]
    staker.bond_worker(worker_address=worker_address)

    # Create this worker and bond it with the staker
    ursula = make_decentralized_ursulas(ursula_config=ursula_decentralized_test_config,
                                        stakers_addresses=[staker.checksum_address],
                                        workers_addresses=[worker_address],
                                        registry=test_registry,
                                        commit_now=False).pop()

    # ...mint few tokens...
    for _ in range(2):
        ursula.commit_to_next_period()
        testerchain.time_travel(periods=1)

    # Check mintable periods
    assert staker.mintable_periods() == 1
    ursula.commit_to_next_period()

    # ...wait more...
    assert staker.mintable_periods() == 0
    testerchain.time_travel(periods=2)
    assert staker.mintable_periods() == 2

    # Capture the current token balance of the staker
    initial_balance = staker.token_balance
    assert token_agent.get_balance(staker.checksum_address) == initial_balance

    # Profit!
    staked = staker.non_withdrawable_stake()
    owned = staker.owned_tokens()
    staker.collect_staking_reward()
    assert staker.owned_tokens() == staked

    final_balance = staker.token_balance
    assert final_balance == initial_balance + owned - staked


def test_staker_manages_winding_down(testerchain,
                                     test_registry,
                                     staker,
                                     token_economics,
                                     ursula_decentralized_test_config):
    # Get worker
    ursula = make_decentralized_ursulas(ursula_config=ursula_decentralized_test_config,
                                        stakers_addresses=[staker.checksum_address],
                                        workers_addresses=[staker.worker_address],
                                        registry=test_registry).pop()

    # Enable winding down
    testerchain.time_travel(periods=1)
    base_duration = token_economics.minimum_locked_periods + 4
    receipt = staker.enable_winding_down()
    assert receipt['status'] == 1
    assert staker.locked_tokens(base_duration) != 0
    assert staker.locked_tokens(base_duration + 1) == 0
    ursula.commit_to_next_period()
    assert staker.locked_tokens(base_duration) != 0
    assert staker.locked_tokens(base_duration + 1) == 0

    # Disable winding down
    testerchain.time_travel(periods=1)
    receipt = staker.disable_winding_down()
    assert receipt['status'] == 1
    assert staker.locked_tokens(base_duration - 1) != 0
    assert staker.locked_tokens(base_duration) == 0
    ursula.commit_to_next_period()
    assert staker.locked_tokens(base_duration - 1) != 0
    assert staker.locked_tokens(base_duration) == 0


def test_staker_manages_snapshots(testerchain,
                                  test_registry,
                                  staker,
                                  token_economics,
                                  ursula_decentralized_test_config):
    # Disable taking snapshots
    testerchain.time_travel(periods=1)
    assert staker.is_taking_snapshots
    receipt = staker.disable_snapshots()
    assert receipt['status'] == 1
    assert not staker.is_taking_snapshots

    # Enable taking snapshots
    receipt = staker.enable_snapshots()
    assert receipt['status'] == 1
    assert staker.is_taking_snapshots


def test_set_min_fee_rate(testerchain, test_registry, staker):
    # Check before set
    _minimum, default, maximum = FEE_RATE_RANGE
    assert staker.min_fee_rate == default

    # New value must be within range
    with pytest.raises((TransactionFailed, ValueError)):
        staker.set_min_fee_rate(maximum + 1)
    receipt = staker.set_min_fee_rate(maximum - 1)
    assert receipt['status'] == 1
    assert staker.min_fee_rate == maximum - 1
