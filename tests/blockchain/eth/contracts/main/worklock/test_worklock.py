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
from eth_utils import to_wei


@pytest.fixture()
def token(testerchain, token_economics, deploy_contract):
    contract, _ = deploy_contract('NuCypherToken', _totalSupplyOfTokens=token_economics.erc20_total_supply)
    return contract


@pytest.fixture()
def escrow(testerchain, token_economics, deploy_contract, token):
    contract, _ = deploy_contract(
        contract_name='StakingEscrowForWorkLockMock',
        _token=token.address,
        _minAllowableLockedTokens=token_economics.minimum_allowed_locked,
        _maxAllowableLockedTokens=token_economics.maximum_allowed_locked,
        _minLockedPeriods=token_economics.minimum_locked_periods
    )
    return contract


@pytest.mark.slow
def test_worklock(testerchain, token_economics, deploy_contract, token, escrow):
    creator, staker1, staker2, staker3, *everyone_else = testerchain.w3.eth.accounts

    # Deploy WorkLock
    now = testerchain.w3.eth.getBlock(block_identifier='latest').timestamp
    start_bid_date = now + (60 * 60)  # 1 Hour
    end_bid_date = start_bid_date + (60 * 60)
    boosting_refund = 50
    slowing_refund = 100
    staking_periods = 2 * token_economics.minimum_locked_periods
    worklock, _ = deploy_contract(
        contract_name='WorkLock',
        _token=token.address,
        _escrow=escrow.address,
        _startBidDate=start_bid_date,
        _endBidDate=end_bid_date,
        _boostingRefund=boosting_refund,
        _stakingPeriods=staking_periods
    )
    assert worklock.functions.startBidDate().call() == start_bid_date
    assert worklock.functions.endBidDate().call() == end_bid_date
    assert worklock.functions.boostingRefund().call() == boosting_refund
    assert worklock.functions.SLOWING_REFUND().call() == slowing_refund
    assert worklock.functions.stakingPeriods().call() == staking_periods

    deposit_log = worklock.events.Deposited.createFilter(fromBlock='latest')
    bidding_log = worklock.events.Bid.createFilter(fromBlock='latest')
    claim_log = worklock.events.Claimed.createFilter(fromBlock='latest')
    refund_log = worklock.events.Refund.createFilter(fromBlock='latest')
    burning_log = worklock.events.Burnt.createFilter(fromBlock='latest')
    canceling_log = worklock.events.Canceled.createFilter(fromBlock='latest')

    # Transfer tokens to WorkLock
    worklock_supply_1 = 2 * token_economics.maximum_allowed_locked + 1
    worklock_supply_2 = token_economics.maximum_allowed_locked - 1
    worklock_supply = worklock_supply_1 + worklock_supply_2
    tx = token.functions.approve(worklock.address, worklock_supply).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    tx = worklock.functions.tokenDeposit(worklock_supply_1).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert worklock.functions.tokenSupply().call() == worklock_supply_1
    tx = worklock.functions.tokenDeposit(worklock_supply_2).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert worklock.functions.tokenSupply().call() == worklock_supply

    events = deposit_log.get_all_entries()
    assert 2 == len(events)
    event_args = events[0]['args']
    assert event_args['sender'] == creator
    assert event_args['value'] == worklock_supply_1
    event_args = events[1]['args']
    assert event_args['sender'] == creator
    assert event_args['value'] == worklock_supply_2

    # Give stakers some ETH
    deposit_eth_1 = to_wei(4, 'ether')
    deposit_eth_2 = deposit_eth_1 // 4
    staker1_balance = 10 * deposit_eth_1
    tx = testerchain.w3.eth.sendTransaction(
        {'from': testerchain.etherbase_account, 'to': staker1, 'value': staker1_balance})
    testerchain.wait_for_receipt(tx)
    staker2_balance = staker1_balance
    tx = testerchain.w3.eth.sendTransaction(
        {'from': testerchain.etherbase_account, 'to': staker2, 'value': staker2_balance})
    testerchain.wait_for_receipt(tx)
    staker3_balance = staker1_balance
    tx = testerchain.w3.eth.sendTransaction(
        {'from': testerchain.etherbase_account, 'to': staker3, 'value': staker3_balance})
    testerchain.wait_for_receipt(tx)

    # Can't do anything before start date
    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.bid().transact({'from': staker1, 'value': deposit_eth_1, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.claim().transact({'from': staker1, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.refund().transact({'from': staker1, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.burnUnclaimed().transact({'from': staker1, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.cancelBid().transact({'from': staker1, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)

    # Wait for the start of bidding
    testerchain.time_travel(seconds=3600)  # Wait exactly 1 hour

    # Staker does first bid
    assert worklock.functions.workInfo(staker1).call()[0] == 0
    assert testerchain.w3.eth.getBalance(worklock.address) == 0
    tx = worklock.functions.bid().transact({'from': staker1, 'value': deposit_eth_1, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert worklock.functions.workInfo(staker1).call()[0] == deposit_eth_1
    assert not worklock.functions.workInfo(staker1).call()[2]
    assert testerchain.w3.eth.getBalance(worklock.address) == deposit_eth_1
    assert worklock.functions.ethToTokens(deposit_eth_1).call() == worklock_supply

    events = bidding_log.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert event_args['sender'] == staker1
    assert event_args['depositedETH'] == deposit_eth_1

    # Second staker does first bid
    assert worklock.functions.workInfo(staker2).call()[0] == 0
    tx = worklock.functions.bid().transact({'from': staker2, 'value': deposit_eth_2, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert worklock.functions.workInfo(staker2).call()[0] == deposit_eth_2
    assert not worklock.functions.workInfo(staker2).call()[2]
    assert testerchain.w3.eth.getBalance(worklock.address) == deposit_eth_1 + deposit_eth_2
    assert worklock.functions.ethToTokens(deposit_eth_2).call() == worklock_supply // 5

    events = bidding_log.get_all_entries()
    assert 2 == len(events)
    event_args = events[1]['args']
    assert event_args['sender'] == staker2
    assert event_args['depositedETH'] == deposit_eth_2

    # Third staker does first bid
    assert worklock.functions.workInfo(staker3).call()[0] == 0
    tx = worklock.functions.bid().transact({'from': staker3, 'value': deposit_eth_2, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert worklock.functions.workInfo(staker3).call()[0] == deposit_eth_2
    assert testerchain.w3.eth.getBalance(worklock.address) == deposit_eth_1 + 2 * deposit_eth_2
    assert worklock.functions.ethToTokens(deposit_eth_2).call() == worklock_supply // 6

    events = bidding_log.get_all_entries()
    assert 3 == len(events)
    event_args = events[2]['args']
    assert event_args['sender'] == staker3
    assert event_args['depositedETH'] == deposit_eth_2

    # Staker does second bid
    tx = worklock.functions.bid().transact({'from': staker1, 'value': deposit_eth_1, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert worklock.functions.workInfo(staker1).call()[0] == 2 * deposit_eth_1
    assert testerchain.w3.eth.getBalance(worklock.address) == 2 * deposit_eth_1 + 2 * deposit_eth_2
    assert worklock.functions.ethToTokens(deposit_eth_2).call() == worklock_supply // 10

    events = bidding_log.get_all_entries()
    assert 4 == len(events)
    event_args = events[3]['args']
    assert event_args['sender'] == staker1
    assert event_args['depositedETH'] == deposit_eth_1

    # Can't claim, refund or burn while bidding phase
    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.claim().transact({'from': staker1, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.refund().transact({'from': staker1, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.burnUnclaimed().transact({'from': staker1, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)

    # But can cancel bid
    staker3_balance = testerchain.w3.eth.getBalance(staker3)
    tx = worklock.functions.cancelBid().transact({'from': staker3, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert worklock.functions.workInfo(staker3).call()[0] == 0
    assert testerchain.w3.eth.getBalance(worklock.address) == 2 * deposit_eth_1 + deposit_eth_2
    assert worklock.functions.ethToTokens(deposit_eth_2).call() == worklock_supply // 9
    assert testerchain.w3.eth.getBalance(staker3) == staker3_balance + deposit_eth_2

    events = canceling_log.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert event_args['sender'] == staker3
    assert event_args['value'] == deposit_eth_2

    # Can't cancel twice in a row
    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.cancelBid().transact({'from': staker3, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)

    # Third staker does second bid
    assert worklock.functions.workInfo(staker3).call()[0] == 0
    tx = worklock.functions.bid().transact({'from': staker3, 'value': deposit_eth_2, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert worklock.functions.workInfo(staker3).call()[0] == deposit_eth_2
    assert testerchain.w3.eth.getBalance(worklock.address) == 2 * deposit_eth_1 + 2 * deposit_eth_2
    assert worklock.functions.ethToTokens(deposit_eth_2).call() == worklock_supply // 10

    events = bidding_log.get_all_entries()
    assert 5 == len(events)
    event_args = events[4]['args']
    assert event_args['sender'] == staker3
    assert event_args['depositedETH'] == deposit_eth_2

    # Wait for the end of bidding
    testerchain.time_travel(seconds=3600)  # Wait exactly 1 hour

    # Can't bid after the end of bidding
    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.bid().transact({'from': staker1, 'value': deposit_eth_1, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)
    # Can't refund without claim
    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.refund().transact({'from': staker1, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)

    # Staker claims tokens
    value, measure_work, _completed_work, periods = escrow.functions.stakerInfo(staker1).call()
    assert not measure_work
    assert value == 0
    assert periods == 0
    assert not worklock.functions.workInfo(staker1).call()[2]
    tx = worklock.functions.claim().transact({'from': staker1, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert worklock.functions.workInfo(staker1).call()[2]
    staker1_tokens = 8 * worklock_supply // 10
    assert token.functions.balanceOf(staker1).call() == 0
    staker1_remaining_work = int(-(-8 * worklock_supply * slowing_refund // (boosting_refund * 10)))  # div ceil
    assert worklock.functions.ethToWork(2 * deposit_eth_1).call() == staker1_remaining_work
    assert worklock.functions.workToETH(staker1_remaining_work).call() == 2 * deposit_eth_1
    assert worklock.functions.getRemainingWork(staker1).call() == staker1_remaining_work
    assert token.functions.balanceOf(worklock.address).call() == worklock_supply - staker1_tokens
    value, measure_work, _completed_work, periods = escrow.functions.stakerInfo(staker1).call()
    assert measure_work
    assert value == staker1_tokens
    assert periods == staking_periods

    events = claim_log.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert event_args['sender'] == staker1
    assert event_args['claimedTokens'] == staker1_tokens

    # Can't claim more than once
    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.claim().transact({'from': staker1, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)
    # Can't refund without work
    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.refund().transact({'from': staker1, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)
    # Can't cancel after claim
    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.cancelBid().transact({'from': staker1, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)

    # One of stakers cancel bid
    staker3_balance = testerchain.w3.eth.getBalance(staker3)
    staker3_tokens = worklock_supply // 10
    assert worklock.functions.ethToTokens(deposit_eth_2).call() == staker3_tokens
    tx = worklock.functions.cancelBid().transact({'from': staker3, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert worklock.functions.ethToTokens(deposit_eth_2).call() == staker3_tokens
    assert worklock.functions.workInfo(staker3).call()[0] == 0
    assert testerchain.w3.eth.getBalance(worklock.address) == 2 * deposit_eth_1 + deposit_eth_2
    assert testerchain.w3.eth.getBalance(staker3) == staker3_balance + deposit_eth_2
    assert worklock.functions.unclaimedTokens().call() == staker3_tokens
    assert token.functions.balanceOf(worklock.address).call() == worklock_supply - staker1_tokens

    # Second staker claims tokens
    value, measure_work, _completed_work, periods = escrow.functions.stakerInfo(staker2).call()
    assert not measure_work
    assert value == 0
    assert periods == 0
    staker2_tokens = staker3_tokens
    # staker2_tokens * slowing_refund / boosting_refund
    staker2_remaining_work = int(-(-worklock_supply * slowing_refund // (boosting_refund * 10)))  # div ceil
    assert worklock.functions.ethToWork(deposit_eth_2).call() == staker2_remaining_work
    assert worklock.functions.workToETH(staker2_remaining_work).call() == deposit_eth_2
    tx = escrow.functions.setCompletedWork(staker2, staker2_remaining_work // 2).transact()
    testerchain.wait_for_receipt(tx)
    assert not worklock.functions.workInfo(staker2).call()[2]
    tx = worklock.functions.claim().transact({'from': staker2, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert worklock.functions.workInfo(staker2).call()[2]
    assert worklock.functions.getRemainingWork(staker2).call() == staker2_remaining_work
    assert token.functions.balanceOf(worklock.address).call() == worklock_supply - staker1_tokens - staker2_tokens
    assert token.functions.balanceOf(staker2).call() == 0
    value, measure_work, _completed_work, periods = escrow.functions.stakerInfo(staker2).call()
    assert measure_work
    assert value == staker2_tokens
    assert periods == staking_periods

    events = claim_log.get_all_entries()
    assert 2 == len(events)
    event_args = events[1]['args']
    assert event_args['sender'] == staker2
    assert event_args['claimedTokens'] == staker2_tokens

    # "Do" some work and partial refund
    staker1_balance = testerchain.w3.eth.getBalance(staker1)
    completed_work = staker1_remaining_work // 2 + 1
    remaining_work = staker1_remaining_work - completed_work
    tx = escrow.functions.setCompletedWork(staker1, completed_work).transact()
    testerchain.wait_for_receipt(tx)
    assert worklock.functions.getRemainingWork(staker1).call() == remaining_work

    tx = worklock.functions.refund().transact({'from': staker1, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert worklock.functions.workInfo(staker1).call()[0] == deposit_eth_1
    assert worklock.functions.getRemainingWork(staker1).call() == remaining_work
    assert testerchain.w3.eth.getBalance(staker1) == staker1_balance + deposit_eth_1
    assert testerchain.w3.eth.getBalance(worklock.address) == deposit_eth_1 + deposit_eth_2
    _value, measure_work, _completed_work, _periods = escrow.functions.stakerInfo(staker1).call()
    assert measure_work

    events = refund_log.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert event_args['sender'] == staker1
    assert event_args['refundETH'] == deposit_eth_1
    assert event_args['completedWork'] == staker1_remaining_work // 2

    # "Do" more work and full refund
    staker1_balance = testerchain.w3.eth.getBalance(staker1)
    completed_work = staker1_remaining_work
    tx = escrow.functions.setCompletedWork(staker1, completed_work).transact()
    testerchain.wait_for_receipt(tx)
    assert worklock.functions.getRemainingWork(staker1).call() == 0

    tx = worklock.functions.refund().transact({'from': staker1, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert worklock.functions.workInfo(staker1).call()[0] == 0
    assert worklock.functions.getRemainingWork(staker1).call() == 0
    assert testerchain.w3.eth.getBalance(staker1) == staker1_balance + deposit_eth_1
    assert testerchain.w3.eth.getBalance(worklock.address) == deposit_eth_2
    _value, measure_work, _completed_work, _periods = escrow.functions.stakerInfo(staker1).call()
    assert not measure_work

    events = refund_log.get_all_entries()
    assert 2 == len(events)
    event_args = events[1]['args']
    assert event_args['sender'] == staker1
    assert event_args['refundETH'] == deposit_eth_1
    assert event_args['completedWork'] == staker1_remaining_work // 2

    # Can't refund more tokens
    tx = escrow.functions.setCompletedWork(staker1, 2 * completed_work).transact()
    testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.refund().transact({'from': staker1, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)

    # Now burn remaining tokens
    escrow_tokens = token.functions.balanceOf(escrow.address).call()
    assert worklock.functions.unclaimedTokens().call() == staker3_tokens
    tx = worklock.functions.burnUnclaimed().transact({'from': staker1, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert worklock.functions.unclaimedTokens().call() == 0
    assert token.functions.balanceOf(worklock.address).call() == 0
    assert token.functions.balanceOf(escrow.address).call() == escrow_tokens + staker3_tokens

    # Can't burn twice
    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.burnUnclaimed().transact({'from': staker1, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)

    events = burning_log.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert event_args['sender'] == staker1
    assert event_args['value'] == staker3_tokens


@pytest.mark.slow
def test_reentrancy(testerchain, token_economics, deploy_contract, token, escrow):
    # Deploy WorkLock
    now = testerchain.w3.eth.getBlock(block_identifier='latest').timestamp
    start_bid_date = now
    end_bid_date = start_bid_date + (60 * 60)
    boosting_refund = 100
    staking_periods = token_economics.minimum_locked_periods
    worklock, _ = deploy_contract(
        contract_name='WorkLock',
        _token=token.address,
        _escrow=escrow.address,
        _startBidDate=start_bid_date,
        _endBidDate=end_bid_date,
        _boostingRefund=boosting_refund,
        _stakingPeriods=staking_periods
    )
    refund_log = worklock.events.Refund.createFilter(fromBlock='latest')
    canceling_log = worklock.events.Canceled.createFilter(fromBlock='latest')
    worklock_supply = 3 * token_economics.maximum_allowed_locked
    tx = token.functions.approve(worklock.address, worklock_supply).transact()
    testerchain.wait_for_receipt(tx)
    tx = worklock.functions.tokenDeposit(worklock_supply).transact()
    testerchain.wait_for_receipt(tx)

    reentrancy_contract, _ = deploy_contract('ReentrancyTest')
    contract_address = reentrancy_contract.address
    deposit_eth = to_wei(3, 'ether')
    tx = testerchain.client.send_transaction(
        {'from': testerchain.etherbase_account, 'to': contract_address, 'value': deposit_eth})
    testerchain.wait_for_receipt(tx)

    # Bid
    transaction = worklock.functions.bid().buildTransaction({'gas': 0})
    tx = reentrancy_contract.functions.setData(1, transaction['to'], deposit_eth, transaction['data']).transact()
    testerchain.wait_for_receipt(tx)
    tx = testerchain.client.send_transaction({'to': contract_address})
    testerchain.wait_for_receipt(tx)
    assert worklock.functions.workInfo(contract_address).call()[0] == deposit_eth
    assert testerchain.w3.eth.getBalance(worklock.address) == deposit_eth
    tx = worklock.functions.bid().transact({'from': testerchain.etherbase_account, 'value': deposit_eth})
    testerchain.wait_for_receipt(tx)

    # Check reentrancy protection when cancelling a bid
    balance = testerchain.w3.eth.getBalance(contract_address)
    transaction = worklock.functions.cancelBid().buildTransaction({'gas': 0})
    tx = reentrancy_contract.functions.setData(2, transaction['to'], 0, transaction['data']).transact()
    testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = testerchain.client.send_transaction({'to': contract_address})
        testerchain.wait_for_receipt(tx)
    assert testerchain.w3.eth.getBalance(contract_address) == balance
    assert worklock.functions.workInfo(contract_address).call()[0] == deposit_eth
    assert len(canceling_log.get_all_entries()) == 0

    # Claim
    testerchain.time_travel(seconds=3600)  # Wait exactly 1 hour
    transaction = worklock.functions.claim().buildTransaction({'gas': 0})
    tx = reentrancy_contract.functions.setData(1, transaction['to'], 0, transaction['data']).transact()
    testerchain.wait_for_receipt(tx)
    tx = testerchain.client.send_transaction({'to': contract_address})
    testerchain.wait_for_receipt(tx)
    assert worklock.functions.getRemainingWork(contract_address).call() == worklock_supply // 2

    # Prepare for refund and check reentrancy protection
    balance = testerchain.w3.eth.getBalance(contract_address)
    completed_work = worklock_supply // 6
    tx = escrow.functions.setCompletedWork(contract_address, completed_work).transact()
    testerchain.wait_for_receipt(tx)
    transaction = worklock.functions.refund().buildTransaction({'gas': 0})
    tx = reentrancy_contract.functions.setData(2, transaction['to'], 0, transaction['data']).transact()
    testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = testerchain.client.send_transaction({'to': contract_address})
        testerchain.wait_for_receipt(tx)
    assert testerchain.w3.eth.getBalance(contract_address) == balance
    assert worklock.functions.workInfo(contract_address).call()[0] == deposit_eth
    assert worklock.functions.getRemainingWork(contract_address).call() == 2 * worklock_supply // 6
    assert len(refund_log.get_all_entries()) == 0
