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

from nucypher.blockchain.eth.token import NU


VESTING_RELEASE_TIMESTAMP_SLOT = 9
VESTING_RELEASE_RATE_SLOT = 10
OPERATOR_SLOT = 11
ONE_HOUR = 60 * 60


def test_staking_from_worklock(testerchain, token, worklock, escrow):
    """
    Tests for staking method: depositFromWorkLock
    """

    creator, staker1, staker2, staker3 = testerchain.client.accounts[0:4]
    deposit_log = escrow.events.Deposited.createFilter(fromBlock='latest')

    # Give WorkLock and Staker some coins
    value = NU(15_000, 'NU').to_nunits()
    tx = token.functions.transfer(worklock.address, 10 * value).transact({'from': creator})
    testerchain.wait_for_receipt(tx)

    # Can't use method not from WorkLock
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.depositFromWorkLock(staker1, value, 0).transact({'from': staker1})
        testerchain.wait_for_receipt(tx)
    # Can't deposit 0 tokens
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.depositFromWorkLock(staker1, 0, 0).transact({'from': staker1})
        testerchain.wait_for_receipt(tx)
    assert token.functions.balanceOf(escrow.address).call() == 0

    # First deposit
    tx = worklock.functions.depositFromWorkLock(staker1, value, 0).transact()
    testerchain.wait_for_receipt(tx)
    assert token.functions.balanceOf(escrow.address).call() == value
    assert escrow.functions.getAllTokens(staker1).call() == value
    assert escrow.functions.getStakersLength().call() == 1
    assert escrow.functions.stakers(0).call() == staker1

    # Check that all events are emitted
    events = deposit_log.get_all_entries()
    assert len(events) == 1
    event_args = events[-1]['args']
    assert event_args['staker'] == staker1
    assert event_args['value'] == value

    # Deposit directly and then through WorkLock
    tx = escrow.functions.setStaker(staker2, value, 0).transact({'from': staker2})
    testerchain.wait_for_receipt(tx)
    tx = worklock.functions.depositFromWorkLock(staker2, value, 0).transact()
    testerchain.wait_for_receipt(tx)
    assert token.functions.balanceOf(escrow.address).call() == 2 * value
    assert escrow.functions.getAllTokens(staker2).call() == 2 * value
    assert escrow.functions.getStakersLength().call() == 2
    assert escrow.functions.stakers(1).call() == staker2

    # Check that all events are emitted
    events = deposit_log.get_all_entries()
    assert len(events) == 2
    event_args = events[-1]['args']
    assert event_args['staker'] == staker2
    assert event_args['value'] == value

    # Emulate case when staker withdraws everything and then deposits from WorkLock
    tx = escrow.functions.setStaker(staker3, 0, 1).transact({'from': staker3})
    testerchain.wait_for_receipt(tx)
    tx = worklock.functions.depositFromWorkLock(staker3, value, 0).transact()
    testerchain.wait_for_receipt(tx)
    assert token.functions.balanceOf(escrow.address).call() == 3 * value
    assert escrow.functions.getAllTokens(staker3).call() == value
    assert escrow.functions.getStakersLength().call() == 3
    assert escrow.functions.stakers(2).call() == staker3

    # Check that all events are emitted
    events = deposit_log.get_all_entries()
    assert len(events) == 3
    event_args = events[-1]['args']
    assert event_args['staker'] == staker3
    assert event_args['value'] == value


def test_slashing(testerchain, token, worklock, threshold_staking, escrow):
    creator = testerchain.client.accounts[0]
    staker = testerchain.client.accounts[1]
    investigator = testerchain.client.accounts[2]

    slashing_log = escrow.events.Slashed.createFilter(fromBlock='latest')

    # Staker deposits some tokens
    stake = NU(15_000, 'NU').to_nunits()
    tx = token.functions.transfer(worklock.address, 10 * stake).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    tx = worklock.functions.depositFromWorkLock(staker, stake, 0).transact()
    testerchain.wait_for_receipt(tx)

    assert stake == escrow.functions.getAllTokens(staker).call()

    reward = stake // 100
    # Can't slash directly using the escrow contract
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.slashStaker(staker, stake, investigator, reward).transact()
        testerchain.wait_for_receipt(tx)
    # Penalty must be greater than zero
    with pytest.raises((TransactionFailed, ValueError)):
        tx = threshold_staking.functions.slashStaker(staker, 0, investigator, 0).transact()
        testerchain.wait_for_receipt(tx)

    # Slash the whole stake
    tx = threshold_staking.functions.slashStaker(staker, 2 * stake, investigator, reward).transact()
    testerchain.wait_for_receipt(tx)
    # Staker has no more stake
    assert escrow.functions.getAllTokens(staker).call() == 0
    assert token.functions.balanceOf(investigator).call() == reward

    events = slashing_log.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert event_args['staker'] == staker
    assert event_args['penalty'] == stake
    assert event_args['investigator'] == investigator
    assert event_args['reward'] == reward

    # Slash small part
    tx = worklock.functions.depositFromWorkLock(staker, stake, 0).transact()
    testerchain.wait_for_receipt(tx)
    amount_to_slash = stake // 10
    tx = threshold_staking.functions.slashStaker(staker, amount_to_slash, investigator, 2 * amount_to_slash).transact()
    testerchain.wait_for_receipt(tx)
    # Staker has no more stake
    assert escrow.functions.getAllTokens(staker).call() == stake - amount_to_slash
    assert token.functions.balanceOf(investigator).call() == reward + amount_to_slash

    events = slashing_log.get_all_entries()
    assert 2 == len(events)
    event_args = events[1]['args']
    assert event_args['staker'] == staker
    assert event_args['penalty'] == amount_to_slash
    assert event_args['investigator'] == investigator
    assert event_args['reward'] == amount_to_slash

    # Slash without reward
    tx = threshold_staking.functions.slashStaker(staker, amount_to_slash, investigator, 0).transact()
    testerchain.wait_for_receipt(tx)
    # Staker has no more stake
    assert escrow.functions.getAllTokens(staker).call() == stake - 2 * amount_to_slash
    assert token.functions.balanceOf(investigator).call() == reward + amount_to_slash

    events = slashing_log.get_all_entries()
    assert 3 == len(events)
    event_args = events[2]['args']
    assert event_args['staker'] == staker
    assert event_args['penalty'] == amount_to_slash
    assert event_args['investigator'] == investigator
    assert event_args['reward'] == 0


def test_request_merge(testerchain, threshold_staking, escrow):
    staker1, staker2, operator1, operator2 = testerchain.client.accounts[0:4]
    merge_requests_log = escrow.events.MergeRequested.createFilter(fromBlock='latest')

    # Can't request merge directly
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.requestMerge(staker1, operator1).transact()
        testerchain.wait_for_receipt(tx)

    # Requesting merge for non-existent staker will return zero
    tx = threshold_staking.functions.requestMerge(staker1, operator1).transact()
    testerchain.wait_for_receipt(tx)
    assert escrow.functions.getAllTokens(staker1).call() == 0
    assert escrow.functions.stakerInfo(staker1).call()[OPERATOR_SLOT] == operator1
    assert threshold_staking.functions.operators(operator1).call()[0] == 0

    events = merge_requests_log.get_all_entries()
    assert len(events) == 1
    event_args = events[-1]['args']
    assert event_args['staker'] == staker1
    assert event_args['operator'] == operator1

    # Request can be made several times
    tx = threshold_staking.functions.requestMerge(staker1, operator1).transact()
    testerchain.wait_for_receipt(tx)
    assert escrow.functions.getAllTokens(staker1).call() == 0
    assert escrow.functions.stakerInfo(staker1).call()[OPERATOR_SLOT] == operator1
    assert threshold_staking.functions.operators(operator1).call()[0] == 0
    assert len(merge_requests_log.get_all_entries()) == 1
    _snapshots_enabled, merged = escrow.functions.getFlags(staker1).call()
    assert not merged

    # Request can be done only with the same operator
    with pytest.raises((TransactionFailed, ValueError)):
        tx = threshold_staking.functions.requestMerge(staker1, operator2).transact()
        testerchain.wait_for_receipt(tx)

    # Requesting merge for existent staker will return stake
    value = 1000
    tx = escrow.functions.setStaker(staker2, value, 0).transact()
    testerchain.wait_for_receipt(tx)
    tx = threshold_staking.functions.requestMerge(staker2, operator2).transact()
    testerchain.wait_for_receipt(tx)
    assert escrow.functions.getAllTokens(staker2).call() == value
    assert escrow.functions.stakerInfo(staker2).call()[OPERATOR_SLOT] == operator2
    assert threshold_staking.functions.operators(operator2).call()[0] == value

    events = merge_requests_log.get_all_entries()
    assert len(events) == 2
    event_args = events[-1]['args']
    assert event_args['staker'] == staker2
    assert event_args['operator'] == operator2

    # Request can be made several times
    tx = threshold_staking.functions.requestMerge(staker2, operator2).transact()
    testerchain.wait_for_receipt(tx)
    assert escrow.functions.getAllTokens(staker2).call() == value
    assert escrow.functions.stakerInfo(staker2).call()[OPERATOR_SLOT] == operator2
    assert threshold_staking.functions.operators(operator2).call()[0] == value

    tx = escrow.functions.setStaker(staker2, 2 * value, 0).transact()
    testerchain.wait_for_receipt(tx)
    tx = threshold_staking.functions.requestMerge(staker2, operator2).transact()
    testerchain.wait_for_receipt(tx)
    assert escrow.functions.getAllTokens(staker2).call() == 2 * value
    assert escrow.functions.stakerInfo(staker2).call()[OPERATOR_SLOT] == operator2
    assert threshold_staking.functions.operators(operator2).call()[0] == 2 * value

    assert len(merge_requests_log.get_all_entries()) == 2
    _snapshots_enabled, merged = escrow.functions.getFlags(staker2).call()
    assert not merged

    # Request can be done only with the same operator
    with pytest.raises((TransactionFailed, ValueError)):
        tx = threshold_staking.functions.requestMerge(staker2, operator1).transact()
        testerchain.wait_for_receipt(tx)


def test_confirm_merge(testerchain, threshold_staking, escrow):
    creator, staker, operator = testerchain.client.accounts[0:3]
    merge_confirmations_log = escrow.events.MergeConfirmed.createFilter(fromBlock='latest')
    staking_error = NU(10**15, "NuNit").to_nunits()

    # Can't confirm merge without request
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.confirmMerge(staker).transact()
        testerchain.wait_for_receipt(tx)

    # Prepare staker and make a request
    value = NU(1000, "NU").to_nunits()
    tx = escrow.functions.setStaker(staker, value, 0).transact()
    testerchain.wait_for_receipt(tx)
    tx = threshold_staking.functions.requestMerge(staker, operator).transact()
    testerchain.wait_for_receipt(tx)

    # Emulate unstake
    tx = threshold_staking.functions.setStakedNu(operator, value - staking_error - 1).transact()
    testerchain.wait_for_receipt(tx)

    # Must be staked everything to allow confirm
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.confirmMerge(staker).transact()
        testerchain.wait_for_receipt(tx)

    # And everything must be authorized
    tx = threshold_staking.functions.requestMerge(staker, operator).transact()
    testerchain.wait_for_receipt(tx)
    tx = threshold_staking.functions.setStakedNu(operator, value - staking_error).transact()
    testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.confirmMerge(staker).transact()
        testerchain.wait_for_receipt(tx)

    tx = threshold_staking.functions.setMinStaked(operator, value - staking_error).transact()
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.confirmMerge(staker).transact()
    testerchain.wait_for_receipt(tx)
    _snapshots_enabled, merged = escrow.functions.getFlags(staker).call()
    assert merged

    events = merge_confirmations_log.get_all_entries()
    assert len(events) == 1
    event_args = events[-1]['args']
    assert event_args['staker'] == staker

    # Confirm can be made only once
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.confirmMerge(staker).transact()
        testerchain.wait_for_receipt(tx)


def test_withdraw(testerchain, token, worklock, threshold_staking, escrow):
    creator, staker, operator = testerchain.client.accounts[0:3]
    withdrawal_log = escrow.events.Withdrawn.createFilter(fromBlock='latest')

    # Deposit some tokens
    value = NU(15_000, 'NU').to_nunits()
    tx = token.functions.transfer(worklock.address, 10 * value).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    tx = worklock.functions.depositFromWorkLock(staker, value, 0).transact()
    testerchain.wait_for_receipt(tx)

    # Can't withdraw without confirmed merge
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.withdraw(1).transact({'from': staker})
        testerchain.wait_for_receipt(tx)

    tx = threshold_staking.functions.requestMerge(staker, operator).transact()
    testerchain.wait_for_receipt(tx)
    tx = threshold_staking.functions.setMinStaked(operator, value).transact()
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.confirmMerge(staker).transact()
    testerchain.wait_for_receipt(tx)
    tx = threshold_staking.functions.setMinStaked(operator, 0).transact()
    testerchain.wait_for_receipt(tx)

    # Still can't withdraw because everything is staked
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.withdraw(1).transact({'from': staker})
        testerchain.wait_for_receipt(tx)

    # Set vesting for the staker
    tx = threshold_staking.functions.setStakedNu(operator, value // 2).transact()
    testerchain.wait_for_receipt(tx)
    now = testerchain.w3.eth.getBlock('latest').timestamp
    release_timestamp = now + ONE_HOUR
    rate = 2 * value // ONE_HOUR
    tx = escrow.functions.setupVesting([staker], [release_timestamp], [rate]).transact({'from': creator})
    testerchain.wait_for_receipt(tx)

    # Vesting parameters prevent from withdrawing
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.withdraw(1).transact({'from': staker})
        testerchain.wait_for_receipt(tx)

    # Wait some time
    testerchain.time_travel(seconds=40 * 60)
    released = value - escrow.functions.getVestedTokens(staker).call()

    # Can't withdraw 0 tokens
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.withdraw(0).transact({'from': staker})
        testerchain.wait_for_receipt(tx)

    # Can't withdraw more than released
    to_withdraw = released + rate  # +rate because in new tx timestamp will be one second more
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.withdraw(to_withdraw + 1).transact({'from': staker})
        testerchain.wait_for_receipt(tx)

    # Only staker can withdraw stake
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.withdraw(1).transact({'from': operator})
        testerchain.wait_for_receipt(tx)

    tx = escrow.functions.withdraw(to_withdraw).transact({'from': staker})
    testerchain.wait_for_receipt(tx)
    assert escrow.functions.getAllTokens(staker).call() == value - to_withdraw
    assert token.functions.balanceOf(staker).call() == to_withdraw
    assert token.functions.balanceOf(escrow.address).call() == value - to_withdraw

    events = withdrawal_log.get_all_entries()
    assert len(events) == 1
    event_args = events[-1]['args']
    assert event_args['staker'] == staker
    assert event_args['value'] == to_withdraw

    # Can't withdraw more than unstaked
    testerchain.time_travel(seconds=20 * 60)
    unstaked = value // 2 - to_withdraw
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.withdraw(unstaked + 1).transact({'from': staker})
        testerchain.wait_for_receipt(tx)

    tx = escrow.functions.withdraw(unstaked).transact({'from': staker})
    testerchain.wait_for_receipt(tx)
    assert escrow.functions.getAllTokens(staker).call() == value // 2
    assert token.functions.balanceOf(staker).call() == value // 2
    assert token.functions.balanceOf(escrow.address).call() == value // 2

    events = withdrawal_log.get_all_entries()
    assert len(events) == 2
    event_args = events[-1]['args']
    assert event_args['staker'] == staker
    assert event_args['value'] == unstaked

    # Now unstake and withdraw everything
    tx = threshold_staking.functions.setStakedNu(operator, 0).transact()
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.withdraw(value // 2).transact({'from': staker})
    testerchain.wait_for_receipt(tx)
    assert escrow.functions.getAllTokens(staker).call() == 0
    assert token.functions.balanceOf(staker).call() == value
    assert token.functions.balanceOf(escrow.address).call() == 0

    events = withdrawal_log.get_all_entries()
    assert len(events) == 3
    event_args = events[-1]['args']
    assert event_args['staker'] == staker
    assert event_args['value'] == value // 2


def test_vesting(testerchain, token, worklock, escrow):
    creator, staker1, staker2, staker3 = testerchain.client.accounts[0:4]
    vesting_log = escrow.events.VestingSet.createFilter(fromBlock='latest')

    value = NU(15_000, 'NU').to_nunits()
    tx = token.functions.transfer(worklock.address, 10 * value).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    tx = worklock.functions.depositFromWorkLock(staker1, value, 0).transact()
    testerchain.wait_for_receipt(tx)

    now = testerchain.w3.eth.getBlock('latest').timestamp
    release_timestamp = now + ONE_HOUR
    rate = 2 * value // ONE_HOUR

    # Only owner can set vesting parameters
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.setupVesting([staker1], [release_timestamp], [rate]).transact({'from': staker1})
        testerchain.wait_for_receipt(tx)

    # All input arrays must have same number of values
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.setupVesting(
            [staker1, staker2],
            [release_timestamp, release_timestamp],
            [rate]
        ).transact({'from': creator})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.setupVesting(
            [staker1, staker2],
            [release_timestamp],
            [rate, rate]
        ).transact({'from': creator})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.setupVesting(
            [staker1],
            [release_timestamp, release_timestamp],
            [rate, rate]
        ).transact({'from': creator})
        testerchain.wait_for_receipt(tx)

    # At least some amount of tokens must be locked after setting parameters
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.setupVesting([staker1], [release_timestamp], [0]).transact({'from': creator})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.setupVesting([staker1], [now], [rate]).transact({'from': creator})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.setupVesting(
            [staker1, staker2],
            [release_timestamp, release_timestamp],
            [rate, rate]
        ).transact({'from': creator})
        testerchain.wait_for_receipt(tx)

    tx = escrow.functions.setupVesting([staker1], [release_timestamp], [rate]).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert escrow.functions.getVestedTokens(staker1).call() == value
    assert escrow.functions.stakerInfo(staker1).call()[VESTING_RELEASE_TIMESTAMP_SLOT] == release_timestamp
    assert escrow.functions.stakerInfo(staker1).call()[VESTING_RELEASE_RATE_SLOT] == rate

    events = vesting_log.get_all_entries()
    assert len(events) == 1
    event_args = events[-1]['args']
    assert event_args['staker'] == staker1
    assert event_args['releaseTimestamp'] == release_timestamp
    assert event_args['releaseRate'] == rate

    testerchain.time_travel(seconds=40 * 60)
    now = testerchain.w3.eth.getBlock('latest').timestamp
    vested = (release_timestamp - now) * rate
    assert escrow.functions.getVestedTokens(staker1).call() == vested

    testerchain.time_travel(seconds=20 * 60)
    assert escrow.functions.getVestedTokens(staker1).call() == 0

    # Can't set vesting again even after unlocking
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.setupVesting([staker1], [release_timestamp], [rate]).transact({'from': creator})
        testerchain.wait_for_receipt(tx)

    # Try again with two other stakers
    value = NU(ONE_HOUR, 'NU').to_nunits()  # Exclude rounding error
    tx = worklock.functions.depositFromWorkLock(staker2, value, 0).transact()
    testerchain.wait_for_receipt(tx)
    tx = worklock.functions.depositFromWorkLock(staker3, value, 0).transact()
    testerchain.wait_for_receipt(tx)

    now = testerchain.w3.eth.getBlock('latest').timestamp + 1  # +1 sec because tx will be executed in new block
    release_timestamp_2 = now + ONE_HOUR
    release_timestamp_3 = now + 2 * ONE_HOUR
    rate_2 = value // ONE_HOUR // 2
    rate_3 = value // ONE_HOUR // 4
    tx = escrow.functions.setupVesting(
        [staker2, staker3],
        [release_timestamp_2, release_timestamp_3],
        [rate_2, rate_3]
    ).transact({'from': creator})
    testerchain.wait_for_receipt(tx)

    assert escrow.functions.getVestedTokens(staker2).call() == value // 2
    assert escrow.functions.getVestedTokens(staker3).call() == value // 2
    assert escrow.functions.stakerInfo(staker2).call()[VESTING_RELEASE_TIMESTAMP_SLOT] == release_timestamp_2
    assert escrow.functions.stakerInfo(staker2).call()[VESTING_RELEASE_RATE_SLOT] == rate_2
    assert escrow.functions.stakerInfo(staker3).call()[VESTING_RELEASE_TIMESTAMP_SLOT] == release_timestamp_3
    assert escrow.functions.stakerInfo(staker3).call()[VESTING_RELEASE_RATE_SLOT] == rate_3

    events = vesting_log.get_all_entries()
    assert len(events) == 3
    event_args = events[-2]['args']
    assert event_args['staker'] == staker2
    assert event_args['releaseTimestamp'] == release_timestamp_2
    assert event_args['releaseRate'] == rate_2
    event_args = events[-1]['args']
    assert event_args['staker'] == staker3
    assert event_args['releaseTimestamp'] == release_timestamp_3
    assert event_args['releaseRate'] == rate_3

    testerchain.time_travel(seconds=ONE_HOUR)
    assert escrow.functions.getVestedTokens(staker2).call() == 0
    assert escrow.functions.getVestedTokens(staker3).call() == value // 4
