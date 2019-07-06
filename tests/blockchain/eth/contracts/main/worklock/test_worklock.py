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


@pytest.mark.slow
def test_worklock(testerchain, token_economics):
    creator, ursula1, ursula2, *everyone_else = testerchain.w3.eth.accounts

    # Create an ERC20 token
    token, _ = testerchain.deploy_contract('NuCypherToken', _totalSupply=token_economics.erc20_total_supply)

    # Deploy MinersEscrow mock
    escrow, _ = testerchain.deploy_contract(
        contract_name='StakingEscrowForWorkLockMock',
        _token=token.address,
        _minAllowableLockedTokens=token_economics.minimum_allowed_locked,
        _maxAllowableLockedTokens=token_economics.maximum_allowed_locked,
        _minLockedPeriods=token_economics.minimum_locked_periods
    )

    # Deploy WorkLock
    now = testerchain.w3.eth.getBlock(block_identifier='latest').timestamp
    start_bid_date = now + (60 * 60)  # 1 Hour
    end_bid_date = start_bid_date + (60 * 60)
    deposit_rate = 100
    refund_rate = 200
    worklock, _ = testerchain.deploy_contract(
        contract_name='WorkLock',
        _token=token.address,
        _escrow=escrow.address,
        _startBidDate=start_bid_date,
        _endBidDate=end_bid_date,
        _depositRate=deposit_rate,
        _refundRate=refund_rate,
        _lockedPeriods=2 * token_economics.minimum_locked_periods
    )
    assert worklock.functions.startBidDate().call() == start_bid_date
    assert worklock.functions.endBidDate().call() == end_bid_date
    assert worklock.functions.minAllowableLockedTokens().call() == token_economics.minimum_allowed_locked
    assert worklock.functions.maxAllowableLockedTokens().call() == token_economics.maximum_allowed_locked
    assert worklock.functions.depositRate().call() == deposit_rate
    assert worklock.functions.refundRate().call() == refund_rate

    bidding_log = worklock.events.Bid.createFilter(fromBlock='latest')
    claim_log = worklock.events.Claimed.createFilter(fromBlock='latest')
    refund_log = worklock.events.Refund.createFilter(fromBlock='latest')

    # Transfer tokens to WorkLock
    worklock_supply = 2 * token_economics.maximum_allowed_locked - 1
    tx = token.functions.transfer(worklock.address, worklock_supply).transact({'from': creator})
    testerchain.wait_for_receipt(tx)

    # Give Ursulas some ETH
    minimum_deposit_eth = token_economics.minimum_allowed_locked // deposit_rate
    maximum_deposit_eth = token_economics.maximum_allowed_locked // deposit_rate
    ursula1_balance = 2 * maximum_deposit_eth
    tx = testerchain.w3.eth.sendTransaction(
        {'from': testerchain.etherbase_account, 'to': ursula1, 'value': ursula1_balance})
    testerchain.wait_for_receipt(tx)
    ursula2_balance = 2 * maximum_deposit_eth
    tx = testerchain.w3.eth.sendTransaction(
        {'from': testerchain.etherbase_account, 'to': ursula2, 'value': ursula2_balance})
    testerchain.wait_for_receipt(tx)

    # Can't do anything before start date
    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.bid().transact({'from': ursula1, 'value': minimum_deposit_eth, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.claim().transact({'from': ursula1, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.refund().transact({'from': ursula1, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)

    # Wait for the start of bidding
    testerchain.time_travel(seconds=3600)  # Wait exactly 1 hour

    # Can't bid with too low or too high ETH
    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.bid().transact({'from': ursula1, 'value': minimum_deposit_eth - 1, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.bid().transact({'from': ursula1, 'value': maximum_deposit_eth + 1, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)

    # Ursula does first bid
    assert worklock.functions.allClaimedTokens().call() == 0
    assert worklock.functions.workInfo(ursula1).call()[0] == 0
    assert testerchain.w3.eth.getBalance(worklock.address) == 0
    tx = worklock.functions.bid().transact({'from': ursula1, 'value': minimum_deposit_eth, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert worklock.functions.allClaimedTokens().call() == token_economics.minimum_allowed_locked
    assert worklock.functions.workInfo(ursula1).call()[0] == minimum_deposit_eth
    assert testerchain.w3.eth.getBalance(worklock.address) == minimum_deposit_eth

    events = bidding_log.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert event_args['staker'] == ursula1
    assert event_args['depositedETH'] == minimum_deposit_eth
    assert event_args['claimedTokens'] == token_economics.minimum_allowed_locked

    # Second Ursula does first bid
    assert worklock.functions.workInfo(ursula2).call()[0] == 0
    tx = worklock.functions.bid().transact({'from': ursula2, 'value': maximum_deposit_eth, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert worklock.functions.allClaimedTokens().call() == \
           token_economics.minimum_allowed_locked + token_economics.maximum_allowed_locked
    assert worklock.functions.workInfo(ursula2).call()[0] == maximum_deposit_eth
    assert testerchain.w3.eth.getBalance(worklock.address) == maximum_deposit_eth + minimum_deposit_eth

    events = bidding_log.get_all_entries()
    assert 2 == len(events)
    event_args = events[1]['args']
    assert event_args['staker'] == ursula2
    assert event_args['depositedETH'] == maximum_deposit_eth
    assert event_args['claimedTokens'] == token_economics.maximum_allowed_locked

    # Can't bid again with too high ETH
    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.bid().transact(
            {'from': ursula1, 'value': maximum_deposit_eth-minimum_deposit_eth+1, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.bid().transact({'from': ursula2, 'value': 1, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)

    # Ursula does second bid
    tx = worklock.functions.bid().transact({'from': ursula1, 'value': minimum_deposit_eth, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert worklock.functions.allClaimedTokens().call() == \
           2 * token_economics.minimum_allowed_locked + token_economics.maximum_allowed_locked
    assert worklock.functions.workInfo(ursula1).call()[0] == 2 * minimum_deposit_eth
    assert testerchain.w3.eth.getBalance(worklock.address) == maximum_deposit_eth + 2 * minimum_deposit_eth

    events = bidding_log.get_all_entries()
    assert 3 == len(events)
    event_args = events[2]['args']
    assert event_args['staker'] == ursula1
    assert event_args['depositedETH'] == minimum_deposit_eth
    assert event_args['claimedTokens'] == token_economics.minimum_allowed_locked

    # Can't bid again: not enough tokens in worklock
    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.bid().transact(
            {'from': ursula1, 'value': maximum_deposit_eth - 2 * minimum_deposit_eth, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)

    # Can't claim or refund while bidding phase
    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.claim().transact({'from': ursula1, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.refund().transact({'from': ursula1, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)

    # Wait for the end of bidding
    testerchain.time_travel(seconds=3600)  # Wait exactly 1 hour

    # Can't bid after the enf of bidding
    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.bid().transact({'from': ursula1, 'value': minimum_deposit_eth, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)

    # Can't refund without claim
    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.refund().transact({'from': ursula1, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)

    # Ursula claims tokens
    value, measure_work, _work_done, periods = escrow.functions.stakerInfo(ursula1).call()
    assert value == 0
    assert not measure_work
    assert periods == 0
    tx = worklock.functions.claim().transact({'from': ursula1, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert worklock.functions.getRemainingWork(ursula1).call() == 2 * minimum_deposit_eth * refund_rate
    value, measure_work, work_done, periods = escrow.functions.stakerInfo(ursula1).call()
    assert value == 2 * token_economics.minimum_allowed_locked
    assert measure_work
    assert periods == 2 * token_economics.minimum_locked_periods
    assert token.functions.balanceOf(worklock.address).call() == \
           worklock_supply - 2 * token_economics.minimum_allowed_locked
    assert token.functions.balanceOf(escrow.address).call() == 2 * token_economics.minimum_allowed_locked

    events = claim_log.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert event_args['staker'] == ursula1
    assert event_args['claimedTokens'] == 2 * token_economics.minimum_allowed_locked

    # Can't claim more than once
    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.claim().transact({'from': ursula1, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)

    # Can't refund without work
    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.refund().transact({'from': ursula1, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)

    # Second Ursula claims tokens
    value, measure_work, _work_done, periods = escrow.functions.stakerInfo(ursula2).call()
    assert value == 0
    assert not measure_work
    assert periods == 0
    tx = escrow.functions.setWorkDone(ursula2, refund_rate * minimum_deposit_eth).transact()
    testerchain.wait_for_receipt(tx)
    tx = worklock.functions.claim().transact({'from': ursula2, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert worklock.functions.getRemainingWork(ursula2).call() == maximum_deposit_eth * refund_rate
    value, measure_work, work_done, periods = escrow.functions.stakerInfo(ursula2).call()
    assert value == token_economics.maximum_allowed_locked
    assert measure_work
    assert periods == 2 * token_economics.minimum_locked_periods
    assert token.functions.balanceOf(worklock.address).call() == \
           worklock_supply - 2 * token_economics.minimum_allowed_locked - token_economics.maximum_allowed_locked
    assert token.functions.balanceOf(escrow.address).call() == \
           2 * token_economics.minimum_allowed_locked + token_economics.maximum_allowed_locked

    events = claim_log.get_all_entries()
    assert 2 == len(events)
    event_args = events[1]['args']
    assert event_args['staker'] == ursula2
    assert event_args['claimedTokens'] == token_economics.maximum_allowed_locked

    # "Do" some work and partial refund
    ursula1_balance = testerchain.w3.eth.getBalance(ursula1)
    work_done = refund_rate * minimum_deposit_eth + refund_rate // 2
    tx = escrow.functions.setWorkDone(ursula1, work_done).transact()
    testerchain.wait_for_receipt(tx)
    assert worklock.functions.getRemainingWork(ursula1).call() == minimum_deposit_eth * refund_rate - refund_rate // 2
    tx = worklock.functions.refund().transact({'from': ursula1, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert worklock.functions.workInfo(ursula1).call()[0] == minimum_deposit_eth
    assert worklock.functions.getRemainingWork(ursula1).call() == minimum_deposit_eth * refund_rate - refund_rate // 2
    assert testerchain.w3.eth.getBalance(ursula1) == ursula1_balance + minimum_deposit_eth
    assert testerchain.w3.eth.getBalance(worklock.address) == maximum_deposit_eth + minimum_deposit_eth
    _value, measure_work, _work_done, _periods = escrow.functions.stakerInfo(ursula1).call()
    assert measure_work

    events = refund_log.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert event_args['staker'] == ursula1
    assert event_args['refundETH'] == minimum_deposit_eth
    assert event_args['workDone'] == minimum_deposit_eth * refund_rate

    # "Do" more work and full refund
    ursula1_balance = testerchain.w3.eth.getBalance(ursula1)
    work_done = refund_rate * 2 * minimum_deposit_eth
    tx = escrow.functions.setWorkDone(ursula1, work_done).transact()
    testerchain.wait_for_receipt(tx)
    assert worklock.functions.getRemainingWork(ursula1).call() == 0
    tx = worklock.functions.refund().transact({'from': ursula1, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert worklock.functions.workInfo(ursula1).call()[0] == 0
    assert worklock.functions.getRemainingWork(ursula1).call() == 0
    assert testerchain.w3.eth.getBalance(ursula1) == ursula1_balance + minimum_deposit_eth
    assert testerchain.w3.eth.getBalance(worklock.address) == maximum_deposit_eth
    _value, measure_work, _work_done, _periods = escrow.functions.stakerInfo(ursula1).call()
    assert not measure_work

    events = refund_log.get_all_entries()
    assert 2 == len(events)
    event_args = events[1]['args']
    assert event_args['staker'] == ursula1
    assert event_args['refundETH'] == minimum_deposit_eth
    assert event_args['workDone'] == minimum_deposit_eth * refund_rate

    # Can't refund more tokens
    tx = escrow.functions.setWorkDone(ursula1, 2 * work_done).transact()
    testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.refund().transact({'from': ursula1, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)
