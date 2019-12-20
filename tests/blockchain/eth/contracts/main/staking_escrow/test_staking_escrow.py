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
from eth_utils import to_checksum_address

MAX_SUB_STAKES = 30
MAX_UINT16 = 65535


@pytest.mark.slow
def test_staking(testerchain, token, escrow_contract):
    """
    Tests for staking methods: deposit, lock and stake division
    """

    escrow = escrow_contract(1500)
    creator = testerchain.client.accounts[0]
    ursula1 = testerchain.client.accounts[1]
    ursula2 = testerchain.client.accounts[2]
    deposit_log = escrow.events.Deposited.createFilter(fromBlock='latest')
    lock_log = escrow.events.Locked.createFilter(fromBlock='latest')
    activity_log = escrow.events.ActivityConfirmed.createFilter(fromBlock='latest')
    divides_log = escrow.events.Divided.createFilter(fromBlock='latest')
    withdraw_log = escrow.events.Withdrawn.createFilter(fromBlock='latest')
    wind_down_log = escrow.events.WindDownSet.createFilter(fromBlock='latest')

    # Give Ursula and Ursula(2) some coins
    tx = token.functions.transfer(ursula1, 10000).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    tx = token.functions.transfer(ursula2, 10000).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert 10000 == token.functions.balanceOf(ursula1).call()
    assert 10000 == token.functions.balanceOf(ursula2).call()

    # Ursula and Ursula(2) give Escrow rights to transfer
    tx = token.functions.approve(escrow.address, 1000).transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    assert 1000 == token.functions.allowance(ursula1, escrow.address).call()
    tx = token.functions.approve(escrow.address, 500).transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    assert 500 == token.functions.allowance(ursula2, escrow.address).call()

    # Ursula's withdrawal attempt won't succeed because nothing to withdraw
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.withdraw(100).transact({'from': ursula1})
        testerchain.wait_for_receipt(tx)

    # And can't lock because nothing to lock
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.lock(500, 2).transact({'from': ursula1})
        testerchain.wait_for_receipt(tx)

    # Check that nothing is locked
    assert 0 == escrow.functions.getLockedTokens(ursula1, 0).call()
    assert 0 == escrow.functions.getLockedTokens(ursula2, 0).call()
    assert 0 == escrow.functions.getLockedTokens(testerchain.client.accounts[3], 0).call()

    # Ursula can't deposit tokens before Escrow initialization
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.deposit(500, 2).transact({'from': ursula1})
        testerchain.wait_for_receipt(tx)

    # Initialize Escrow contract
    tx = escrow.functions.initialize(0).transact({'from': creator})
    testerchain.wait_for_receipt(tx)

    # Ursula can't deposit and lock too low value (less than _minAllowableLockedTokens coefficient)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.deposit(1, 10).transact({'from': ursula1})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = token.functions.approveAndCall(escrow.address, 1, testerchain.w3.toBytes(10))\
            .transact({'from': ursula1})
        testerchain.wait_for_receipt(tx)
    # And can't deposit and lock too high value (more than _maxAllowableLockedTokens coefficient)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.deposit(1501, 10).transact({'from': ursula1})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = token.functions.approveAndCall(escrow.address, 1501, testerchain.w3.toBytes(10))\
            .transact({'from': ursula1})
        testerchain.wait_for_receipt(tx)
    # And can't deposit for too short a period (less than _minLockedPeriods coefficient)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.deposit(1000, 1).transact({'from': ursula1})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = token.functions.approveAndCall(escrow.address, 1000, testerchain.w3.toBytes(1))\
            .transact({'from': ursula1})
        testerchain.wait_for_receipt(tx)

    # Ursula transfers some tokens to the escrow and lock them
    current_period = escrow.functions.getCurrentPeriod().call()
    tx = escrow.functions.deposit(1000, 2).transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.setWorker(ursula1).transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.setWindDown(True).transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    assert 1000 == token.functions.balanceOf(escrow.address).call()
    assert 9000 == token.functions.balanceOf(ursula1).call()
    assert 0 == escrow.functions.getLockedTokens(ursula1, 0).call()
    assert 1000 == escrow.functions.getLockedTokens(ursula1, 1).call()
    assert 1000 == escrow.functions.getLockedTokens(ursula1, 2).call()
    assert 0 == escrow.functions.getLockedTokens(ursula1, 3).call()

    # Check that all events are emitted
    events = deposit_log.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert ursula1 == event_args['staker']
    assert 1000 == event_args['value']
    assert 2 == event_args['periods']
    events = lock_log.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert ursula1 == event_args['staker']
    assert 1000 == event_args['value']
    assert current_period + 1 == event_args['firstPeriod']
    assert 2 == event_args['periods']
    events = wind_down_log.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert ursula1 == event_args['staker']
    assert event_args['windDown']

    # Ursula(2) stakes tokens also
    tx = escrow.functions.deposit(500, 2).transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.setWorker(ursula2).transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.setWindDown(True).transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    assert 1500 == token.functions.balanceOf(escrow.address).call()
    assert 9500 == token.functions.balanceOf(ursula2).call()
    assert 0 == escrow.functions.getLockedTokens(ursula2, 0).call()
    assert 500 == escrow.functions.getLockedTokens(ursula2, 1).call()

    events = deposit_log.get_all_entries()
    assert 2 == len(events)
    event_args = events[1]['args']
    assert ursula2 == event_args['staker']
    assert 500 == event_args['value']
    assert 2 == event_args['periods']
    events = lock_log.get_all_entries()
    assert 2 == len(events)
    event_args = events[1]['args']
    assert ursula2 == event_args['staker']
    assert 500 == event_args['value']
    assert current_period + 1 == event_args['firstPeriod']
    assert 2 == event_args['periods']
    events = wind_down_log.get_all_entries()
    assert 2 == len(events)
    event_args = events[1]['args']
    assert ursula2 == event_args['staker']
    assert event_args['windDown']

    # Ursula and Ursula(2) confirm activity
    tx = escrow.functions.confirmActivity().transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.confirmActivity().transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    assert current_period + 1 == escrow.functions.getLastActivePeriod(ursula1).call()
    assert current_period + 1 == escrow.functions.getLastActivePeriod(ursula2).call()

    # No active stakers before next period
    all_locked, stakers = escrow.functions.getActiveStakers(1, 0, 0).call()
    assert 0 == all_locked
    assert 0 == len(stakers)

    events = activity_log.get_all_entries()
    assert 2 == len(events)
    event_args = events[0]['args']
    assert ursula1 == event_args['staker']
    assert current_period + 1 == event_args['period']
    assert 1000 == event_args['value']
    events = activity_log.get_all_entries()
    event_args = events[1]['args']
    assert ursula2 == event_args['staker']
    assert current_period + 1 == event_args['period']
    assert 500 == event_args['value']

    # Checks locked tokens in the next period
    testerchain.time_travel(hours=1)
    current_period = escrow.functions.getCurrentPeriod().call()
    assert 1000 == escrow.functions.getLockedTokens(ursula1, 0).call()
    assert 500 == escrow.functions.getLockedTokens(ursula2, 0).call()

    # Both stakers are active and have locked tokens in next period
    all_locked, stakers = escrow.functions.getActiveStakers(1, 0, 0).call()
    assert 1500 == all_locked
    assert 2 == len(stakers)
    assert ursula1 == to_checksum_address(stakers[0][0])
    assert 1000 == stakers[0][1]
    assert ursula2 == to_checksum_address(stakers[1][0])
    assert 500 == stakers[1][1]

    # Test parameters of getActiveStakers method
    same_all_locked, same_stakers = escrow.functions.getActiveStakers(1, 0, 2).call()
    assert all_locked == same_all_locked
    assert stakers == same_stakers
    same_all_locked, same_stakers = escrow.functions.getActiveStakers(1, 0, 10).call()
    assert all_locked == same_all_locked
    assert stakers == same_stakers
    all_locked_1, stakers_1 = escrow.functions.getActiveStakers(1, 0, 1).call()
    all_locked_2, stakers_2 = escrow.functions.getActiveStakers(1, 1, 1).call()
    assert all_locked == all_locked_1 + all_locked_2
    assert stakers == stakers_1 + stakers_2
    same_all_locked, same_stakers = escrow.functions.getActiveStakers(1, 1, 0).call()
    assert all_locked_2 == same_all_locked
    assert stakers_2 == same_stakers
    with pytest.raises((TransactionFailed, ValueError)):
        escrow.functions.getActiveStakers(1, 2, 1).call()

    # But in two periods their sub stakes will be unlocked
    all_locked, stakers = escrow.functions.getActiveStakers(2, 0, 0).call()
    assert 0 == all_locked
    assert 0 == len(stakers)

    # Ursula's withdrawal attempt won't succeed because everything is locked
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.withdraw(100).transact({'from': ursula1})
        testerchain.wait_for_receipt(tx)
    assert 1500 == token.functions.balanceOf(escrow.address).call()
    assert 9000 == token.functions.balanceOf(ursula1).call()

    # Ursula can deposit more tokens
    tx = escrow.functions.confirmActivity().transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    assert current_period + 1 == escrow.functions.getLastActivePeriod(ursula1).call()
    assert 1000 == escrow.functions.getLockedTokens(ursula1, 1).call()
    assert 0 == escrow.functions.getLockedTokens(ursula1, 2).call()

    events = activity_log.get_all_entries()
    assert 3 == len(events)
    event_args = events[2]['args']
    assert ursula1 == event_args['staker']
    assert current_period + 1 == event_args['period']
    assert 1000 == event_args['value']

    locked_next_period = escrow.functions.lockedPerPeriod(current_period + 1).call()
    tx = token.functions.approveAndCall(escrow.address, 500, testerchain.w3.toBytes(2))\
        .transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    assert 2000 == token.functions.balanceOf(escrow.address).call()
    assert 8500 == token.functions.balanceOf(ursula1).call()
    assert 1500 == escrow.functions.getLockedTokens(ursula1, 1).call()
    assert 500 == escrow.functions.getLockedTokens(ursula1, 2).call()
    assert 0 == escrow.functions.getLockedTokens(ursula1, 3).call()
    assert locked_next_period + 500 == escrow.functions.lockedPerPeriod(current_period + 1).call()

    events = activity_log.get_all_entries()
    assert 4 == len(events)
    event_args = events[3]['args']
    assert ursula1 == event_args['staker']
    assert current_period + 1 == event_args['period']
    assert 500 == event_args['value']

    # But can't deposit too high value (more than _maxAllowableLockedTokens coefficient)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.deposit(100, 2).transact({'from': ursula1})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = token.functions.approveAndCall(escrow.address, 100, testerchain.w3.toBytes(2))\
            .transact({'from': ursula1})
        testerchain.wait_for_receipt(tx)

    # Both stakers are active and only the first one locked tokens for two more periods
    all_locked, stakers = escrow.functions.getActiveStakers(2, 0, 0).call()
    assert 500 == all_locked
    assert 1 == len(stakers)
    assert ursula1 == to_checksum_address(stakers[0][0])
    assert 500 == stakers[0][1]
    _, stakers = escrow.functions.getActiveStakers(2, 0, 2).call()
    assert 1 == len(stakers)
    same_all_locked, same_stakers = escrow.functions.getActiveStakers(2, 0, 1).call()
    assert all_locked == same_all_locked
    assert stakers == same_stakers
    all_locked, stakers = escrow.functions.getActiveStakers(2, 1, 1).call()
    assert 0 == all_locked
    assert 0 == len(stakers)

    # Wait 1 period and checks locking
    testerchain.time_travel(hours=1)
    assert 1500 == escrow.functions.getLockedTokens(ursula1, 0).call()

    # Only one staker is active
    all_locked, stakers = escrow.functions.getActiveStakers(1, 0, 0).call()
    assert 500 == all_locked
    assert 1 == len(stakers)
    assert ursula1 == to_checksum_address(stakers[0][0])
    assert 500 == stakers[0][1]

    # Confirm activity and wait 1 period, locking will be decreased because of end of one stake
    tx = escrow.functions.confirmActivity().transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    testerchain.time_travel(hours=1)
    current_period = escrow.functions.getCurrentPeriod().call()
    assert 500 == escrow.functions.getLockedTokens(ursula1, 0).call()
    assert 0 == escrow.functions.getLockedTokens(ursula1, 1).call()

    events = activity_log.get_all_entries()
    assert 5 == len(events)
    event_args = events[4]['args']
    assert ursula1 == event_args['staker']
    assert current_period == event_args['period']
    assert 500 == event_args['value']

    # Stake is unlocked and Ursula can withdraw some tokens
    tx = escrow.functions.withdraw(100).transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    assert 1900 == token.functions.balanceOf(escrow.address).call()
    assert 8600 == token.functions.balanceOf(ursula1).call()
    events = withdraw_log.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert ursula1 == event_args['staker']
    assert 100 == event_args['value']

    # But Ursula can't withdraw all without unlocking other stakes
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.withdraw(1400).transact({'from': ursula1})
        testerchain.wait_for_receipt(tx)

    # And Ursula can't lock again too low value
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.lock(1, 1).transact({'from': ursula1})
        testerchain.wait_for_receipt(tx)

    # Ursula can deposit and lock more tokens
    tx = token.functions.approveAndCall(escrow.address, 500, testerchain.w3.toBytes(2))\
        .transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.confirmActivity().transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)

    events = activity_log.get_all_entries()
    assert 6 == len(events)
    event_args = events[5]['args']
    assert ursula1 == event_args['staker']
    assert current_period + 1 == event_args['period']
    assert 500 == event_args['value']

    tx = escrow.functions.lock(100, 2).transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)

    events = activity_log.get_all_entries()
    assert 7 == len(events)
    event_args = events[6]['args']
    assert ursula1 == event_args['staker']
    assert current_period + 1 == event_args['period']
    assert 100 == event_args['value']

    # Value of locked tokens will be updated in next period
    assert 500 == escrow.functions.getLockedTokens(ursula1, 0).call()
    assert 600 == escrow.functions.getLockedTokens(ursula1, 1).call()
    assert 600 == escrow.functions.getLockedTokens(ursula1, 2).call()
    assert 0 == escrow.functions.getLockedTokens(ursula1, 3).call()
    testerchain.time_travel(hours=1)
    assert 600 == escrow.functions.getLockedTokens(ursula1, 0).call()
    assert 600 == escrow.functions.getLockedTokens(ursula1, 1).call()
    assert 0 == escrow.functions.getLockedTokens(ursula1, 2).call()

    # Ursula increases lock
    tx = escrow.functions.lock(500, 2).transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.confirmActivity().transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    assert 600 == escrow.functions.getLockedTokens(ursula1, 0).call()
    assert 1100 == escrow.functions.getLockedTokens(ursula1, 1).call()
    assert 500 == escrow.functions.getLockedTokens(ursula1, 2).call()
    assert 0 == escrow.functions.getLockedTokens(ursula1, 3).call()
    testerchain.time_travel(hours=1)
    assert 1100 == escrow.functions.getLockedTokens(ursula1, 0).call()

    # Ursula(2) increases lock by deposit more tokens using approveAndCall
    tx = token.functions.approveAndCall(escrow.address, 500, testerchain.w3.toBytes(2))\
        .transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.confirmActivity().transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    assert 500 == escrow.functions.getLockedTokens(ursula2, 0).call()
    assert 1000 == escrow.functions.getLockedTokens(ursula2, 1).call()
    assert 500 == escrow.functions.getLockedTokens(ursula2, 2).call()
    assert 0 == escrow.functions.getLockedTokens(ursula2, 3).call()
    testerchain.time_travel(hours=1)

    # And increases locked time by dividing stake into two parts
    current_period = escrow.functions.getCurrentPeriod().call()
    assert 2 == escrow.functions.getSubStakesLength(ursula2).call()
    assert current_period + 1 == escrow.functions.getLastPeriodOfSubStake(ursula2, 1).call()
    tx = escrow.functions.divideStake(1, 200, 1).transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    assert 1000 == escrow.functions.getLockedTokens(ursula2, 0).call()
    assert 500 == escrow.functions.getLockedTokens(ursula2, 1).call()
    assert 200 == escrow.functions.getLockedTokens(ursula2, 2).call()
    assert 0 == escrow.functions.getLockedTokens(ursula2, 3).call()

    events = lock_log.get_all_entries()
    assert 8 == len(events)
    event_args = events[7]['args']
    assert ursula2 == event_args['staker']
    assert 200 == event_args['value']
    assert current_period == event_args['firstPeriod']
    assert 2 == event_args['periods']
    events = divides_log.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert ursula2 == event_args['staker']
    assert 500 == event_args['oldValue']
    assert current_period + 1 == event_args['lastPeriod']
    assert 200 == event_args['newValue']
    assert 1 == event_args['periods']

    tx = escrow.functions.confirmActivity().transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    testerchain.time_travel(hours=1)
    # Check number of stakes and last stake parameters
    current_period = escrow.functions.getCurrentPeriod().call()
    assert 3 == escrow.functions.getSubStakesLength(ursula2).call()
    assert current_period == escrow.functions.getLastPeriodOfSubStake(ursula2, 1).call()

    # Can't divide stake again because current period is the last periods for this sub stake
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.divideStake(1, 200, 2).transact({'from': ursula2})
        testerchain.wait_for_receipt(tx)
    # But can lock
    tx = escrow.functions.lock(200, 2).transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    assert 500 == escrow.functions.getLockedTokens(ursula2, 0).call()
    assert 400 == escrow.functions.getLockedTokens(ursula2, 1).call()
    assert 200 == escrow.functions.getLockedTokens(ursula2, 2).call()
    assert 0 == escrow.functions.getLockedTokens(ursula2, 3).call()

    # Check number of stakes and last stake parameters
    assert 4 == escrow.functions.getSubStakesLength(ursula2).call()
    assert current_period + 1 == escrow.functions.getLastPeriodOfSubStake(ursula2, 2).call()

    # Divide stake again
    tx = escrow.functions.divideStake(2, 100, 1).transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    assert 500 == escrow.functions.getLockedTokens(ursula2, 0).call()
    assert 400 == escrow.functions.getLockedTokens(ursula2, 1).call()
    assert 300 == escrow.functions.getLockedTokens(ursula2, 2).call()
    assert 0 == escrow.functions.getLockedTokens(ursula2, 3).call()

    events = divides_log.get_all_entries()
    assert 2 == len(events)
    event_args = events[1]['args']
    assert ursula2 == event_args['staker']
    assert 200 == event_args['oldValue']
    assert current_period + 1 == event_args['lastPeriod']
    assert 100 == event_args['newValue']
    assert 1 == event_args['periods']

    # Prolong some sub stake
    tx = escrow.functions.prolongStake(3, 1).transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    assert 500 == escrow.functions.getLockedTokens(ursula2, 0).call()
    assert 400 == escrow.functions.getLockedTokens(ursula2, 1).call()
    assert 300 == escrow.functions.getLockedTokens(ursula2, 2).call()
    assert 200 == escrow.functions.getLockedTokens(ursula2, 3).call()
    assert 0 == escrow.functions.getLockedTokens(ursula2, 4).call()

    events = lock_log.get_all_entries()
    assert 11 == len(events)
    event_args = events[10]['args']
    assert ursula2 == event_args['staker']
    assert 200 == event_args['value']
    assert current_period + 3 == event_args['firstPeriod']
    assert 1 == event_args['periods']

    # Prolong sub stake that will end in the next period
    tx = escrow.functions.confirmActivity().transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.prolongStake(2, 1).transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    assert 500 == escrow.functions.getLockedTokens(ursula2, 0).call()
    assert 400 == escrow.functions.getLockedTokens(ursula2, 1).call()
    assert 400 == escrow.functions.getLockedTokens(ursula2, 2).call()
    assert 200 == escrow.functions.getLockedTokens(ursula2, 3).call()
    assert 0 == escrow.functions.getLockedTokens(ursula2, 4).call()

    # Check overflow in prolong stake
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.prolongStake(2, MAX_UINT16).transact({'from': ursula2})
        testerchain.wait_for_receipt(tx)

    events = lock_log.get_all_entries()
    assert 12 == len(events)
    event_args = events[11]['args']
    assert ursula2 == event_args['staker']
    assert 100 == event_args['value']
    assert current_period + 2 == event_args['firstPeriod']
    assert 1 == event_args['periods']

    # Can't prolong sub stake that will end in the current period
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.prolongStake(1, 2).transact({'from': ursula2})
        testerchain.wait_for_receipt(tx)

    # Just wait and confirm activity
    testerchain.time_travel(hours=1)
    tx = escrow.functions.confirmActivity().transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    testerchain.time_travel(hours=1)
    tx = escrow.functions.confirmActivity().transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)

    # Can't divide old stake because it's already unlocked
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.divideStake(0, 200, 10).transact({'from': ursula2})
        testerchain.wait_for_receipt(tx)
    # Can't divide nonexistent stake
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.divideStake(10, 100, 1).transact({'from': ursula2})
        testerchain.wait_for_receipt(tx)
    # And can't prolong old stake
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.prolongStake(0, 10).transact({'from': ursula2})
        testerchain.wait_for_receipt(tx)

    current_period = escrow.functions.getCurrentPeriod().call()
    events = activity_log.get_all_entries()
    assert 13 == len(events)
    event_args = events[11]['args']
    assert ursula2 == event_args['staker']
    assert current_period == event_args['period']
    assert 400 == event_args['value']
    event_args = events[12]['args']
    assert ursula2 == event_args['staker']
    assert current_period + 1 == event_args['period']
    assert 200 == event_args['value']

    assert 5 == len(deposit_log.get_all_entries())
    assert 1 == len(withdraw_log.get_all_entries())

    # Test max locking duration
    tx = escrow.functions.lock(200, MAX_UINT16).transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    assert 200 == escrow.functions.getLockedTokens(ursula2, MAX_UINT16 - current_period).call()


@pytest.mark.slow
def test_max_sub_stakes(testerchain, token, escrow_contract):
    escrow = escrow_contract(10000)
    creator = testerchain.client.accounts[0]
    ursula = testerchain.client.accounts[1]

    # Initialize Escrow contract
    tx = escrow.functions.initialize(0).transact({'from': creator})
    testerchain.wait_for_receipt(tx)

    # Prepare before deposit
    tx = token.functions.transfer(ursula, 4000).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    tx = token.functions.approve(escrow.address, 4000).transact({'from': ursula})
    testerchain.wait_for_receipt(tx)

    # Lock one sub stake from current period and others from next one
    tx = escrow.functions.deposit(100, 2).transact({'from': ursula})
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.setWorker(ursula).transact({'from': ursula})
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.setWindDown(True).transact({'from': ursula})
    testerchain.wait_for_receipt(tx)
    assert 1 == escrow.functions.getSubStakesLength(ursula).call()

    tx = escrow.functions.confirmActivity().transact({'from': ursula})
    testerchain.wait_for_receipt(tx)
    testerchain.time_travel(hours=1)
    for index in range(MAX_SUB_STAKES - 1):
        tx = escrow.functions.deposit(100, 2).transact({'from': ursula})
        testerchain.wait_for_receipt(tx)
    assert MAX_SUB_STAKES == escrow.functions.getSubStakesLength(ursula).call()
    assert 3000 == escrow.functions.getLockedTokens(ursula, 1).call()

    # Can't lock more because of reaching the maximum number of active sub stakes
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.deposit(100, 2).transact({'from': ursula})
        testerchain.wait_for_receipt(tx)

    # After two periods first sub stake will be unlocked and we can lock again
    tx = escrow.functions.confirmActivity().transact({'from': ursula})
    testerchain.wait_for_receipt(tx)
    testerchain.time_travel(hours=1)
    tx = escrow.functions.confirmActivity().transact({'from': ursula})
    testerchain.wait_for_receipt(tx)
    testerchain.time_travel(hours=1)
    assert 2900 == escrow.functions.getLockedTokens(ursula, 0).call()
    assert 0 == escrow.functions.getLockedTokens(ursula, 1).call()
    assert MAX_SUB_STAKES == escrow.functions.getSubStakesLength(ursula).call()
    # Before sub stake will be inactive it must be mined
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.deposit(100, 2).transact({'from': ursula})
        testerchain.wait_for_receipt(tx)
    tx = escrow.functions.mint().transact({'from': ursula})
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.deposit(100, 2).transact({'from': ursula})
    testerchain.wait_for_receipt(tx)
    assert 2900 == escrow.functions.getLockedTokens(ursula, 0).call()
    assert 100 == escrow.functions.getLockedTokens(ursula, 1).call()
    assert MAX_SUB_STAKES == escrow.functions.getSubStakesLength(ursula).call()

    # Can't lock more because of reaching the maximum number of active sub stakes and they are not mined yet
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.deposit(100, 2).transact({'from': ursula})
        testerchain.wait_for_receipt(tx)
