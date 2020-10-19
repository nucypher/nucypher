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

import os
import pytest
from eth_tester.exceptions import TransactionFailed
from eth_utils.address import is_address, to_checksum_address

from nucypher.blockchain.eth.agents import ContractAgency, StakingEscrowAgent
from nucypher.blockchain.eth.constants import NULL_ADDRESS
from nucypher.blockchain.eth.registry import BaseContractRegistry
from nucypher.types import StakerInfo
from tests.constants import INSECURE_DEVELOPMENT_PASSWORD


def test_unknown_contract(testerchain, test_registry):
    with pytest.raises(BaseContractRegistry.UnknownContract) as exception:
        _staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=test_registry)

    assert exception.value.args[0] == StakingEscrowAgent.contract_name


def test_deposit_tokens(testerchain, agency, token_economics, mock_transacting_power_activation):
    token_agent, staking_agent, _policy_agent = agency

    locked_tokens = token_economics.minimum_allowed_locked * 5

    staker_account = testerchain.unassigned_accounts[0]

    mock_transacting_power_activation(account=testerchain.etherbase_account, password=INSECURE_DEVELOPMENT_PASSWORD)

    balance = token_agent.get_balance(address=staker_account)
    assert balance == 0

    # The staker receives an initial amount of tokens
    _txhash = token_agent.transfer(amount=token_economics.minimum_allowed_locked * 10,
                                   target_address=staker_account,
                                   sender_address=testerchain.etherbase_account)

    mock_transacting_power_activation(account=staker_account, password=INSECURE_DEVELOPMENT_PASSWORD)

    #
    # Deposit: The staker deposits tokens in the StakingEscrow contract.
    # Previously, she needs to approve this transfer on the token contract.
    #

    _receipt = token_agent.approve_transfer(amount=token_economics.minimum_allowed_locked * 10,  # Approve
                                            spender_address=staking_agent.contract_address,
                                            sender_address=staker_account)

    receipt = staking_agent.deposit_tokens(amount=locked_tokens,
                                           lock_periods=token_economics.minimum_locked_periods,
                                           sender_address=staker_account,
                                           staker_address=staker_account)

    # Check the receipt for the contract address success code
    assert receipt['status'] == 1, "Transaction Rejected"
    assert receipt['logs'][2]['address'] == staking_agent.contract_address

    testerchain.time_travel(periods=1)
    balance = token_agent.get_balance(address=staker_account)
    assert balance == locked_tokens
    assert staking_agent.get_locked_tokens(staker_address=staker_account) == locked_tokens


def test_locked_tokens(testerchain, agency, token_economics):
    _token_agent, staking_agent, _policy_agent = agency
    staker_account = testerchain.unassigned_accounts[0]
    locked_amount = staking_agent.get_locked_tokens(staker_address=staker_account)
    assert token_economics.maximum_allowed_locked >= locked_amount >= token_economics.minimum_allowed_locked


def test_get_all_stakes(testerchain, agency, token_economics):
    _token_agent, staking_agent, _policy_agent = agency
    staker_account = testerchain.unassigned_accounts[0]

    all_stakes = list(staking_agent.get_all_stakes(staker_address=staker_account))
    assert len(all_stakes) == 1
    stake_info = all_stakes[0]
    assert len(stake_info) == 3
    start_period, end_period, value = stake_info
    assert end_period > start_period
    assert token_economics.maximum_allowed_locked > value > token_economics.minimum_allowed_locked


def test_stakers_and_workers_relationships(testerchain, agency):
    _token_agent, staking_agent, _policy_agent = agency

    staker_account, worker_account, *other = testerchain.unassigned_accounts

    # The staker hasn't bond a worker yet
    assert NULL_ADDRESS == staking_agent.get_worker_from_staker(staker_address=staker_account)

    _txhash = staking_agent.bond_worker(staker_address=staker_account,
                                        worker_address=worker_account)

    # We can check the staker-worker relation from both sides
    assert worker_account == staking_agent.get_worker_from_staker(staker_address=staker_account)
    assert staker_account == staking_agent.get_staker_from_worker(worker_address=worker_account)

    # No staker-worker relationship
    random_address = to_checksum_address(os.urandom(20))
    assert NULL_ADDRESS == staking_agent.get_worker_from_staker(staker_address=random_address)
    assert NULL_ADDRESS == staking_agent.get_staker_from_worker(worker_address=random_address)


def test_get_staker_population(agency, stakers):
    _token_agent, staking_agent, _policy_agent = agency

    # Apart from all the stakers in the fixture, we also added a new staker above
    assert staking_agent.get_staker_population() == len(stakers) + 1


def test_get_swarm(agency, blockchain_ursulas):
    _token_agent, staking_agent, _policy_agent = agency

    swarm = staking_agent.swarm()
    swarm_addresses = list(swarm)
    assert len(swarm_addresses) == len(blockchain_ursulas) + 1

    # Grab a staker address from the swarm
    staker_addr = swarm_addresses[0]
    assert isinstance(staker_addr, str)
    assert is_address(staker_addr)


@pytest.mark.usefixtures("blockchain_ursulas")
def test_sample_stakers(agency):
    _token_agent, staking_agent, _policy_agent = agency
    stakers_population = staking_agent.get_staker_population()

    with pytest.raises(StakingEscrowAgent.NotEnoughStakers):
        staking_agent.get_stakers_reservoir(duration=1).draw(stakers_population + 1)  # One more than we have deployed

    stakers = staking_agent.get_stakers_reservoir(duration=5).draw(3)
    assert len(stakers) == 3       # Three...
    assert len(set(stakers)) == 3  # ...unique addresses

    # Same but with pagination
    stakers = staking_agent.get_stakers_reservoir(duration=5, pagination_size=1).draw(3)
    assert len(stakers) == 3
    assert len(set(stakers)) == 3
    light = staking_agent.blockchain.is_light
    staking_agent.blockchain.is_light = not light
    stakers = staking_agent.get_stakers_reservoir(duration=5).draw(3)
    assert len(stakers) == 3
    assert len(set(stakers)) == 3
    staking_agent.blockchain.is_light = light


def test_get_current_period(agency, testerchain):
    _token_agent, staking_agent, _policy_agent = agency
    start_period = staking_agent.get_current_period()
    testerchain.time_travel(periods=1)
    end_period = staking_agent.get_current_period()
    assert end_period > start_period


def test_commit_to_next_period(agency, testerchain, mock_transacting_power_activation):
    _token_agent, staking_agent, _policy_agent = agency

    staker_account, worker_account, *other = testerchain.unassigned_accounts

    mock_transacting_power_activation(account=worker_account, password=INSECURE_DEVELOPMENT_PASSWORD)

    txhash = staking_agent.commit_to_next_period(worker_address=worker_account)
    receipt = testerchain.wait_for_receipt(txhash)
    assert receipt['status'] == 1, "Transaction Rejected"
    assert receipt['logs'][0]['address'] == staking_agent.contract_address


def test_get_staker_info(agency, testerchain):
    _token_agent, staking_agent, _policy_agent = agency

    staker_account, worker_account, *other = testerchain.unassigned_accounts

    info: StakerInfo = staking_agent.get_staker_info(staker_address=staker_account)
    assert info.value > 0
    assert info.worker == worker_account


def test_divide_stake(agency, testerchain, token_economics):
    token_agent, staking_agent, policy_agent = agency
    agent = staking_agent
    staker_account = testerchain.unassigned_accounts[0]

    locked_tokens = token_economics.minimum_allowed_locked * 2

    # Deposit
    _txhash = agent.deposit_tokens(amount=locked_tokens,
                                   lock_periods=token_economics.minimum_locked_periods,
                                   sender_address=staker_account,
                                   staker_address=staker_account)

    stakes = list(agent.get_all_stakes(staker_address=staker_account))
    stakes_length = len(stakes)
    origin_stake = stakes[-1]

    receipt = agent.divide_stake(staker_address=staker_account,
                                 stake_index=1,
                                 target_value=token_economics.minimum_allowed_locked,
                                 periods=1)

    assert receipt['status'] == 1, "Transaction Rejected"
    assert receipt['logs'][0]['address'] == agent.contract_address

    stakes = list(agent.get_all_stakes(staker_address=staker_account))
    assert len(stakes) == stakes_length + 1
    assert stakes[-2].locked_value == origin_stake.locked_value - token_economics.minimum_allowed_locked
    assert stakes[-2].last_period == origin_stake.last_period
    assert stakes[-1].locked_value == token_economics.minimum_allowed_locked
    assert stakes[-1].last_period == origin_stake.last_period + 1


def test_prolong_stake(agency, testerchain, test_registry):
    staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=test_registry)
    staker_account, worker_account, *other = testerchain.unassigned_accounts

    stakes = list(staking_agent.get_all_stakes(staker_address=staker_account))
    original_termination = stakes[0].last_period

    receipt = staking_agent.prolong_stake(staker_address=staker_account, stake_index=0, periods=1)
    assert receipt['status'] == 1

    # Ensure stake was extended by one period.
    stakes = list(staking_agent.get_all_stakes(staker_address=staker_account))
    new_termination = stakes[0].last_period
    assert new_termination == original_termination + 1


def test_deposit_and_increase(agency, testerchain, test_registry, token_economics):
    staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=test_registry)
    staker_account, worker_account, *other = testerchain.unassigned_accounts

    stakes = list(staking_agent.get_all_stakes(staker_address=staker_account))
    original_stake = stakes[0]
    locked_tokens = staking_agent.get_locked_tokens(staker_account, 1)

    amount = token_economics.minimum_allowed_locked // 2
    receipt = staking_agent.deposit_and_increase(staker_address=staker_account,
                                                 stake_index=0,
                                                 amount=amount)
    assert receipt['status'] == 1

    # Ensure stake was extended by one period.
    stakes = list(staking_agent.get_all_stakes(staker_address=staker_account))
    new_stake = stakes[0]
    assert new_stake.locked_value == original_stake.locked_value + amount
    assert staking_agent.get_locked_tokens(staker_account, 1) == locked_tokens + amount


def test_lock_restaking(agency, testerchain, test_registry):
    staker_account, worker_account, *other = testerchain.unassigned_accounts
    staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=test_registry)
    current_period = staking_agent.get_current_period()
    terminal_period = current_period + 2

    assert staking_agent.is_restaking(staker_account)
    assert not staking_agent.is_restaking_locked(staker_account)
    receipt = staking_agent.lock_restaking(staker_account, release_period=terminal_period)
    assert receipt['status'] == 1, "Transaction Rejected"
    assert staking_agent.is_restaking_locked(staker_account)

    testerchain.time_travel(periods=2)  # Wait for re-staking lock to be released.
    assert not staking_agent.is_restaking_locked(staker_account)


def test_disable_restaking(agency, testerchain, test_registry):
    staker_account, worker_account, *other = testerchain.unassigned_accounts
    staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=test_registry)

    assert staking_agent.is_restaking(staker_account)
    receipt = staking_agent.set_restaking(staker_account, value=False)
    assert receipt['status'] == 1, "Transaction Rejected"
    assert not staking_agent.is_restaking(staker_account)


def test_collect_staking_reward(agency, testerchain, mock_transacting_power_activation):
    token_agent, staking_agent, _policy_agent = agency

    staker_account, worker_account, *other = testerchain.unassigned_accounts

    # Commit to next period
    staking_agent.commit_to_next_period(worker_address=worker_account)
    testerchain.time_travel(periods=2)

    mock_transacting_power_activation(account=staker_account, password=INSECURE_DEVELOPMENT_PASSWORD)

    # Mint
    _receipt = staking_agent.mint(staker_address=staker_account)

    old_balance = token_agent.get_balance(address=staker_account)
    owned_tokens = staking_agent.owned_tokens(staker_address=staker_account)
    staked = staking_agent.non_withdrawable_stake(staker_address=staker_account)

    receipt = staking_agent.collect_staking_reward(staker_address=staker_account)
    assert receipt['status'] == 1, "Transaction Rejected"
    assert receipt['logs'][-1]['address'] == staking_agent.contract_address

    new_balance = token_agent.get_balance(address=staker_account)  # not the shoes
    assert new_balance == old_balance + owned_tokens - staked
    assert staking_agent.owned_tokens(staker_address=staker_account) == staked


def test_winding_down(agency, testerchain, test_registry, token_economics):
    staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=test_registry)  # type: StakingEscrowAgent
    staker_account, worker_account, *other = testerchain.unassigned_accounts
    duration = token_economics.minimum_locked_periods + 1

    def check_last_period():
        assert staking_agent.get_locked_tokens(staker_account, duration) != 0, "Sub-stake is already unlocked"
        assert staking_agent.get_locked_tokens(staker_account, duration + 1) == 0, "Sub-stake is still locked"

    assert not staking_agent.is_winding_down(staker_account)
    check_last_period()
    staking_agent.commit_to_next_period(worker_address=worker_account)
    check_last_period()

    # Examine the last periods of sub-stakes

    testerchain.time_travel(periods=1)
    check_last_period()
    receipt = staking_agent.set_winding_down(staker_account, value=True)
    assert receipt['status'] == 1
    assert staking_agent.is_winding_down(staker_account)
    check_last_period()
    staking_agent.commit_to_next_period(worker_address=worker_account)
    check_last_period()

    testerchain.time_travel(periods=1)
    duration -= 1
    check_last_period()
    receipt = staking_agent.set_winding_down(staker_account, value=False)
    assert receipt['status'] == 1
    assert not staking_agent.is_winding_down(staker_account)
    check_last_period()
    staking_agent.commit_to_next_period(worker_address=worker_account)
    check_last_period()


def test_lock_and_create(agency, testerchain, test_registry, token_economics):
    staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=test_registry)
    staker_account, worker_account, *other = testerchain.unassigned_accounts

    stakes = list(staking_agent.get_all_stakes(staker_address=staker_account))
    stakes_length = len(stakes)
    current_locked_tokens = staking_agent.get_locked_tokens(staker_account, 0)
    next_locked_tokens = staking_agent.get_locked_tokens(staker_account, 1)

    amount = token_economics.minimum_allowed_locked
    receipt = staking_agent.lock_and_create(staker_address=staker_account,
                                            lock_periods=token_economics.minimum_locked_periods,
                                            amount=amount)
    assert receipt['status'] == 1

    # Ensure stake was extended by one period.
    stakes = list(staking_agent.get_all_stakes(staker_address=staker_account))
    assert len(stakes) == stakes_length + 1
    new_stake = stakes[-1]
    current_period = staking_agent.get_current_period()
    assert new_stake.last_period == current_period + token_economics.minimum_locked_periods
    assert new_stake.first_period == current_period + 1
    assert new_stake.locked_value == amount
    assert staking_agent.get_locked_tokens(staker_account, 1) == next_locked_tokens + amount
    assert staking_agent.get_locked_tokens(staker_account, 0) == current_locked_tokens


def test_lock_and_increase(agency, testerchain, test_registry, token_economics):
    staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=test_registry)
    staker_account, worker_account, *other = testerchain.unassigned_accounts

    stakes = list(staking_agent.get_all_stakes(staker_address=staker_account))
    original_stake = stakes[0]
    current_locked_tokens = staking_agent.get_locked_tokens(staker_account, 0)
    next_locked_tokens = staking_agent.get_locked_tokens(staker_account, 1)

    amount = staking_agent.calculate_staking_reward(staker_address=staker_account)
    receipt = staking_agent.lock_and_increase(staker_address=staker_account,
                                              stake_index=0,
                                              amount=amount)
    assert receipt['status'] == 1

    # Ensure stake was extended by one period.
    stakes = list(staking_agent.get_all_stakes(staker_address=staker_account))
    new_stake = stakes[0]
    assert new_stake.locked_value == original_stake.locked_value + amount
    assert staking_agent.get_locked_tokens(staker_account, 1) == next_locked_tokens + amount
    assert staking_agent.get_locked_tokens(staker_account, 0) == current_locked_tokens


def test_merge(agency, testerchain, test_registry, token_economics):
    staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=test_registry)
    staker_account = testerchain.unassigned_accounts[0]

    stakes = list(staking_agent.get_all_stakes(staker_address=staker_account))
    original_stake_1 = stakes[0]
    original_stake_2 = stakes[2]
    assert original_stake_1.last_period == original_stake_2.last_period

    current_locked_tokens = staking_agent.get_locked_tokens(staker_account, 0)
    next_locked_tokens = staking_agent.get_locked_tokens(staker_account, 1)

    receipt = staking_agent.merge_stakes(staker_address=staker_account,
                                         stake_index_1=0,
                                         stake_index_2=2)
    assert receipt['status'] == 1

    # Ensure stake was extended by one period.
    stakes = list(staking_agent.get_all_stakes(staker_address=staker_account))
    new_stake = stakes[0]
    assert new_stake.locked_value == original_stake_1.locked_value + original_stake_2.locked_value
    assert staking_agent.get_locked_tokens(staker_account, 1) == next_locked_tokens
    assert staking_agent.get_locked_tokens(staker_account, 0) == current_locked_tokens


def test_remove_unused_stake(agency, testerchain, test_registry):
    staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=test_registry)
    staker_account = testerchain.unassigned_accounts[0]

    testerchain.time_travel(periods=1)
    staking_agent.mint(staker_address=staker_account)
    current_period = staking_agent.get_current_period()
    original_stakes = list(staking_agent.get_all_stakes(staker_address=staker_account))
    assert original_stakes[2].last_period == current_period - 1

    current_locked_tokens = staking_agent.get_locked_tokens(staker_account, 0)
    next_locked_tokens = staking_agent.get_locked_tokens(staker_account, 1)

    receipt = staking_agent.remove_unused_stake(staker_address=staker_account, stake_index=2)
    assert receipt['status'] == 1

    # Ensure stake was extended by one period.
    stakes = list(staking_agent.get_all_stakes(staker_address=staker_account))
    assert len(stakes) == len(original_stakes) - 1
    assert stakes[0] == original_stakes[0]
    assert stakes[1] == original_stakes[1]
    assert stakes[2] == original_stakes[4]
    assert stakes[3] == original_stakes[3]
    assert staking_agent.get_locked_tokens(staker_account, 1) == next_locked_tokens
    assert staking_agent.get_locked_tokens(staker_account, 0) == current_locked_tokens


def test_batch_deposit(testerchain,
                       agency,
                       token_economics,
                       mock_transacting_power_activation,
                       get_random_checksum_address):

    token_agent, staking_agent, _policy_agent = agency

    amount = token_economics.minimum_allowed_locked
    lock_periods = token_economics.minimum_locked_periods

    stakers = [get_random_checksum_address() for _ in range(4)]

    N = 5
    substakes = [(amount, lock_periods)] * N
    deposits = {staker: substakes for staker in stakers}

    batch_parameters = staking_agent.construct_batch_deposit_parameters(deposits=deposits)

    assert batch_parameters[0] == stakers
    assert batch_parameters[1] == [N] * len(stakers)
    assert batch_parameters[2] == [amount] * (N * len(stakers))
    assert batch_parameters[3] == [lock_periods] * (N * len(stakers))

    mock_transacting_power_activation(account=testerchain.etherbase_account, password=INSECURE_DEVELOPMENT_PASSWORD)

    tokens_in_batch = sum(batch_parameters[2])

    _receipt = token_agent.approve_transfer(amount=tokens_in_batch,
                                            spender_address=staking_agent.contract_address,
                                            sender_address=testerchain.etherbase_account)

    not_enough_gas = 800_000
    with pytest.raises((TransactionFailed, ValueError)):
        staking_agent.batch_deposit(*batch_parameters,
                                    sender_address=testerchain.etherbase_account,
                                    dry_run=True,
                                    gas_limit=not_enough_gas)

    staking_agent.batch_deposit(*batch_parameters,
                                sender_address=testerchain.etherbase_account,
                                dry_run=True)

    staking_agent.batch_deposit(*batch_parameters,
                                sender_address=testerchain.etherbase_account)

    for staker in stakers:
        assert staking_agent.owned_tokens(staker_address=staker) == amount * N
        staker_substakes = list(staking_agent.get_all_stakes(staker_address=staker))
        assert N == len(staker_substakes)
        for substake in staker_substakes:
            first_period, last_period, locked_value = substake
            assert last_period == first_period + lock_periods - 1
            assert locked_value == amount
