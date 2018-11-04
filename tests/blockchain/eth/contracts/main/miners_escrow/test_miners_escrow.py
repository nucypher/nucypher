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
import pytest
from eth_tester.exceptions import TransactionFailed

VALUE_FIELD = 0
DECIMALS_FIELD = 1
CONFIRMED_PERIOD_1_FIELD = 2
CONFIRMED_PERIOD_2_FIELD = 3
LAST_ACTIVE_PERIOD_FIELD = 4


@pytest.mark.slow
def test_staking(testerchain, token, escrow_contract):
    """
    Tests for staking methods: deposit, lock and stake division
    """

    escrow = escrow_contract(1500)
    creator = testerchain.interface.w3.eth.accounts[0]
    ursula1 = testerchain.interface.w3.eth.accounts[1]
    ursula2 = testerchain.interface.w3.eth.accounts[2]
    deposit_log = escrow.events.Deposited.createFilter(fromBlock='latest')
    lock_log = escrow.events.Locked.createFilter(fromBlock='latest')
    activity_log = escrow.events.ActivityConfirmed.createFilter(fromBlock='latest')
    divides_log = escrow.events.Divided.createFilter(fromBlock='latest')
    withdraw_log = escrow.events.Withdrawn.createFilter(fromBlock='latest')

    # Give Ursula and Ursula(2) some coins
    tx = token.functions.transfer(ursula1, 10000).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    tx = token.functions.transfer(ursula2, 10000).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert 10000 == token.functions.balanceOf(ursula1).call()
    assert 10000 == token.functions.balanceOf(ursula2).call()

    # Ursula and Ursula(2) give Escrow rights to transfer
    tx = token.functions.approve(escrow.address, 1100).transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    assert 1100 == token.functions.allowance(ursula1, escrow.address).call()
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
    assert 0 == escrow.functions.getLockedTokens(ursula1).call()
    assert 0 == escrow.functions.getLockedTokens(ursula2).call()
    assert 0 == escrow.functions.getLockedTokens(testerchain.interface.w3.eth.accounts[3]).call()

    # Ursula can't deposit tokens before Escrow initialization
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.deposit(1, 1).transact({'from': ursula1})
        testerchain.wait_for_receipt(tx)

    # Initialize Escrow contract
    tx = escrow.functions.initialize().transact({'from': creator})
    testerchain.wait_for_receipt(tx)

    # Ursula can't deposit and lock too low value (less than _minAllowableLockedTokens coefficient)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.deposit(1, 10).transact({'from': ursula1})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = token.functions.approveAndCall(escrow.address, 1, testerchain.interface.w3.toBytes(10))\
            .transact({'from': ursula1})
        testerchain.wait_for_receipt(tx)
    # And can't deposit and lock too high value (more than _maxAllowableLockedTokens coefficient)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.deposit(1501, 10).transact({'from': ursula1})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = token.functions.approveAndCall(escrow.address, 1501, testerchain.interface.w3.toBytes(10))\
            .transact({'from': ursula1})
        testerchain.wait_for_receipt(tx)
    # And can't deposit for too short a period (less than _minLockedPeriods coefficient)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.deposit(1000, 1).transact({'from': ursula1})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = token.functions.approveAndCall(escrow.address, 1000, testerchain.interface.w3.toBytes(1))\
            .transact({'from': ursula1})
        testerchain.wait_for_receipt(tx)

    # Ursula transfers some tokens to the escrow and lock them
    tx = escrow.functions.deposit(1000, 2).transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    assert 1000 == token.functions.balanceOf(escrow.address).call()
    assert 9000 == token.functions.balanceOf(ursula1).call()
    assert 0 == escrow.functions.getLockedTokens(ursula1).call()
    assert 1000 == escrow.functions.getLockedTokens(ursula1, 1).call()
    assert 1000 == escrow.functions.getLockedTokens(ursula1, 2).call()
    assert 0 == escrow.functions.getLockedTokens(ursula1, 3).call()
    assert escrow.functions.getCurrentPeriod().call() + 1 == escrow.functions.getLastActivePeriod(ursula1).call()

    # Check that all events are emitted
    events = deposit_log.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert ursula1 == event_args['miner']
    assert 1000 == event_args['value']
    assert 2 == event_args['periods']
    events = lock_log.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert ursula1 == event_args['miner']
    assert 1000 == event_args['value']
    assert escrow.functions.getCurrentPeriod().call() + 1 == event_args['firstPeriod']
    assert 2 == event_args['periods']
    events = activity_log.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert ursula1 == event_args['miner']
    assert escrow.functions.getCurrentPeriod().call() + 1 == event_args['period']
    assert 1000 == event_args['value']

    # Ursula(2) stakes tokens also
    tx = escrow.functions.deposit(500, 2).transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    assert 1500 == token.functions.balanceOf(escrow.address).call()
    assert 9500 == token.functions.balanceOf(ursula2).call()
    assert 0 == escrow.functions.getLockedTokens(ursula2).call()
    assert 500 == escrow.functions.getLockedTokens(ursula2, 1).call()
    assert escrow.functions.getCurrentPeriod().call() + 1 == escrow.functions.getLastActivePeriod(ursula2).call()

    events = deposit_log.get_all_entries()
    assert 2 == len(events)
    event_args = events[1]['args']
    assert ursula2 == event_args['miner']
    assert 500 == event_args['value']
    assert 2 == event_args['periods']
    events = lock_log.get_all_entries()
    assert 2 == len(events)
    event_args = events[1]['args']
    assert ursula2 == event_args['miner']
    assert 500 == event_args['value']
    assert escrow.functions.getCurrentPeriod().call() + 1 == event_args['firstPeriod']
    assert 2 == event_args['periods']
    events = activity_log.get_all_entries()
    assert 2 == len(events)
    event_args = events[1]['args']
    assert ursula2 == event_args['miner']
    assert escrow.functions.getCurrentPeriod().call() + 1 == event_args['period']
    assert 500 == event_args['value']

    # Checks locked tokens in the next period
    testerchain.time_travel(hours=1)
    assert 1000 == escrow.functions.getLockedTokens(ursula1).call()
    assert 500 == escrow.functions.getLockedTokens(ursula2).call()

    # Ursula's withdrawal attempt won't succeed because everything is locked
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.withdraw(100).transact({'from': ursula1})
        testerchain.wait_for_receipt(tx)
    assert 1500 == token.functions.balanceOf(escrow.address).call()
    assert 9000 == token.functions.balanceOf(ursula1).call()

    # Ursula can deposit more tokens
    tx = escrow.functions.confirmActivity().transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    assert escrow.functions.getCurrentPeriod().call() + 1 == escrow.functions.getLastActivePeriod(ursula1).call()
    assert 1000 == escrow.functions.getLockedTokens(ursula1, 1).call()
    assert 0 == escrow.functions.getLockedTokens(ursula1, 2).call()

    events = activity_log.get_all_entries()
    assert 3 == len(events)
    event_args = events[2]['args']
    assert ursula1 == event_args['miner']
    assert escrow.functions.getCurrentPeriod().call() + 1 == event_args['period']
    assert 1000 == event_args['value']

    tx = token.functions.approveAndCall(escrow.address, 500, testerchain.interface.w3.toBytes(2))\
        .transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    assert 2000 == token.functions.balanceOf(escrow.address).call()
    assert 8500 == token.functions.balanceOf(ursula1).call()
    assert 1500 == escrow.functions.getLockedTokens(ursula1, 1).call()
    assert 500 == escrow.functions.getLockedTokens(ursula1, 2).call()
    assert 0 == escrow.functions.getLockedTokens(ursula1, 3).call()

    events = activity_log.get_all_entries()
    assert 4 == len(events)
    event_args = events[3]['args']
    assert ursula1 == event_args['miner']
    assert escrow.functions.getCurrentPeriod().call() + 1 == event_args['period']
    assert 500 == event_args['value']

    # But can't deposit too high value (more than _maxAllowableLockedTokens coefficient)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.deposit(100, 2).transact({'from': ursula1})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = token.functions.approveAndCall(escrow.address, 100, testerchain.interface.w3.toBytes(2))\
            .transact({'from': ursula1})
        testerchain.wait_for_receipt(tx)

    # Wait 1 period and checks locking
    testerchain.time_travel(hours=1)
    assert 1500 == escrow.functions.getLockedTokens(ursula1).call()

    # Confirm activity and wait 1 period, locking will be decreased because of end of one stake
    tx = escrow.functions.confirmActivity().transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    testerchain.time_travel(hours=1)
    assert 500 == escrow.functions.getLockedTokens(ursula1).call()
    assert 0 == escrow.functions.getLockedTokens(ursula1, 1).call()

    events = activity_log.get_all_entries()
    assert 5 == len(events)
    event_args = events[4]['args']
    assert ursula1 == event_args['miner']
    assert escrow.functions.getCurrentPeriod().call() == event_args['period']
    assert 500 == event_args['value']

    # Stake is unlocked and Ursula can withdraw some tokens
    tx = escrow.functions.withdraw(100).transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    assert 1900 == token.functions.balanceOf(escrow.address).call()
    assert 8600 == token.functions.balanceOf(ursula1).call()
    events = withdraw_log.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert ursula1 == event_args['miner']
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
    tx = token.functions.approveAndCall(escrow.address, 500, testerchain.interface.w3.toBytes(2))\
        .transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)

    events = activity_log.get_all_entries()
    assert 6 == len(events)
    event_args = events[5]['args']
    assert ursula1 == event_args['miner']
    assert escrow.functions.getCurrentPeriod().call() + 1 == event_args['period']
    assert 500 == event_args['value']

    tx = escrow.functions.lock(100, 2).transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)

    events = activity_log.get_all_entries()
    assert 7 == len(events)
    event_args = events[6]['args']
    assert ursula1 == event_args['miner']
    assert escrow.functions.getCurrentPeriod().call() + 1 == event_args['period']
    assert 100 == event_args['value']

    # Value of locked tokens will be updated in next period
    assert 500 == escrow.functions.getLockedTokens(ursula1).call()
    assert 600 == escrow.functions.getLockedTokens(ursula1, 1).call()
    assert 600 == escrow.functions.getLockedTokens(ursula1, 2).call()
    assert 0 == escrow.functions.getLockedTokens(ursula1, 3).call()
    testerchain.time_travel(hours=1)
    assert 600 == escrow.functions.getLockedTokens(ursula1).call()
    assert 600 == escrow.functions.getLockedTokens(ursula1, 1).call()
    assert 0 == escrow.functions.getLockedTokens(ursula1, 2).call()

    # Ursula increases lock
    tx = escrow.functions.lock(500, 2).transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    assert 600 == escrow.functions.getLockedTokens(ursula1).call()
    assert 1100 == escrow.functions.getLockedTokens(ursula1, 1).call()
    assert 500 == escrow.functions.getLockedTokens(ursula1, 2).call()
    assert 0 == escrow.functions.getLockedTokens(ursula1, 3).call()
    testerchain.time_travel(hours=1)
    assert 1100 == escrow.functions.getLockedTokens(ursula1).call()

    # Ursula(2) increases lock by deposit more tokens using approveAndCall
    tx = token.functions.approveAndCall(escrow.address, 500, testerchain.interface.w3.toBytes(2))\
        .transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    assert 500 == escrow.functions.getLockedTokens(ursula2).call()
    assert 1000 == escrow.functions.getLockedTokens(ursula2, 1).call()
    assert 500 == escrow.functions.getLockedTokens(ursula2, 2).call()
    assert 0 == escrow.functions.getLockedTokens(ursula2, 3).call()
    testerchain.time_travel(hours=1)

    # And increases locked time by dividing stake into two parts
    period = escrow.functions.getCurrentPeriod().call()
    assert 2 == escrow.functions.getStakesLength(ursula2).call()
    assert period + 1 == escrow.functions.getLastPeriodOfStake(ursula2, 1).call()
    tx = escrow.functions.divideStake(1, 200, 1).transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    assert 1000 == escrow.functions.getLockedTokens(ursula2).call()
    assert 500 == escrow.functions.getLockedTokens(ursula2, 1).call()
    assert 200 == escrow.functions.getLockedTokens(ursula2, 2).call()
    assert 0 == escrow.functions.getLockedTokens(ursula2, 3).call()

    events = lock_log.get_all_entries()
    assert 8 == len(events)
    event_args = events[7]['args']
    assert ursula2 == event_args['miner']
    assert 200 == event_args['value']
    assert period == event_args['firstPeriod']
    assert 2 == event_args['periods']
    events = divides_log.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert ursula2 == event_args['miner']
    assert 500 == event_args['oldValue']
    assert period + 1 == event_args['lastPeriod']
    assert 200 == event_args['newValue']
    assert 1 == event_args['periods']

    tx = escrow.functions.confirmActivity().transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    testerchain.time_travel(hours=1)
    # Check number of stakes and last stake parameters
    period = escrow.functions.getCurrentPeriod().call()
    assert 3 == escrow.functions.getStakesLength(ursula2).call()
    assert period == escrow.functions.getLastPeriodOfStake(ursula2, 1).call()

    # Divide stake again
    tx = escrow.functions.divideStake(1, 200, 2).transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    assert 500 == escrow.functions.getLockedTokens(ursula2).call()
    assert 400 == escrow.functions.getLockedTokens(ursula2, 1).call()
    assert 200 == escrow.functions.getLockedTokens(ursula2, 2).call()
    assert 0 == escrow.functions.getLockedTokens(ursula2, 3).call()

    events = divides_log.get_all_entries()
    assert 2 == len(events)
    event_args = events[1]['args']
    assert ursula2 == event_args['miner']
    assert 300 == event_args['oldValue']
    assert period == event_args['lastPeriod']
    assert 200 == event_args['newValue']
    assert 2 == event_args['periods']

    # Check number of stakes and last stake parameters
    assert 4 == escrow.functions.getStakesLength(ursula2).call()
    assert period + 1 == escrow.functions.getLastPeriodOfStake(ursula2, 2).call()

    # Divide stake again
    tx = escrow.functions.divideStake(2, 100, 2).transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    assert 500 == escrow.functions.getLockedTokens(ursula2).call()
    assert 400 == escrow.functions.getLockedTokens(ursula2, 1).call()
    assert 300 == escrow.functions.getLockedTokens(ursula2, 2).call()
    assert 100 == escrow.functions.getLockedTokens(ursula2, 3).call()
    assert 0 == escrow.functions.getLockedTokens(ursula2, 4).call()

    events = divides_log.get_all_entries()
    assert 3 == len(events)
    event_args = events[2]['args']
    assert ursula2 == event_args['miner']
    assert 200 == event_args['oldValue']
    assert period + 1 == event_args['lastPeriod']
    assert 100 == event_args['newValue']
    assert 2 == event_args['periods']

    # Just wait and confirm activity
    tx = escrow.functions.confirmActivity().transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    testerchain.time_travel(hours=1)
    tx = escrow.functions.confirmActivity().transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    testerchain.time_travel(hours=1)
    tx = escrow.functions.confirmActivity().transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)

    # Can't divide old stake because it's already unlocked
    period = escrow.functions.getCurrentPeriod().call()
    with pytest.raises((TransactionFailed, ValueError)):
        tx = escrow.functions.divideStake(0, 200, 10).transact({'from': ursula2})
        testerchain.wait_for_receipt(tx)

    assert 5 == escrow.functions.getStakesLength(ursula2).call()
    assert period == escrow.functions.getLastPeriodOfStake(ursula2, 3).call()
    tx = escrow.functions.divideStake(3, 100, 1).transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)

    events = divides_log.get_all_entries()
    assert 4 == len(events)
    event_args = events[3]['args']
    assert ursula2 == event_args['miner']
    assert 200 == event_args['oldValue']
    assert period == event_args['lastPeriod']
    assert 100 == event_args['newValue']
    assert 1 == event_args['periods']

    events = activity_log.get_all_entries()
    assert 14 == len(events)
    event_args = events[11]['args']
    assert ursula2 == event_args['miner']
    assert escrow.functions.getCurrentPeriod().call() == event_args['period']
    assert 300 == event_args['value']
    event_args = events[12]['args']
    assert ursula2 == event_args['miner']
    assert escrow.functions.getCurrentPeriod().call() + 1 == event_args['period']
    assert 100 == event_args['value']
    event_args = events[13]['args']
    assert ursula2 == event_args['miner']
    assert escrow.functions.getCurrentPeriod().call() + 1 == event_args['period']
    assert 100 == event_args['value']

    assert 5 == len(deposit_log.get_all_entries())
    assert 11 == len(lock_log.get_all_entries())
    assert 1 == len(withdraw_log.get_all_entries())
