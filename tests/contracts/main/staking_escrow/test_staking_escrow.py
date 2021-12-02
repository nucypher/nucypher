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
    # tx = token.functions.transfer(staker1, value).transact({'from': creator})
    # testerchain.wait_for_receipt(tx)

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
    # # Can't slash directly using the escrow contract
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
