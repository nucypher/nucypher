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
from web3.contract import Contract

MAX_SUB_STAKES = 30
MAX_UINT16 = 65535


@pytest.mark.slow
def test_staking(testerchain, token, escrow_contract):
    """
    Tests for staking methods: deposit, lock and stake division
    """

    escrow = escrow_contract(1500)
    creator = testerchain.client.accounts[0]
    staker1 = testerchain.client.accounts[1]
    staker2 = testerchain.client.accounts[2]
    deposit_log = escrow.events.Deposited.createFilter(fromBlock='latest')
    lock_log = escrow.events.Locked.createFilter(fromBlock='latest')
    activity_log = escrow.events.ActivityConfirmed.createFilter(fromBlock='latest')
    divides_log = escrow.events.Divided.createFilter(fromBlock='latest')
    prolong_log = escrow.events.Prolonged.createFilter(fromBlock='latest')
    withdraw_log = escrow.events.Withdrawn.createFilter(fromBlock='latest')
    wind_down_log = escrow.events.WindDownSet.createFilter(fromBlock='latest')

    # Give Staker and Staker(2) some coins
    tx = token.functions.transfer(staker1, 10000).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    tx = token.functions.transfer(staker2, 10000).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert 10000 == token.functions.balanceOf(staker1).call()
    assert 10000 == token.functions.balanceOf(staker2).call()

    # Staker and Staker(2) give Escrow rights to transfer
    tx = token.functions.approve(escrow.address, 1000).transact({'from': staker1})
    testerchain.wait_for_receipt(tx)
    assert 1000 == token.functions.allowance(staker1, escrow.address).call()
    tx = token.functions.approve(escrow.address, 500).transact({'from': staker2})
    testerchain.wait_for_receipt(tx)
    assert 500 == token.functions.allowance(staker2, escrow.address).call()

    # Staker's withdrawal attempt won't succeed because nothing to withdraw
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.withdraw(100).transact({'from': staker1})
        testerchain.wait_for_receipt(tx)

    # Can't lock because nothing to lock
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.lock(500, 2).transact({'from': staker1})
        testerchain.wait_for_receipt(tx)

    # Check that nothing is locked
    assert 0 == escrow.functions.getLockedTokens(staker1, 0).call()
    assert 0 == escrow.functions.getLockedTokens(staker2, 0).call()
    assert 0 == escrow.functions.getLockedTokens(testerchain.client.accounts[3], 0).call()

    # Can't deposit for too short a period (less than _minLockedPeriods coefficient)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.deposit(1000, 1).transact({'from': staker1})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = token.functions.approveAndCall(escrow.address, 1000, testerchain.w3.toBytes(1))\
            .transact({'from': staker1})
        testerchain.wait_for_receipt(tx)

    # Staker transfers some tokens to the escrow and locks them before initialization
    current_period = escrow.functions.getCurrentPeriod().call()
    tx = escrow.functions.deposit(1000, 2).transact({'from': staker1})
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.setWorker(staker1).transact({'from': staker1})
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.setWindDown(True).transact({'from': staker1})
    testerchain.wait_for_receipt(tx)
    assert 1000 == token.functions.balanceOf(escrow.address).call()
    assert 9000 == token.functions.balanceOf(staker1).call()
    assert 0 == escrow.functions.getLockedTokens(staker1, 0).call()
    assert 1000 == escrow.functions.getLockedTokens(staker1, 1).call()
    assert 1000 == escrow.functions.getLockedTokens(staker1, 2).call()
    assert 0 == escrow.functions.getLockedTokens(staker1, 3).call()

    # Check that all events are emitted
    events = deposit_log.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert staker1 == event_args['staker']
    assert 1000 == event_args['value']
    assert 2 == event_args['periods']
    events = lock_log.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert staker1 == event_args['staker']
    assert 1000 == event_args['value']
    assert current_period + 1 == event_args['firstPeriod']
    assert 2 == event_args['periods']
    events = wind_down_log.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert staker1 == event_args['staker']
    assert event_args['windDown']

    # Can't confirm activity before initialization
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.confirmActivity().transact({'from': staker1})
        testerchain.wait_for_receipt(tx)

    # Initialize Escrow contract
    tx = escrow.functions.initialize(0).transact({'from': creator})
    testerchain.wait_for_receipt(tx)

    # Ursula(2) stakes tokens also
    tx = escrow.functions.deposit(500, 2).transact({'from': staker2})
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.setWorker(staker2).transact({'from': staker2})
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.setWindDown(True).transact({'from': staker2})
    testerchain.wait_for_receipt(tx)
    assert 1500 == token.functions.balanceOf(escrow.address).call()
    assert 9500 == token.functions.balanceOf(staker2).call()
    assert 0 == escrow.functions.getLockedTokens(staker2, 0).call()
    assert 500 == escrow.functions.getLockedTokens(staker2, 1).call()

    events = deposit_log.get_all_entries()
    assert 2 == len(events)
    event_args = events[1]['args']
    assert staker2 == event_args['staker']
    assert 500 == event_args['value']
    assert 2 == event_args['periods']
    events = lock_log.get_all_entries()
    assert 2 == len(events)
    event_args = events[1]['args']
    assert staker2 == event_args['staker']
    assert 500 == event_args['value']
    assert current_period + 1 == event_args['firstPeriod']
    assert 2 == event_args['periods']
    events = wind_down_log.get_all_entries()
    assert 2 == len(events)
    event_args = events[1]['args']
    assert staker2 == event_args['staker']
    assert event_args['windDown']

    # Staker and Staker(2) confirm activity
    tx = escrow.functions.confirmActivity().transact({'from': staker1})
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.confirmActivity().transact({'from': staker2})
    testerchain.wait_for_receipt(tx)
    assert current_period + 1 == escrow.functions.getLastActivePeriod(staker1).call()
    assert current_period + 1 == escrow.functions.getLastActivePeriod(staker2).call()

    # No active stakers before next period
    all_locked, stakers = escrow.functions.getActiveStakers(1, 0, 0).call()
    assert 0 == all_locked
    assert 0 == len(stakers)

    events = activity_log.get_all_entries()
    assert 2 == len(events)
    event_args = events[0]['args']
    assert staker1 == event_args['staker']
    assert current_period + 1 == event_args['period']
    assert 1000 == event_args['value']
    events = activity_log.get_all_entries()
    event_args = events[1]['args']
    assert staker2 == event_args['staker']
    assert current_period + 1 == event_args['period']
    assert 500 == event_args['value']

    # Checks locked tokens in the next period
    testerchain.time_travel(hours=1)
    current_period = escrow.functions.getCurrentPeriod().call()
    assert 1000 == escrow.functions.getLockedTokens(staker1, 0).call()
    assert 500 == escrow.functions.getLockedTokens(staker2, 0).call()

    # Both stakers are active and have locked tokens in next period
    all_locked, stakers = escrow.functions.getActiveStakers(1, 0, 0).call()
    assert 1500 == all_locked
    assert 2 == len(stakers)
    assert staker1 == to_checksum_address(stakers[0][0])
    assert 1000 == stakers[0][1]
    assert staker2 == to_checksum_address(stakers[1][0])
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

    # Staker's withdrawal attempt won't succeed because everything is locked
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.withdraw(100).transact({'from': staker1})
        testerchain.wait_for_receipt(tx)
    assert 1500 == token.functions.balanceOf(escrow.address).call()
    assert 9000 == token.functions.balanceOf(staker1).call()

    # Staker can deposit more tokens
    tx = escrow.functions.confirmActivity().transact({'from': staker1})
    testerchain.wait_for_receipt(tx)
    assert current_period + 1 == escrow.functions.getLastActivePeriod(staker1).call()
    assert 1000 == escrow.functions.getLockedTokens(staker1, 1).call()
    assert 0 == escrow.functions.getLockedTokens(staker1, 2).call()

    events = activity_log.get_all_entries()
    assert 3 == len(events)
    event_args = events[2]['args']
    assert staker1 == event_args['staker']
    assert current_period + 1 == event_args['period']
    assert 1000 == event_args['value']

    locked_next_period = escrow.functions.lockedPerPeriod(current_period + 1).call()
    tx = token.functions.approveAndCall(escrow.address, 500, testerchain.w3.toBytes(2))\
        .transact({'from': staker1})
    testerchain.wait_for_receipt(tx)
    assert 2000 == token.functions.balanceOf(escrow.address).call()
    assert 8500 == token.functions.balanceOf(staker1).call()
    assert 1500 == escrow.functions.getLockedTokens(staker1, 1).call()
    assert 500 == escrow.functions.getLockedTokens(staker1, 2).call()
    assert 0 == escrow.functions.getLockedTokens(staker1, 3).call()
    assert locked_next_period + 500 == escrow.functions.lockedPerPeriod(current_period + 1).call()

    events = activity_log.get_all_entries()
    assert 4 == len(events)
    event_args = events[3]['args']
    assert staker1 == event_args['staker']
    assert current_period + 1 == event_args['period']
    assert 500 == event_args['value']

    # Both stakers are active and only the first one locked tokens for two more periods
    all_locked, stakers = escrow.functions.getActiveStakers(2, 0, 0).call()
    assert 500 == all_locked
    assert 1 == len(stakers)
    assert staker1 == to_checksum_address(stakers[0][0])
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
    assert 1500 == escrow.functions.getLockedTokens(staker1, 0).call()

    # Only one staker is active
    all_locked, stakers = escrow.functions.getActiveStakers(1, 0, 0).call()
    assert 500 == all_locked
    assert 1 == len(stakers)
    assert staker1 == to_checksum_address(stakers[0][0])
    assert 500 == stakers[0][1]

    # Confirm activity and wait 1 period, locking will be decreased because of end of one stake
    tx = escrow.functions.confirmActivity().transact({'from': staker1})
    testerchain.wait_for_receipt(tx)
    testerchain.time_travel(hours=1)
    current_period = escrow.functions.getCurrentPeriod().call()
    assert 500 == escrow.functions.getLockedTokens(staker1, 0).call()
    assert 0 == escrow.functions.getLockedTokens(staker1, 1).call()

    events = activity_log.get_all_entries()
    assert 5 == len(events)
    event_args = events[4]['args']
    assert staker1 == event_args['staker']
    assert current_period == event_args['period']
    assert 500 == event_args['value']

    # Stake is unlocked and Staker can withdraw some tokens
    tx = escrow.functions.withdraw(100).transact({'from': staker1})
    testerchain.wait_for_receipt(tx)
    assert 1900 == token.functions.balanceOf(escrow.address).call()
    assert 8600 == token.functions.balanceOf(staker1).call()
    events = withdraw_log.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert staker1 == event_args['staker']
    assert 100 == event_args['value']

    # But Staker can't withdraw all without unlocking other stakes
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.withdraw(1400).transact({'from': staker1})
        testerchain.wait_for_receipt(tx)

    # Staker can deposit and lock more tokens
    tx = token.functions.approveAndCall(escrow.address, 500, testerchain.w3.toBytes(2))\
        .transact({'from': staker1})
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.confirmActivity().transact({'from': staker1})
    testerchain.wait_for_receipt(tx)

    events = activity_log.get_all_entries()
    assert 6 == len(events)
    event_args = events[5]['args']
    assert staker1 == event_args['staker']
    assert current_period + 1 == event_args['period']
    assert 500 == event_args['value']

    tx = escrow.functions.lock(100, 2).transact({'from': staker1})
    testerchain.wait_for_receipt(tx)

    events = activity_log.get_all_entries()
    assert 7 == len(events)
    event_args = events[6]['args']
    assert staker1 == event_args['staker']
    assert current_period + 1 == event_args['period']
    assert 100 == event_args['value']

    # Value of locked tokens will be updated in next period
    assert 500 == escrow.functions.getLockedTokens(staker1, 0).call()
    assert 600 == escrow.functions.getLockedTokens(staker1, 1).call()
    assert 600 == escrow.functions.getLockedTokens(staker1, 2).call()
    assert 0 == escrow.functions.getLockedTokens(staker1, 3).call()
    testerchain.time_travel(hours=1)
    assert 600 == escrow.functions.getLockedTokens(staker1, 0).call()
    assert 600 == escrow.functions.getLockedTokens(staker1, 1).call()
    assert 0 == escrow.functions.getLockedTokens(staker1, 2).call()

    # Staker increases lock
    tx = escrow.functions.lock(500, 2).transact({'from': staker1})
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.confirmActivity().transact({'from': staker1})
    testerchain.wait_for_receipt(tx)
    assert 600 == escrow.functions.getLockedTokens(staker1, 0).call()
    assert 1100 == escrow.functions.getLockedTokens(staker1, 1).call()
    assert 500 == escrow.functions.getLockedTokens(staker1, 2).call()
    assert 0 == escrow.functions.getLockedTokens(staker1, 3).call()
    testerchain.time_travel(hours=1)
    assert 1100 == escrow.functions.getLockedTokens(staker1, 0).call()

    # Staker(2) increases lock by deposit more tokens using approveAndCall
    tx = token.functions.approveAndCall(escrow.address, 500, testerchain.w3.toBytes(2))\
        .transact({'from': staker2})
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.confirmActivity().transact({'from': staker2})
    testerchain.wait_for_receipt(tx)
    assert 500 == escrow.functions.getLockedTokens(staker2, 0).call()
    assert 1000 == escrow.functions.getLockedTokens(staker2, 1).call()
    assert 500 == escrow.functions.getLockedTokens(staker2, 2).call()
    assert 0 == escrow.functions.getLockedTokens(staker2, 3).call()
    testerchain.time_travel(hours=1)

    # And increases locked time by dividing stake into two parts
    current_period = escrow.functions.getCurrentPeriod().call()
    assert 2 == escrow.functions.getSubStakesLength(staker2).call()
    assert current_period + 1 == escrow.functions.getLastPeriodOfSubStake(staker2, 1).call()
    tx = escrow.functions.divideStake(1, 200, 1).transact({'from': staker2})
    testerchain.wait_for_receipt(tx)
    assert 1000 == escrow.functions.getLockedTokens(staker2, 0).call()
    assert 500 == escrow.functions.getLockedTokens(staker2, 1).call()
    assert 200 == escrow.functions.getLockedTokens(staker2, 2).call()
    assert 0 == escrow.functions.getLockedTokens(staker2, 3).call()

    events = lock_log.get_all_entries()
    assert 8 == len(events)
    event_args = events[7]['args']
    assert staker2 == event_args['staker']
    assert 200 == event_args['value']
    assert current_period == event_args['firstPeriod']
    assert 2 == event_args['periods']
    events = divides_log.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert staker2 == event_args['staker']
    assert 500 == event_args['oldValue']
    assert current_period + 1 == event_args['lastPeriod']
    assert 200 == event_args['newValue']
    assert 1 == event_args['periods']

    tx = escrow.functions.confirmActivity().transact({'from': staker2})
    testerchain.wait_for_receipt(tx)
    testerchain.time_travel(hours=1)
    # Check number of stakes and last stake parameters
    current_period = escrow.functions.getCurrentPeriod().call()
    assert 3 == escrow.functions.getSubStakesLength(staker2).call()
    assert current_period == escrow.functions.getLastPeriodOfSubStake(staker2, 1).call()

    # Can't divide stake again because current period is the last periods for this sub stake
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.divideStake(1, 200, 2).transact({'from': staker2})
        testerchain.wait_for_receipt(tx)
    # But can lock
    tx = escrow.functions.lock(200, 2).transact({'from': staker2})
    testerchain.wait_for_receipt(tx)
    assert 500 == escrow.functions.getLockedTokens(staker2, 0).call()
    assert 400 == escrow.functions.getLockedTokens(staker2, 1).call()
    assert 200 == escrow.functions.getLockedTokens(staker2, 2).call()
    assert 0 == escrow.functions.getLockedTokens(staker2, 3).call()

    # Check number of stakes and last stake parameters
    assert 4 == escrow.functions.getSubStakesLength(staker2).call()
    assert current_period + 1 == escrow.functions.getLastPeriodOfSubStake(staker2, 2).call()

    # Divide stake again
    tx = escrow.functions.divideStake(2, 100, 1).transact({'from': staker2})
    testerchain.wait_for_receipt(tx)
    assert 500 == escrow.functions.getLockedTokens(staker2, 0).call()
    assert 400 == escrow.functions.getLockedTokens(staker2, 1).call()
    assert 300 == escrow.functions.getLockedTokens(staker2, 2).call()
    assert 0 == escrow.functions.getLockedTokens(staker2, 3).call()

    events = divides_log.get_all_entries()
    assert 2 == len(events)
    event_args = events[1]['args']
    assert staker2 == event_args['staker']
    assert 200 == event_args['oldValue']
    assert current_period + 1 == event_args['lastPeriod']
    assert 100 == event_args['newValue']
    assert 1 == event_args['periods']

    # Prolong some sub stake
    tx = escrow.functions.prolongStake(3, 1).transact({'from': staker2})
    testerchain.wait_for_receipt(tx)
    assert 500 == escrow.functions.getLockedTokens(staker2, 0).call()
    assert 400 == escrow.functions.getLockedTokens(staker2, 1).call()
    assert 300 == escrow.functions.getLockedTokens(staker2, 2).call()
    assert 200 == escrow.functions.getLockedTokens(staker2, 3).call()
    assert 0 == escrow.functions.getLockedTokens(staker2, 4).call()

    events = lock_log.get_all_entries()
    assert 11 == len(events)
    event_args = events[10]['args']
    assert staker2 == event_args['staker']
    assert 200 == event_args['value']
    assert current_period + 3 == event_args['firstPeriod']
    assert 1 == event_args['periods']

    events = prolong_log.get_all_entries()
    assert len(events) == 1
    event_args = events[0]['args']
    assert staker2 == event_args['staker']
    assert 200 == event_args['value']
    assert current_period + 2 == event_args['lastPeriod']
    assert 1 == event_args['periods']

    # Prolong sub stake that will end in the next period
    tx = escrow.functions.confirmActivity().transact({'from': staker2})
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.prolongStake(2, 1).transact({'from': staker2})
    testerchain.wait_for_receipt(tx)
    assert 500 == escrow.functions.getLockedTokens(staker2, 0).call()
    assert 400 == escrow.functions.getLockedTokens(staker2, 1).call()
    assert 400 == escrow.functions.getLockedTokens(staker2, 2).call()
    assert 200 == escrow.functions.getLockedTokens(staker2, 3).call()
    assert 0 == escrow.functions.getLockedTokens(staker2, 4).call()

    # Check overflow in prolong stake
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.prolongStake(2, MAX_UINT16).transact({'from': staker2})
        testerchain.wait_for_receipt(tx)

    events = lock_log.get_all_entries()
    assert 12 == len(events)
    event_args = events[11]['args']
    assert staker2 == event_args['staker']
    assert 100 == event_args['value']
    assert current_period + 2 == event_args['firstPeriod']
    assert 1 == event_args['periods']

    events = prolong_log.get_all_entries()
    assert len(events) == 2
    event_args = events[1]['args']
    assert staker2 == event_args['staker']
    assert 100 == event_args['value']
    assert current_period + 1 == event_args['lastPeriod']
    assert 1 == event_args['periods']

    # Can't prolong sub stake that will end in the current period
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.prolongStake(1, 2).transact({'from': staker2})
        testerchain.wait_for_receipt(tx)

    # Just wait and confirm activity
    testerchain.time_travel(hours=1)
    tx = escrow.functions.confirmActivity().transact({'from': staker2})
    testerchain.wait_for_receipt(tx)
    testerchain.time_travel(hours=1)
    tx = escrow.functions.confirmActivity().transact({'from': staker2})
    testerchain.wait_for_receipt(tx)

    # Can't divide old stake because it's already unlocked
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.divideStake(0, 200, 10).transact({'from': staker2})
        testerchain.wait_for_receipt(tx)
    # Can't divide nonexistent stake
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.divideStake(10, 100, 1).transact({'from': staker2})
        testerchain.wait_for_receipt(tx)
    # And can't prolong old stake
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.prolongStake(0, 10).transact({'from': staker2})
        testerchain.wait_for_receipt(tx)

    current_period = escrow.functions.getCurrentPeriod().call()
    events = activity_log.get_all_entries()
    assert 13 == len(events)
    event_args = events[11]['args']
    assert staker2 == event_args['staker']
    assert current_period == event_args['period']
    assert 400 == event_args['value']
    event_args = events[12]['args']
    assert staker2 == event_args['staker']
    assert current_period + 1 == event_args['period']
    assert 200 == event_args['value']

    assert 5 == len(deposit_log.get_all_entries())
    assert 1 == len(withdraw_log.get_all_entries())

    # Test max locking duration
    tx = escrow.functions.lock(200, MAX_UINT16).transact({'from': staker2})
    testerchain.wait_for_receipt(tx)
    assert 200 == escrow.functions.getLockedTokens(staker2, MAX_UINT16 - current_period).call()


@pytest.mark.slow
def test_max_sub_stakes(testerchain, token, escrow_contract):
    escrow = escrow_contract(10000)
    creator = testerchain.client.accounts[0]
    staker = testerchain.client.accounts[1]

    # Initialize Escrow contract
    tx = escrow.functions.initialize(0).transact({'from': creator})
    testerchain.wait_for_receipt(tx)

    # Prepare before deposit
    tx = token.functions.transfer(staker, 4000).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    tx = token.functions.approve(escrow.address, 4000).transact({'from': staker})
    testerchain.wait_for_receipt(tx)

    # Lock one sub stake from current period and others from next one
    tx = escrow.functions.deposit(100, 2).transact({'from': staker})
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.setWorker(staker).transact({'from': staker})
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.setWindDown(True).transact({'from': staker})
    testerchain.wait_for_receipt(tx)
    assert 1 == escrow.functions.getSubStakesLength(staker).call()

    tx = escrow.functions.confirmActivity().transact({'from': staker})
    testerchain.wait_for_receipt(tx)
    testerchain.time_travel(hours=1)
    for index in range(MAX_SUB_STAKES - 1):
        tx = escrow.functions.deposit(100, 2).transact({'from': staker})
        testerchain.wait_for_receipt(tx)
    assert MAX_SUB_STAKES == escrow.functions.getSubStakesLength(staker).call()
    assert 3000 == escrow.functions.getLockedTokens(staker, 1).call()

    # Can't lock more because of reaching the maximum number of active sub stakes
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.deposit(100, 2).transact({'from': staker})
        testerchain.wait_for_receipt(tx)

    # After two periods first sub stake will be unlocked and we can lock again
    tx = escrow.functions.confirmActivity().transact({'from': staker})
    testerchain.wait_for_receipt(tx)
    testerchain.time_travel(hours=1)
    tx = escrow.functions.confirmActivity().transact({'from': staker})
    testerchain.wait_for_receipt(tx)
    testerchain.time_travel(hours=1)
    assert 2900 == escrow.functions.getLockedTokens(staker, 0).call()
    assert 0 == escrow.functions.getLockedTokens(staker, 1).call()
    assert MAX_SUB_STAKES == escrow.functions.getSubStakesLength(staker).call()
    # Before sub stake will be inactive it must be mined
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.deposit(100, 2).transact({'from': staker})
        testerchain.wait_for_receipt(tx)
    tx = escrow.functions.mint().transact({'from': staker})
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.deposit(100, 2).transact({'from': staker})
    testerchain.wait_for_receipt(tx)
    assert 2900 == escrow.functions.getLockedTokens(staker, 0).call()
    assert 100 == escrow.functions.getLockedTokens(staker, 1).call()
    assert MAX_SUB_STAKES == escrow.functions.getSubStakesLength(staker).call()

    # Can't lock more because of reaching the maximum number of active sub stakes and they are not mined yet
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.deposit(100, 2).transact({'from': staker})
        testerchain.wait_for_receipt(tx)


@pytest.mark.slow
def test_allowable_locked_tokens(testerchain, token_economics, token, escrow_contract, deploy_contract):
    maximum_allowed = 1500
    minimum_allowed = token_economics.minimum_allowed_locked
    escrow = escrow_contract(maximum_allowed)
    creator, staker1, staker2, *everyone_else = testerchain.client.accounts

    # Initialize Escrow contract
    tx = escrow.functions.initialize(0).transact({'from': creator})
    testerchain.wait_for_receipt(tx)

    # Prepare before deposit
    duration = token_economics.minimum_locked_periods
    tx = token.functions.transfer(staker1, 2 * maximum_allowed).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    tx = token.functions.transfer(staker2, 2 * maximum_allowed).transact({'from': creator})
    testerchain.wait_for_receipt(tx)

    # Staker can't deposit and lock too low value (less than _minAllowableLockedTokens coefficient)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = token.functions.approveAndCall(escrow.address, minimum_allowed - 1, testerchain.w3.toBytes(duration))\
            .transact({'from': staker1})
        testerchain.wait_for_receipt(tx)
    # And can't deposit and lock too high value (more than _maxAllowableLockedTokens coefficient)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = token.functions.approveAndCall(escrow.address, maximum_allowed + 1, testerchain.w3.toBytes(duration))\
            .transact({'from': staker1})
        testerchain.wait_for_receipt(tx)

    tx = token.functions.approve(escrow.address, maximum_allowed + 1).transact({'from': staker1})
    testerchain.wait_for_receipt(tx)
    # Staker can't deposit and lock too low value (less than _minAllowableLockedTokens coefficient)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.deposit(minimum_allowed - 1, duration).transact({'from': staker1})
        testerchain.wait_for_receipt(tx)
    # And can't deposit and lock too high value (more than _maxAllowableLockedTokens coefficient)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.deposit(maximum_allowed + 1, duration).transact({'from': staker1})
        testerchain.wait_for_receipt(tx)

    tx = escrow.functions.deposit(minimum_allowed, duration).transact({'from': staker1})
    testerchain.wait_for_receipt(tx)
    staker1_lock = minimum_allowed
    tx = token.functions.approve(escrow.address, 0).transact({'from': staker1})
    testerchain.wait_for_receipt(tx)
    tx = token.functions.approveAndCall(escrow.address, minimum_allowed, testerchain.w3.toBytes(duration)) \
        .transact({'from': staker1})
    testerchain.wait_for_receipt(tx)
    staker1_lock += minimum_allowed

    # Preparation for next cases
    tx = token.functions.approveAndCall(escrow.address, minimum_allowed, testerchain.w3.toBytes(duration))\
        .transact({'from': staker1})
    testerchain.wait_for_receipt(tx)
    staker1_lock += minimum_allowed
    tx = token.functions.approveAndCall(escrow.address, maximum_allowed, testerchain.w3.toBytes(duration))\
        .transact({'from': staker2})
    testerchain.wait_for_receipt(tx)

    # Can't deposit or lock too high value (more than _maxAllowableLockedTokens coefficient)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = token.functions.approveAndCall(escrow.address, minimum_allowed, testerchain.w3.toBytes(2 * duration))\
            .transact({'from': staker2})
        testerchain.wait_for_receipt(tx)
    tx = token.functions.approve(escrow.address, minimum_allowed).transact({'from': staker2})
    testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.deposit(minimum_allowed, 2 * duration).transact({'from': staker2})
        testerchain.wait_for_receipt(tx)

    # Prepare for testing `lock()`: staker makes new sub-staker and unlocks first sub-stake
    tx = token.functions\
        .approveAndCall(escrow.address, maximum_allowed - staker1_lock, testerchain.w3.toBytes(2 * duration)) \
        .transact({'from': staker1})
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.setWindDown(True).transact({'from': staker1})
    testerchain.wait_for_receipt(tx)
    tx = escrow.functions.setWorker(staker1).transact({'from': staker1})
    testerchain.wait_for_receipt(tx)
    for _ in range(duration):
        tx = escrow.functions.confirmActivity().transact({'from': staker1})
        testerchain.wait_for_receipt(tx)
        testerchain.time_travel(hours=1)
    testerchain.time_travel(hours=2)
    staker1_lock = maximum_allowed - staker1_lock
    assert escrow.functions.getLockedTokens(staker1, 0).call() == staker1_lock

    # Staker can't lock again too low or too high value
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.lock(minimum_allowed - 1, duration).transact({'from': staker1})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.lock(maximum_allowed - staker1_lock + 1, duration).transact({'from': staker1})
        testerchain.wait_for_receipt(tx)

    tx = escrow.functions.lock(minimum_allowed, duration).transact({'from': staker1})
    testerchain.wait_for_receipt(tx)
    staker1_lock += minimum_allowed
    tx = escrow.functions.lock(maximum_allowed - staker1_lock, duration).transact({'from': staker1})
    testerchain.wait_for_receipt(tx)


@pytest.mark.slow
def test_batch_deposit(testerchain, token, escrow_contract, deploy_contract):
    escrow = escrow_contract(1500)
    policy_manager_interface = testerchain.get_contract_factory('PolicyManagerForStakingEscrowMock')
    policy_manager = testerchain.client.get_contract(
        abi=policy_manager_interface.abi,
        address=escrow.functions.policyManager().call(),
        ContractFactoryClass=Contract)

    creator = testerchain.client.accounts[0]
    deposit_log = escrow.events.Deposited.createFilter(fromBlock='latest')
    lock_log = escrow.events.Locked.createFilter(fromBlock='latest')

    # Grant access to transfer tokens
    tx = token.functions.approve(escrow.address, 10000).transact({'from': creator})
    testerchain.wait_for_receipt(tx)

    # Deposit tokens for 1 staker
    staker = testerchain.client.accounts[1]
    tx = escrow.functions.batchDeposit([staker], [1], [1000], [10]).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    escrow_balance = 1000
    assert token.functions.balanceOf(escrow.address).call() == escrow_balance
    assert escrow.functions.getAllTokens(staker).call() == 1000
    assert escrow.functions.getLockedTokens(staker, 0).call() == 0
    assert escrow.functions.getLockedTokens(staker, 1).call() == 1000
    assert escrow.functions.getLockedTokens(staker, 10).call() == 1000
    assert escrow.functions.getLockedTokens(staker, 11).call() == 0
    current_period = escrow.functions.getCurrentPeriod().call()
    assert policy_manager.functions.getPeriodsLength(staker).call() == 1
    assert policy_manager.functions.getPeriod(staker, 0).call() == current_period - 1
    assert escrow.functions.getPastDowntimeLength(staker).call() == 0
    assert escrow.functions.getLastActivePeriod(staker).call() == 0

    deposit_events = deposit_log.get_all_entries()
    assert len(deposit_events) == 1
    event_args = deposit_events[-1]['args']
    assert event_args['staker'] == staker
    assert event_args['value'] == 1000
    assert event_args['periods'] == 10

    lock_events = lock_log.get_all_entries()
    assert len(lock_events) == 1
    event_args = lock_events[-1]['args']
    assert event_args['staker'] == staker
    assert event_args['value'] == 1000
    assert event_args['firstPeriod'] == current_period + 1
    assert event_args['periods'] == 10

    # Can't deposit tokens again for the same staker twice
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.batchDeposit([staker], [1], [1000], [10])\
            .transact({'from': creator})
        testerchain.wait_for_receipt(tx)

    # Can't deposit tokens with too low or too high value
    staker = testerchain.client.accounts[2]
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.batchDeposit([staker], [1], [1], [10])\
            .transact({'from': creator})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.batchDeposit([staker], [1], [1501], [10])\
            .transact({'from': creator})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.batchDeposit([staker], [1], [500], [1])\
            .transact({'from': creator})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.batchDeposit([staker], [2], [1000, 501], [10, 10])\
            .transact({'from': creator})
        testerchain.wait_for_receipt(tx)

    # Inconsistent input
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.batchDeposit([staker], [0], [500], [10])\
            .transact({'from': creator})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.batchDeposit([staker], [2], [500], [10])\
            .transact({'from': creator})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.batchDeposit([staker], [1, 1], [500], [10])\
            .transact({'from': creator})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.batchDeposit([staker], [1, 1], [500, 500], [10])\
            .transact({'from': creator})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.batchDeposit([staker], [1, 1], [500, 500], [10, 10])\
            .transact({'from': creator})
        testerchain.wait_for_receipt(tx)
    stakers = testerchain.client.accounts[2:4]
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.batchDeposit(stakers, [1, 1], [500, 500, 500], [10, 10, 10])\
            .transact({'from': creator})
        testerchain.wait_for_receipt(tx)

    # Initialize Escrow contract
    tx = escrow.functions.initialize(0).transact({'from': creator})
    testerchain.wait_for_receipt(tx)

    # Deposit tokens for multiple stakers
    stakers = testerchain.client.accounts[2:7]
    tx = escrow.functions.batchDeposit(
        stakers, [1, 1, 1, 1, 1], [100, 200, 300, 400, 500], [50, 100, 150, 200, 250]).transact({'from': creator})
    testerchain.wait_for_receipt(tx)

    escrow_balance += 1500
    assert token.functions.balanceOf(escrow.address).call() == escrow_balance
    current_period = escrow.functions.getCurrentPeriod().call()
    deposit_events = deposit_log.get_all_entries()
    lock_events = lock_log.get_all_entries()

    assert len(deposit_events) == 6
    assert len(lock_events) == 6

    for index, staker in enumerate(stakers):
        value = 100 * (index + 1)
        duration = 50 * (index + 1)
        assert escrow.functions.getAllTokens(staker).call() == value
        assert escrow.functions.getLockedTokens(staker, 0).call() == 0
        assert escrow.functions.getLockedTokens(staker, 1).call() == value
        assert escrow.functions.getLockedTokens(staker, duration).call() == value
        assert escrow.functions.getLockedTokens(staker, duration + 1).call() == 0
        assert policy_manager.functions.getPeriodsLength(staker).call() == 1
        assert policy_manager.functions.getPeriod(staker, 0).call() == current_period - 1
        assert escrow.functions.getPastDowntimeLength(staker).call() == 0
        assert escrow.functions.getLastActivePeriod(staker).call() == 0

        event_args = deposit_events[index + 1]['args']
        assert event_args['staker'] == staker
        assert event_args['value'] == value
        assert event_args['periods'] == duration

        event_args = lock_events[index + 1]['args']
        assert event_args['staker'] == staker
        assert event_args['value'] == value
        assert event_args['firstPeriod'] == current_period + 1
        assert event_args['periods'] == duration

    # Deposit tokens for multiple stakers with multiple sub-stakes
    stakers = testerchain.client.accounts[7:10]
    tx = escrow.functions.batchDeposit(
        stakers, [1, 2, 3], [100, 200, 300, 400, 500, 600], [50, 100, 150, 200, 250, 300])\
        .transact({'from': creator})
    testerchain.wait_for_receipt(tx)

    escrow_balance += 2100
    assert token.functions.balanceOf(escrow.address).call() == escrow_balance
    current_period = escrow.functions.getCurrentPeriod().call()
    deposit_events = deposit_log.get_all_entries()
    lock_events = lock_log.get_all_entries()

    assert len(deposit_events) == 12
    assert len(lock_events) == 12

    staker = stakers[0]
    duration = 50
    value = 100
    assert escrow.functions.getAllTokens(staker).call() == value
    assert escrow.functions.getLockedTokens(staker, 1).call() == value
    assert escrow.functions.getLockedTokens(staker, duration).call() == value
    assert escrow.functions.getLockedTokens(staker, duration + 1).call() == 0
    assert policy_manager.functions.getPeriodsLength(staker).call() == 1
    assert policy_manager.functions.getPeriod(staker, 0).call() == current_period - 1
    assert escrow.functions.getPastDowntimeLength(staker).call() == 0
    assert escrow.functions.getLastActivePeriod(staker).call() == 0
    assert escrow.functions.getSubStakesLength(staker).call() == 1

    event_args = deposit_events[6]['args']
    assert event_args['staker'] == staker
    assert event_args['value'] == value
    assert event_args['periods'] == duration

    event_args = lock_events[6]['args']
    assert event_args['staker'] == staker
    assert event_args['value'] == value
    assert event_args['firstPeriod'] == current_period + 1
    assert event_args['periods'] == duration

    staker = stakers[1]
    duration1 = 100
    duration2 = 150
    value1 = 200
    value2 = 300
    assert escrow.functions.getAllTokens(staker).call() == value1 + value2
    assert escrow.functions.getLockedTokens(staker, 0).call() == 0
    assert escrow.functions.getLockedTokens(staker, 1).call() == value1 + value2
    assert escrow.functions.getLockedTokens(staker, duration1).call() == value1 + value2
    assert escrow.functions.getLockedTokens(staker, duration1 + 1).call() == value2
    assert escrow.functions.getLockedTokens(staker, duration2).call() == value2
    assert escrow.functions.getLockedTokens(staker, duration2 + 1).call() == 0
    assert policy_manager.functions.getPeriodsLength(staker).call() == 1
    assert policy_manager.functions.getPeriod(staker, 0).call() == current_period - 1
    assert escrow.functions.getPastDowntimeLength(staker).call() == 0
    assert escrow.functions.getLastActivePeriod(staker).call() == 0
    assert escrow.functions.getSubStakesLength(staker).call() == 2

    event_args = deposit_events[7]['args']
    assert event_args['staker'] == staker
    assert event_args['value'] == value1
    assert event_args['periods'] == duration1

    event_args = lock_events[7]['args']
    assert event_args['staker'] == staker
    assert event_args['value'] == value1
    assert event_args['firstPeriod'] == current_period + 1
    assert event_args['periods'] == duration1

    event_args = deposit_events[8]['args']
    assert event_args['staker'] == staker
    assert event_args['value'] == value2
    assert event_args['periods'] == duration2

    event_args = lock_events[8]['args']
    assert event_args['staker'] == staker
    assert event_args['value'] == value2
    assert event_args['firstPeriod'] == current_period + 1
    assert event_args['periods'] == duration2

    staker = stakers[2]
    duration1 = 200
    duration2 = 250
    duration3 = 300
    value1 = 400
    value2 = 500
    value3 = 600
    assert escrow.functions.getAllTokens(staker).call() == value1 + value2 + value3
    assert escrow.functions.getLockedTokens(staker, 0).call() == 0
    assert escrow.functions.getLockedTokens(staker, 1).call() == value1 + value2 + value3
    assert escrow.functions.getLockedTokens(staker, duration1).call() == value1 + value2 + value3
    assert escrow.functions.getLockedTokens(staker, duration1 + 1).call() == value2 + value3
    assert escrow.functions.getLockedTokens(staker, duration2).call() == value2 + value3
    assert escrow.functions.getLockedTokens(staker, duration2 + 1).call() == value3
    assert escrow.functions.getLockedTokens(staker, duration3).call() == value3
    assert escrow.functions.getLockedTokens(staker, duration3 + 1).call() == 0
    assert policy_manager.functions.getPeriodsLength(staker).call() == 1
    assert policy_manager.functions.getPeriod(staker, 0).call() == current_period - 1
    assert escrow.functions.getPastDowntimeLength(staker).call() == 0
    assert escrow.functions.getLastActivePeriod(staker).call() == 0
    assert escrow.functions.getSubStakesLength(staker).call() == 3

    event_args = deposit_events[9]['args']
    assert event_args['staker'] == staker
    assert event_args['value'] == value1
    assert event_args['periods'] == duration1

    event_args = lock_events[9]['args']
    assert event_args['staker'] == staker
    assert event_args['value'] == value1
    assert event_args['firstPeriod'] == current_period + 1
    assert event_args['periods'] == duration1

    event_args = deposit_events[10]['args']
    assert event_args['staker'] == staker
    assert event_args['value'] == value2
    assert event_args['periods'] == duration2

    event_args = lock_events[10]['args']
    assert event_args['staker'] == staker
    assert event_args['value'] == value2
    assert event_args['firstPeriod'] == current_period + 1
    assert event_args['periods'] == duration2

    event_args = deposit_events[11]['args']
    assert event_args['staker'] == staker
    assert event_args['value'] == value3
    assert event_args['periods'] == duration3

    event_args = lock_events[11]['args']
    assert event_args['staker'] == staker
    assert event_args['value'] == value3
    assert event_args['firstPeriod'] == current_period + 1
    assert event_args['periods'] == duration3
