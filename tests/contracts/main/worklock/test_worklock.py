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
import random

import pytest
from eth_tester.exceptions import TransactionFailed
from eth_utils import to_wei

from nucypher.blockchain.eth.constants import NULL_ADDRESS


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


ONE_HOUR = 60 * 60
BIDDING_DURATION = ONE_HOUR
MIN_ALLOWED_BID = to_wei(1, 'ether')


@pytest.fixture()
def worklock_factory(testerchain, token, escrow, token_economics, deploy_contract):
    def deploy_worklock(supply, bidding_delay, additional_time_to_cancel, boosting_refund):

        now = testerchain.w3.eth.getBlock('latest').timestamp
        start_bid_date = now + bidding_delay
        end_bid_date = start_bid_date + BIDDING_DURATION
        end_cancellation_date = end_bid_date + additional_time_to_cancel
        staking_periods = 2 * token_economics.minimum_locked_periods

        contract, _ = deploy_contract(
            contract_name='WorkLock',
            _token=token.address,
            _escrow=escrow.address,
            _startBidDate=start_bid_date,
            _endBidDate=end_bid_date,
            _endCancellationDate=end_cancellation_date,
            _boostingRefund=boosting_refund,
            _stakingPeriods=staking_periods,
            _minAllowedBid=MIN_ALLOWED_BID
        )

        if supply > 0:
            tx = token.functions.approve(contract.address, supply).transact()
            testerchain.wait_for_receipt(tx)
            tx = contract.functions.tokenDeposit(supply).transact()
            testerchain.wait_for_receipt(tx)

        return contract
    return deploy_worklock


def do_bids(testerchain, worklock, bidders, amount):
    for bidder in bidders:
        tx = testerchain.w3.eth.sendTransaction(
            {'from': testerchain.etherbase_account, 'to': bidder, 'value': amount})
        testerchain.wait_for_receipt(tx)
        tx = worklock.functions.bid().transact({'from': bidder, 'value': amount, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)


def test_worklock(testerchain, token_economics, deploy_contract, token, escrow, worklock_factory):
    creator, staker1, staker2, staker3, staker4, *everyone_else = testerchain.w3.eth.accounts
    gas_to_save_state = 30000

    # Deploy WorkLock
    now = testerchain.get_blocktime()
    start_bid_date = now + ONE_HOUR
    end_bid_date = start_bid_date + ONE_HOUR
    end_cancellation_date = end_bid_date + ONE_HOUR
    slowing_refund = 100
    staking_periods = 2 * token_economics.minimum_locked_periods
    boosting_refund = 50

    worklock = worklock_factory(supply=0,
                                bidding_delay=ONE_HOUR,
                                additional_time_to_cancel=ONE_HOUR,
                                boosting_refund=boosting_refund)

    assert worklock.functions.startBidDate().call() == start_bid_date
    assert worklock.functions.endBidDate().call() == end_bid_date
    assert worklock.functions.endCancellationDate().call() == end_cancellation_date
    assert worklock.functions.boostingRefund().call() == boosting_refund
    assert worklock.functions.SLOWING_REFUND().call() == slowing_refund
    assert worklock.functions.stakingPeriods().call() == staking_periods
    assert worklock.functions.maxAllowableLockedTokens().call() == token_economics.maximum_allowed_locked
    assert worklock.functions.minAllowableLockedTokens().call() == token_economics.minimum_allowed_locked

    deposit_log = worklock.events.Deposited.createFilter(fromBlock='latest')
    bidding_log = worklock.events.Bid.createFilter(fromBlock='latest')
    claim_log = worklock.events.Claimed.createFilter(fromBlock='latest')
    refund_log = worklock.events.Refund.createFilter(fromBlock='latest')
    canceling_log = worklock.events.Canceled.createFilter(fromBlock='latest')
    checks_log = worklock.events.BiddersChecked.createFilter(fromBlock='latest')
    force_refund_log = worklock.events.ForceRefund.createFilter(fromBlock='latest')
    compensation_log = worklock.events.CompensationWithdrawn.createFilter(fromBlock='latest')

    # Transfer tokens to WorkLock
    worklock_supply_1 = token_economics.minimum_allowed_locked
    worklock_supply_2 = 2 * token_economics.maximum_allowed_locked
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
    deposit_eth_1 = 4 * MIN_ALLOWED_BID
    deposit_eth_2 = MIN_ALLOWED_BID
    min_stake = token_economics.minimum_allowed_locked
    max_stake = token_economics.maximum_allowed_locked
    staker1_balance = 100 * deposit_eth_1
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
    staker4_balance = staker1_balance
    tx = testerchain.w3.eth.sendTransaction(
        {'from': testerchain.etherbase_account, 'to': staker4, 'value': staker4_balance})
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
        tx = worklock.functions.cancelBid().transact({'from': staker1, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.verifyBiddingCorrectness(gas_to_save_state).transact()
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.forceRefund([staker1]).transact()
        testerchain.wait_for_receipt(tx)

    # Wait for the start of bidding
    testerchain.time_travel(seconds=ONE_HOUR)
    assert not worklock.functions.isClaimingAvailable().call()

    # Bid must be more than minimum
    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.bid().transact({'from': staker1, 'value': MIN_ALLOWED_BID - 1, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)

    # Staker does first bid
    assert worklock.functions.getBiddersLength().call() == 0
    assert worklock.functions.workInfo(staker2).call()[0] == 0
    assert testerchain.w3.eth.getBalance(worklock.address) == 0
    tx = worklock.functions.bid().transact({'from': staker2, 'value': deposit_eth_2, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert worklock.functions.workInfo(staker2).call()[0] == deposit_eth_2
    assert not worklock.functions.workInfo(staker2).call()[2]
    worklock_balance = deposit_eth_2
    bonus_worklock_supply = worklock_supply - min_stake
    assert testerchain.w3.eth.getBalance(worklock.address) == worklock_balance
    assert worklock.functions.bonusETHSupply().call() == 0
    assert worklock.functions.ethToTokens(MIN_ALLOWED_BID).call() == worklock_supply
    assert worklock.functions.ethToTokens(2 * MIN_ALLOWED_BID).call() == worklock_supply
    assert worklock.functions.getBiddersLength().call() == 1
    assert worklock.functions.bidders(0).call() == staker2
    assert worklock.functions.workInfo(staker2).call()[3] == 0

    events = bidding_log.get_all_entries()
    assert 1 == len(events)
    event_args = events[-1]['args']
    assert event_args['sender'] == staker2
    assert event_args['depositedETH'] == deposit_eth_2

    # Other staker does first bid
    assert worklock.functions.workInfo(staker1).call()[0] == 0
    tx = worklock.functions.bid().transact({'from': staker1, 'value': deposit_eth_1, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    staker1_bid = deposit_eth_1
    assert worklock.functions.workInfo(staker1).call()[0] == staker1_bid
    assert not worklock.functions.workInfo(staker1).call()[2]
    worklock_balance += deposit_eth_1
    bonus_worklock_supply -= min_stake
    assert testerchain.w3.eth.getBalance(worklock.address) == worklock_balance
    assert worklock.functions.bonusETHSupply().call() == worklock_balance - 2 * MIN_ALLOWED_BID
    assert worklock.functions.ethToTokens(staker1_bid).call() == min_stake + bonus_worklock_supply
    assert worklock.functions.ethToTokens(MIN_ALLOWED_BID).call() == min_stake
    assert worklock.functions.ethToTokens(2 * MIN_ALLOWED_BID).call() == min_stake + bonus_worklock_supply // 3
    assert worklock.functions.getBiddersLength().call() == 2
    assert worklock.functions.bidders(1).call() == staker1
    assert worklock.functions.workInfo(staker1).call()[3] == 1

    events = bidding_log.get_all_entries()
    assert 2 == len(events)
    event_args = events[-1]['args']
    assert event_args['sender'] == staker1
    assert event_args['depositedETH'] == deposit_eth_1

    # Third staker does first bid
    assert worklock.functions.workInfo(staker3).call()[0] == 0
    tx = worklock.functions.bid().transact({'from': staker3, 'value': deposit_eth_2, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    staker3_bid = deposit_eth_2
    assert worklock.functions.workInfo(staker3).call()[0] == staker3_bid
    worklock_balance += staker3_bid
    bonus_worklock_supply -= min_stake
    assert testerchain.w3.eth.getBalance(worklock.address) == worklock_balance
    assert worklock.functions.bonusETHSupply().call() == worklock_balance - 3 * MIN_ALLOWED_BID
    assert worklock.functions.ethToTokens(MIN_ALLOWED_BID).call() == min_stake
    assert worklock.functions.ethToTokens(2 * MIN_ALLOWED_BID).call() == min_stake + bonus_worklock_supply // 3
    assert worklock.functions.getBiddersLength().call() == 3
    assert worklock.functions.bidders(2).call() == staker3
    assert worklock.functions.workInfo(staker3).call()[3] == 2

    events = bidding_log.get_all_entries()
    assert 3 == len(events)
    event_args = events[-1]['args']
    assert event_args['sender'] == staker3
    assert event_args['depositedETH'] == deposit_eth_2

    # Forth staker does first bid
    staker4_bid = 2 * deposit_eth_2
    assert worklock.functions.workInfo(staker4).call()[0] == 0
    tx = worklock.functions.bid().transact({'from': staker4, 'value': staker4_bid, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert worklock.functions.workInfo(staker4).call()[0] == staker4_bid
    worklock_balance += staker4_bid
    bonus_worklock_supply -= min_stake
    assert testerchain.w3.eth.getBalance(worklock.address) == worklock_balance
    assert worklock.functions.bonusETHSupply().call() == worklock_balance - 4 * MIN_ALLOWED_BID
    assert worklock.functions.ethToTokens(MIN_ALLOWED_BID).call() == min_stake
    assert worklock.functions.ethToTokens(2 * MIN_ALLOWED_BID).call() == min_stake + bonus_worklock_supply // 4
    assert worklock.functions.getBiddersLength().call() == 4
    assert worklock.functions.bidders(3).call() == staker4
    assert worklock.functions.workInfo(staker4).call()[3] == 3

    events = bidding_log.get_all_entries()
    assert 4 == len(events)
    event_args = events[-1]['args']
    assert event_args['sender'] == staker4
    assert event_args['depositedETH'] == staker4_bid

    # Staker does second bid
    tx = worklock.functions.bid().transact({'from': staker1, 'value': deposit_eth_1, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    staker1_bid += deposit_eth_1
    assert worklock.functions.workInfo(staker1).call()[0] == staker1_bid
    worklock_balance += deposit_eth_1
    assert testerchain.w3.eth.getBalance(worklock.address) == worklock_balance
    assert worklock.functions.bonusETHSupply().call() == worklock_balance - 4 * MIN_ALLOWED_BID
    assert worklock.functions.ethToTokens(staker1_bid).call() == min_stake + 7 * bonus_worklock_supply // 8
    assert worklock.functions.ethToTokens(MIN_ALLOWED_BID).call() == min_stake
    assert worklock.functions.ethToTokens(2 * MIN_ALLOWED_BID).call() == min_stake + bonus_worklock_supply // 8
    assert worklock.functions.getBiddersLength().call() == 4

    events = bidding_log.get_all_entries()
    assert 5 == len(events)
    event_args = events[-1]['args']
    assert event_args['sender'] == staker1
    assert event_args['depositedETH'] == deposit_eth_1

    # Can't claim or refund while bidding phase
    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.claim().transact({'from': staker1, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.refund().transact({'from': staker1, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)

    # Third staker does second small bid
    tx = worklock.functions.bid().transact({'from': staker3, 'value': 1, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    staker3_bid += 1
    assert worklock.functions.workInfo(staker3).call()[0] == staker3_bid
    worklock_balance += 1
    assert testerchain.w3.eth.getBalance(worklock.address) == worklock_balance
    assert worklock.functions.bonusETHSupply().call() == worklock_balance - 4 * MIN_ALLOWED_BID
    assert worklock.functions.getBiddersLength().call() == 4

    events = bidding_log.get_all_entries()
    assert 6 == len(events)
    event_args = events[5]['args']
    assert event_args['sender'] == staker3
    assert event_args['depositedETH'] == 1

    # But can cancel bid
    staker3_balance = testerchain.w3.eth.getBalance(staker3)
    tx = worklock.functions.cancelBid().transact({'from': staker3, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert worklock.functions.workInfo(staker3).call()[0] == 0
    worklock_balance -= staker3_bid
    bonus_worklock_supply += min_stake
    assert testerchain.w3.eth.getBalance(worklock.address) == worklock_balance
    assert worklock.functions.bonusETHSupply().call() == worklock_balance - 3 * MIN_ALLOWED_BID
    assert worklock.functions.ethToTokens(MIN_ALLOWED_BID).call() == min_stake
    assert worklock.functions.ethToTokens(2 * MIN_ALLOWED_BID).call() == min_stake + bonus_worklock_supply // 8
    assert testerchain.w3.eth.getBalance(staker3) == staker3_balance + staker3_bid
    assert worklock.functions.getBiddersLength().call() == 3
    assert worklock.functions.bidders(1).call() == staker1
    assert worklock.functions.workInfo(staker1).call()[3] == 1
    assert worklock.functions.bidders(0).call() == staker2
    assert worklock.functions.workInfo(staker2).call()[3] == 0
    assert worklock.functions.bidders(2).call() == staker4
    assert worklock.functions.workInfo(staker4).call()[3] == 2

    events = canceling_log.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert event_args['sender'] == staker3
    assert event_args['value'] == staker3_bid

    # Can't cancel twice in a row
    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.cancelBid().transact({'from': staker3, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)
    # Bid must be more than minimum
    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.bid().transact({'from': staker3, 'value': 1, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)

    # Third staker does third bid
    assert worklock.functions.workInfo(staker3).call()[0] == 0
    tx = worklock.functions.bid().transact({'from': staker3, 'value': deposit_eth_2, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    staker3_bid = deposit_eth_2
    assert worklock.functions.workInfo(staker3).call()[0] == staker3_bid
    worklock_balance += staker3_bid
    bonus_worklock_supply -= min_stake
    assert testerchain.w3.eth.getBalance(worklock.address) == worklock_balance
    assert worklock.functions.bonusETHSupply().call() == worklock_balance - 4 * MIN_ALLOWED_BID
    assert worklock.functions.ethToTokens(MIN_ALLOWED_BID).call() == min_stake
    assert worklock.functions.ethToTokens(2 * MIN_ALLOWED_BID).call() == min_stake + bonus_worklock_supply // 8
    assert worklock.functions.getBiddersLength().call() == 4
    assert worklock.functions.bidders(3).call() == staker3
    assert worklock.functions.workInfo(staker3).call()[3] == 3

    events = bidding_log.get_all_entries()
    assert 7 == len(events)
    event_args = events[-1]['args']
    assert event_args['sender'] == staker3
    assert event_args['depositedETH'] == deposit_eth_2

    # Can't check before end of cancellation window
    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.verifyBiddingCorrectness(gas_to_save_state).transact()
        testerchain.wait_for_receipt(tx)

    # Wait for the end of bidding
    testerchain.time_travel(seconds=ONE_HOUR)

    # Can't bid after the end of bidding
    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.bid().transact({'from': staker1, 'value': deposit_eth_1, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)
    # Can't refund without claim
    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.refund().transact({'from': staker1, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)
    # Can't claim during cancellation window
    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.claim().transact({'from': staker1, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)
    # Can't check before end of cancellation window
    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.verifyBiddingCorrectness(gas_to_save_state).transact()
        testerchain.wait_for_receipt(tx)
    # Can't force refund before end of cancellation window
    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.forceRefund([staker1]).transact()
        testerchain.wait_for_receipt(tx)

    # But can cancel during cancellation window
    staker3_balance = testerchain.w3.eth.getBalance(staker3)
    tx = worklock.functions.cancelBid().transact({'from': staker3, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert worklock.functions.workInfo(staker3).call()[0] == 0
    worklock_balance -= staker3_bid
    bonus_worklock_supply += min_stake
    assert testerchain.w3.eth.getBalance(worklock.address) == worklock_balance
    assert worklock.functions.bonusETHSupply().call() == worklock_balance - 3 * MIN_ALLOWED_BID
    assert worklock.functions.ethToTokens(MIN_ALLOWED_BID).call() == min_stake
    assert worklock.functions.ethToTokens(2 * MIN_ALLOWED_BID).call() == min_stake + bonus_worklock_supply // 8
    assert testerchain.w3.eth.getBalance(staker3) == staker3_balance + staker3_bid
    assert worklock.functions.getBiddersLength().call() == 3
    assert worklock.functions.bidders(1).call() == staker1
    assert worklock.functions.workInfo(staker1).call()[3] == 1
    assert worklock.functions.bidders(0).call() == staker2
    assert worklock.functions.workInfo(staker2).call()[3] == 0
    assert worklock.functions.bidders(2).call() == staker4
    assert worklock.functions.workInfo(staker4).call()[3] == 2

    events = canceling_log.get_all_entries()
    assert 2 == len(events)
    event_args = events[1]['args']
    assert event_args['sender'] == staker3
    assert event_args['value'] == staker3_bid

    # Wait for the end of cancellation window
    testerchain.time_travel(seconds=ONE_HOUR)

    # Can't claim before checking bidders
    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.claim().transact({'from': staker1, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)
    # Before verification need to adjust high bids
    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.verifyBiddingCorrectness(gas_to_save_state).transact()
        testerchain.wait_for_receipt(tx)
    # No compensation yet
    assert worklock.functions.compensation(staker1).call() == 0
    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.withdrawCompensation().transact({'from': staker1})
        testerchain.wait_for_receipt(tx)

    # Force refund to first staker
    assert worklock.functions.ethToTokens(staker1_bid).call() > max_stake
    staker_1_balance = testerchain.w3.eth.getBalance(staker1)
    tx = worklock.functions.forceRefund([staker1]).transact()
    testerchain.wait_for_receipt(tx)
    bid = worklock.functions.workInfo(staker1).call()[0]
    assert bid == 2 * deposit_eth_2
    refund = staker1_bid - bid
    staker1_bid = bid
    assert worklock.functions.ethToTokens(bid).call() <= max_stake
    assert testerchain.w3.eth.getBalance(worklock.address) == worklock_balance
    assert testerchain.w3.eth.getBalance(staker1) == staker_1_balance
    assert worklock.functions.compensation(staker1).call() == refund

    assert len(compensation_log.get_all_entries()) == 0
    events = force_refund_log.get_all_entries()
    assert len(events) == 1
    event_args = events[-1]['args']
    assert event_args['sender'] == creator
    assert event_args['bidder'] == staker1
    assert event_args['refundETH'] == refund

    # Can't force refund again
    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.forceRefund([staker1]).transact()
        testerchain.wait_for_receipt(tx)

    tx = worklock.functions.withdrawCompensation().transact({'from': staker1})
    testerchain.wait_for_receipt(tx)
    worklock_balance -= refund
    assert testerchain.w3.eth.getBalance(worklock.address) == worklock_balance
    assert testerchain.w3.eth.getBalance(staker1) == staker_1_balance + refund
    assert worklock.functions.compensation(staker1).call() == 0

    events = compensation_log.get_all_entries()
    assert len(events) == 1
    event_args = events[-1]['args']
    assert event_args['sender'] == staker1
    assert event_args['value'] == refund

    # Can't withdraw compensation again
    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.withdrawCompensation().transact({'from': staker1})
        testerchain.wait_for_receipt(tx)

    # Check all bidders
    assert not worklock.functions.isClaimingAvailable().call()
    tx = worklock.functions.verifyBiddingCorrectness(gas_to_save_state).transact()
    testerchain.wait_for_receipt(tx)
    assert worklock.functions.nextBidderToCheck().call() == 3
    assert worklock.functions.isClaimingAvailable().call()

    events = checks_log.get_all_entries()
    assert 1 == len(events)
    event_args = events[-1]['args']
    assert event_args['sender'] == creator
    assert event_args['startIndex'] == 0
    assert event_args['endIndex'] == 3

    # Can't check again
    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.verifyBiddingCorrectness(gas_to_save_state).transact()
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
    staker1_tokens = max_stake
    assert token.functions.balanceOf(staker1).call() == 0
    base_work = int(-(- min_stake * slowing_refund // boosting_refund))  # div ceil
    bonus_work = int(-(- bonus_worklock_supply * slowing_refund // boosting_refund // 2))  # div ceil
    staker1_remaining_work = base_work + bonus_work
    assert worklock.functions.getAvailableRefund(staker1).call() == 0
    assert worklock.functions.ethToWork(staker1_bid).call() == staker1_remaining_work
    bonus_part = staker1_bid - MIN_ALLOWED_BID
    assert worklock.functions.workToETH(staker1_remaining_work, staker1_bid).call() == staker1_bid
    assert worklock.functions.workToETH(bonus_work // 2, staker1_bid).call() == bonus_part // 2
    assert worklock.functions.workToETH(bonus_work, staker1_bid).call() == bonus_part
    assert worklock.functions.workToETH(bonus_work + base_work // 2, staker1_bid).call() == MIN_ALLOWED_BID // 2 + bonus_part
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
    # Can't cancel after bidding is over
    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.cancelBid().transact({'from': staker2, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)

    # Second staker claims tokens
    value, measure_work, _completed_work, periods = escrow.functions.stakerInfo(staker2).call()
    assert not measure_work
    assert value == 0
    assert periods == 0
    staker2_tokens = min_stake
    # staker2_tokens * slowing_refund / boosting_refund
    staker2_remaining_work = base_work
    assert worklock.functions.ethToWork(deposit_eth_2).call() == staker2_remaining_work
    assert worklock.functions.workToETH(staker2_remaining_work, deposit_eth_2).call() == deposit_eth_2
    assert worklock.functions.workToETH(staker2_remaining_work // 2, deposit_eth_2).call() == deposit_eth_2 // 2
    tx = escrow.functions.setCompletedWork(staker2, staker2_remaining_work // 2).transact()
    testerchain.wait_for_receipt(tx)
    assert not worklock.functions.workInfo(staker2).call()[2]

    # Can't refund before claim even with completed work
    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.refund().transact({'from': staker2, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)

    tx = worklock.functions.claim().transact({'from': staker2, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert worklock.functions.getAvailableRefund(staker2).call() == 0
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
    completed_work = bonus_work // 2 + 1
    remaining_work = staker1_remaining_work - completed_work
    tx = escrow.functions.setCompletedWork(staker1, completed_work).transact()
    testerchain.wait_for_receipt(tx)
    assert worklock.functions.getRemainingWork(staker1).call() == remaining_work
    refund = (staker1_bid - MIN_ALLOWED_BID) // 2
    assert worklock.functions.getAvailableRefund(staker1).call() == refund

    tx = worklock.functions.refund().transact({'from': staker1, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert worklock.functions.workInfo(staker1).call()[0] == staker1_bid - refund
    assert worklock.functions.getRemainingWork(staker1).call() == remaining_work
    assert testerchain.w3.eth.getBalance(staker1) == staker1_balance + refund
    worklock_balance -= refund
    assert testerchain.w3.eth.getBalance(worklock.address) == worklock_balance
    _value, measure_work, _completed_work, _periods = escrow.functions.stakerInfo(staker1).call()
    assert measure_work
    assert worklock.functions.getAvailableRefund(staker1).call() == 0

    events = refund_log.get_all_entries()
    assert 1 == len(events)
    event_args = events[0]['args']
    assert event_args['sender'] == staker1
    assert event_args['refundETH'] == refund
    assert event_args['completedWork'] == bonus_work // 2

    # "Do" more work and full refund
    staker1_balance = testerchain.w3.eth.getBalance(staker1)
    completed_work = staker1_remaining_work
    tx = escrow.functions.setCompletedWork(staker1, completed_work).transact()
    testerchain.wait_for_receipt(tx)
    assert worklock.functions.getRemainingWork(staker1).call() == 0
    assert worklock.functions.getAvailableRefund(staker1).call() == staker1_bid - refund

    tx = worklock.functions.refund().transact({'from': staker1, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert worklock.functions.workInfo(staker1).call()[0] == 0
    assert worklock.functions.getRemainingWork(staker1).call() == 0
    assert testerchain.w3.eth.getBalance(staker1) == staker1_balance + staker1_bid - refund
    worklock_balance -= staker1_bid - refund
    assert testerchain.w3.eth.getBalance(worklock.address) == worklock_balance
    _value, measure_work, _completed_work, _periods = escrow.functions.stakerInfo(staker1).call()
    assert not measure_work
    assert worklock.functions.getAvailableRefund(staker1).call() == 0

    events = refund_log.get_all_entries()
    assert 2 == len(events)
    event_args = events[1]['args']
    assert event_args['sender'] == staker1
    assert event_args['refundETH'] == staker1_bid - refund
    assert event_args['completedWork'] == remaining_work + 1

    # Can't refund more tokens
    tx = escrow.functions.setCompletedWork(staker1, 2 * completed_work).transact()
    testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.refund().transact({'from': staker1, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)


def test_reentrancy(testerchain, token_economics, deploy_contract, escrow, worklock_factory):
    # Deploy WorkLock
    boosting_refund = 100
    worklock_supply = 2 * token_economics.maximum_allowed_locked
    max_bid = 2 * MIN_ALLOWED_BID
    worklock = worklock_factory(supply=worklock_supply,
                                bidding_delay=0,
                                additional_time_to_cancel=0,
                                boosting_refund=boosting_refund)

    refund_log = worklock.events.Refund.createFilter(fromBlock='latest')
    canceling_log = worklock.events.Canceled.createFilter(fromBlock='latest')
    compensation_log = worklock.events.CompensationWithdrawn.createFilter(fromBlock='latest')

    reentrancy_contract, _ = deploy_contract('ReentrancyTest')
    contract_address = reentrancy_contract.address
    tx = testerchain.client.send_transaction(
        {'from': testerchain.etherbase_account, 'to': contract_address, 'value': max_bid})
    testerchain.wait_for_receipt(tx)

    # Bid
    transaction = worklock.functions.bid().buildTransaction({'gas': 0})
    tx = reentrancy_contract.functions.setData(1, transaction['to'], max_bid, transaction['data']).transact()
    testerchain.wait_for_receipt(tx)
    tx = testerchain.client.send_transaction({'to': contract_address})
    testerchain.wait_for_receipt(tx)
    assert worklock.functions.workInfo(contract_address).call()[0] == max_bid
    assert testerchain.w3.eth.getBalance(worklock.address) == max_bid
    tx = worklock.functions.bid().transact({'from': testerchain.etherbase_account, 'value': MIN_ALLOWED_BID})
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
    assert worklock.functions.workInfo(contract_address).call()[0] == max_bid
    assert len(canceling_log.get_all_entries()) == 0

    # Do force refund and check bidders
    testerchain.time_travel(seconds=ONE_HOUR)
    tx = reentrancy_contract.functions.setData(0, NULL_ADDRESS, 0, b'').transact()
    testerchain.wait_for_receipt(tx)
    tx = worklock.functions.forceRefund([contract_address]).transact()
    testerchain.wait_for_receipt(tx)
    tx = worklock.functions.verifyBiddingCorrectness(30000).transact()
    testerchain.wait_for_receipt(tx)

    # Check reentrancy protection when withdrawing compensation
    refund = worklock.functions.compensation(contract_address).call()
    assert refund > 0
    transaction = worklock.functions.withdrawCompensation().buildTransaction({'gas': 0})
    tx = reentrancy_contract.functions.setData(2, transaction['to'], 0, transaction['data']).transact()
    testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = testerchain.client.send_transaction({'to': contract_address})
        testerchain.wait_for_receipt(tx)
    assert testerchain.w3.eth.getBalance(contract_address) == balance
    assert worklock.functions.compensation(contract_address).call() == refund
    assert len(compensation_log.get_all_entries()) == 0

    # Claim
    transaction = worklock.functions.claim().buildTransaction({'gas': 0})
    tx = reentrancy_contract.functions.setData(1, transaction['to'], 0, transaction['data']).transact()
    testerchain.wait_for_receipt(tx)
    tx = testerchain.client.send_transaction({'to': contract_address})
    testerchain.wait_for_receipt(tx)
    remaining_work = worklock_supply // 2
    assert worklock.functions.getRemainingWork(contract_address).call() == remaining_work

    # Prepare for refund and check reentrancy protection
    assert worklock.functions.workInfo(contract_address).call()[0] == MIN_ALLOWED_BID
    balance = testerchain.w3.eth.getBalance(contract_address)
    completed_work = remaining_work // 4
    tx = escrow.functions.setCompletedWork(contract_address, completed_work).transact()
    testerchain.wait_for_receipt(tx)
    transaction = worklock.functions.refund().buildTransaction({'gas': 0})
    tx = reentrancy_contract.functions.setData(2, transaction['to'], 0, transaction['data']).transact()
    testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = testerchain.client.send_transaction({'to': contract_address})
        testerchain.wait_for_receipt(tx)
    assert testerchain.w3.eth.getBalance(contract_address) == balance
    assert worklock.functions.workInfo(contract_address).call()[0] == MIN_ALLOWED_BID
    assert worklock.functions.getRemainingWork(contract_address).call() == remaining_work - completed_work
    assert len(refund_log.get_all_entries()) == 0


def test_verifying_correctness(testerchain, token_economics, escrow, deploy_contract, worklock_factory):
    creator, bidder1, bidder2, bidder3, *everyone_else = testerchain.w3.eth.accounts
    gas_to_save_state = 30000
    boosting_refund = 100

    # Test: bidder has too much tokens to claim
    worklock_supply = token_economics.maximum_allowed_locked + 1
    worklock = worklock_factory(supply=worklock_supply,
                                bidding_delay=0,
                                additional_time_to_cancel=0,
                                boosting_refund=boosting_refund)

    # Bid
    do_bids(testerchain, worklock, [bidder1], MIN_ALLOWED_BID)
    assert worklock.functions.ethToTokens(MIN_ALLOWED_BID).call() == worklock_supply

    # Check will fail because bidder has too much tokens to claim
    testerchain.time_travel(seconds=ONE_HOUR)
    worklock_balance = testerchain.w3.eth.getBalance(worklock.address)
    max_stake = worklock.functions.maxAllowableLockedTokens().call()
    assert max_stake * worklock_balance // worklock_supply < MIN_ALLOWED_BID
    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.verifyBiddingCorrectness(30000).transact()
        testerchain.wait_for_receipt(tx)

    # Test: bidder will get tokens as much as possible without force refund
    worklock_supply = 3 * token_economics.maximum_allowed_locked
    worklock = worklock_factory(supply=worklock_supply,
                                bidding_delay=0,
                                additional_time_to_cancel=0,
                                boosting_refund=boosting_refund)
    checks_log = worklock.events.BiddersChecked.createFilter(fromBlock='latest')

    # Bids
    do_bids(testerchain, worklock, [bidder1, bidder2, bidder3], MIN_ALLOWED_BID)
    assert worklock.functions.ethToTokens(MIN_ALLOWED_BID).call() == token_economics.maximum_allowed_locked

    # Wait end of bidding
    testerchain.time_travel(seconds=ONE_HOUR)
    worklock_balance = testerchain.w3.eth.getBalance(worklock.address)
    max_stake = worklock.functions.maxAllowableLockedTokens().call()
    assert max_stake * worklock_balance // worklock_supply == MIN_ALLOWED_BID

    # Too low value for gas limit
    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.verifyBiddingCorrectness(gas_to_save_state)\
            .transact({'from': bidder1, 'gas': gas_to_save_state + 25000})
        testerchain.wait_for_receipt(tx)
    tx = worklock.functions.verifyBiddingCorrectness(gas_to_save_state)\
        .transact({'from': bidder1, 'gas': gas_to_save_state + 35000})
    testerchain.wait_for_receipt(tx)
    assert worklock.functions.nextBidderToCheck().call() == 3

    events = checks_log.get_all_entries()
    assert len(events) == 1
    event_args = events[-1]['args']
    assert event_args['sender'] == bidder1
    assert event_args['startIndex'] == 0
    assert event_args['endIndex'] == 3

    # Test: partial verification with low amount of gas limit
    worklock_supply = 3 * token_economics.maximum_allowed_locked
    worklock = worklock_factory(supply=worklock_supply,
                                bidding_delay=0,
                                additional_time_to_cancel=0,
                                boosting_refund=boosting_refund)
    checks_log = worklock.events.BiddersChecked.createFilter(fromBlock='latest')

    # Bids
    bid = MIN_ALLOWED_BID + 1
    do_bids(testerchain, worklock, [bidder1, bidder2, bidder3], bid)
    assert worklock.functions.ethToTokens(bid).call() == worklock_supply // 3

    # Wait end of bidding
    testerchain.time_travel(seconds=ONE_HOUR)
    worklock_balance = testerchain.w3.eth.getBalance(worklock.address)
    max_stake = worklock.functions.maxAllowableLockedTokens().call()
    max_bid_from_max_stake = max_stake * worklock_balance // worklock_supply
    assert max_bid_from_max_stake >= MIN_ALLOWED_BID

    # Too low value for remaining gas
    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.verifyBiddingCorrectness(0)\
            .transact({'from': bidder1, 'gas': gas_to_save_state + 30000})
        testerchain.wait_for_receipt(tx)

    # Too low value for gas limit
    assert worklock.functions.nextBidderToCheck().call() == 0
    tx = worklock.functions.verifyBiddingCorrectness(gas_to_save_state).transact({'gas': gas_to_save_state + 25000})
    testerchain.wait_for_receipt(tx)
    assert worklock.functions.nextBidderToCheck().call() == 0

    # Set gas only for one check
    tx = worklock.functions.verifyBiddingCorrectness(gas_to_save_state)\
        .transact({'gas': gas_to_save_state + 35000, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert worklock.functions.nextBidderToCheck().call() == 1

    events = checks_log.get_all_entries()
    assert len(events) == 1
    event_args = events[-1]['args']
    assert event_args['sender'] == creator
    assert event_args['startIndex'] == 0
    assert event_args['endIndex'] == 1

    # Check others
    tx = worklock.functions.verifyBiddingCorrectness(gas_to_save_state).transact()
    testerchain.wait_for_receipt(tx)
    assert worklock.functions.nextBidderToCheck().call() == 3

    events = checks_log.get_all_entries()
    assert len(events) == 2
    event_args = events[-1]['args']
    assert event_args['sender'] == creator
    assert event_args['startIndex'] == 1
    assert event_args['endIndex'] == 3


def test_force_refund(testerchain, token_economics, deploy_contract, worklock_factory, token):
    creator, *bidders = testerchain.w3.eth.accounts
    boosting_refund = 100
    gas_to_save_state = 30000

    # All bids are allowed, can't do force refund
    worklock_supply = len(bidders) * token_economics.maximum_allowed_locked
    worklock = worklock_factory(supply=worklock_supply,
                                bidding_delay=0,
                                additional_time_to_cancel=0,
                                boosting_refund=boosting_refund)

    do_bids(testerchain, worklock, bidders, MIN_ALLOWED_BID)
    # Wait end of bidding
    testerchain.time_travel(seconds=ONE_HOUR)

    bidders = sorted(bidders, key=str.casefold)
    # There is no bidders with unacceptable bid
    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.forceRefund([]).transact()
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.forceRefund(bidders).transact()
        testerchain.wait_for_receipt(tx)
    for bidder in bidders:
        with pytest.raises((TransactionFailed, ValueError)):
            tx = worklock.functions.forceRefund([bidder]).transact()
            testerchain.wait_for_receipt(tx)

    # Prove that check is ok
    tx = worklock.functions.verifyBiddingCorrectness(gas_to_save_state).transact()
    testerchain.wait_for_receipt(tx)

    # Different bids from whales
    hidden_whales = bidders[0:3]
    whales = bidders[3:6]
    normal_bidders = bidders[6:8]
    bidders = normal_bidders + hidden_whales + whales

    worklock_supply = len(bidders) * token_economics.maximum_allowed_locked
    worklock = worklock_factory(supply=worklock_supply,
                                bidding_delay=0,
                                additional_time_to_cancel=0,
                                boosting_refund=boosting_refund)
    normal_bid = MIN_ALLOWED_BID
    hidden_whales_bid = 2 * MIN_ALLOWED_BID
    whales_bid = 3 * MIN_ALLOWED_BID
    do_bids(testerchain, worklock, normal_bidders, normal_bid)
    do_bids(testerchain, worklock, hidden_whales, hidden_whales_bid)
    do_bids(testerchain, worklock, whales, whales_bid)
    refund_log = worklock.events.ForceRefund.createFilter(fromBlock='latest')

    # Wait end of bidding
    testerchain.time_travel(seconds=ONE_HOUR)

    # Verification founds whales
    assert worklock.functions.ethToTokens(normal_bid).call() < token_economics.maximum_allowed_locked
    assert worklock.functions.ethToTokens(hidden_whales_bid).call() < token_economics.maximum_allowed_locked
    assert worklock.functions.ethToTokens(whales_bid).call() > token_economics.maximum_allowed_locked
    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.verifyBiddingCorrectness(gas_to_save_state).transact()
        testerchain.wait_for_receipt(tx)

    # Can't refund to a normal bidder or an empty address
    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.forceRefund([]).transact()
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.forceRefund([normal_bidders[0]]).transact()
        testerchain.wait_for_receipt(tx)
    # Or to single hidden whale
    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.forceRefund([hidden_whales[0]]).transact()
        testerchain.wait_for_receipt(tx)

    # Force refund to a single whale
    whale_1 = whales[0]
    worklock_balance = testerchain.w3.eth.getBalance(worklock.address)
    whale_1_balance = testerchain.w3.eth.getBalance(whale_1)
    tx = worklock.functions.forceRefund([whale_1]).transact()
    testerchain.wait_for_receipt(tx)
    bid = worklock.functions.workInfo(whale_1).call()[0]
    refund = whales_bid - bid
    assert refund > 0
    assert bid > normal_bid
    assert worklock.functions.ethToTokens(bid).call() <= token_economics.maximum_allowed_locked
    assert testerchain.w3.eth.getBalance(worklock.address) == worklock_balance
    assert testerchain.w3.eth.getBalance(whale_1) == whale_1_balance
    assert worklock.functions.compensation(whale_1).call() == refund

    events = refund_log.get_all_entries()
    assert len(events) == 1
    event_args = events[-1]['args']
    assert event_args['sender'] == creator
    assert event_args['bidder'] == whale_1
    assert event_args['refundETH'] == refund

    # Can't verify yet
    assert worklock.functions.ethToTokens(whales_bid).call() > token_economics.maximum_allowed_locked
    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.verifyBiddingCorrectness(gas_to_save_state).transact()
        testerchain.wait_for_receipt(tx)

    # Group of addresses to refund can't include normal bidders
    group = sorted([normal_bidders[0], whales[1]], key=str.casefold)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.forceRefund(group).transact()
        testerchain.wait_for_receipt(tx)
    # Bad input: not unique addresses, nonexistent address, not sorted list
    group = sorted([whales[1], *whales], key=str.casefold)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.forceRefund(group).transact()
        testerchain.wait_for_receipt(tx)
    group = sorted([NULL_ADDRESS, *whales], key=str.casefold)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.forceRefund(group).transact()
        testerchain.wait_for_receipt(tx)
    group = sorted([creator, *whales], key=str.casefold)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.forceRefund(group).transact()
        testerchain.wait_for_receipt(tx)
    group = sorted(whales, key=str.casefold)[::-1]
    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.forceRefund(group).transact()
        testerchain.wait_for_receipt(tx)

    # Force refund to a group of whales with the same bid
    whale_2 = whales[1]
    whale_3 = whales[2]
    whale_2_balance = testerchain.w3.eth.getBalance(whale_2)
    whale_3_balance = testerchain.w3.eth.getBalance(whale_3)
    group = sorted([whale_2, whale_3], key=str.casefold)
    tx = worklock.functions.forceRefund(group).transact()
    testerchain.wait_for_receipt(tx)
    bid = worklock.functions.workInfo(whale_2).call()[0]
    assert worklock.functions.workInfo(whale_3).call()[0] == bid
    refund = whales_bid - bid
    assert refund > 0
    assert bid > normal_bid
    assert worklock.functions.ethToTokens(bid).call() <= token_economics.maximum_allowed_locked
    assert testerchain.w3.eth.getBalance(worklock.address) == worklock_balance
    assert testerchain.w3.eth.getBalance(whale_2) == whale_2_balance
    assert testerchain.w3.eth.getBalance(whale_3) == whale_3_balance
    assert worklock.functions.compensation(whale_2).call() == refund
    assert worklock.functions.compensation(whale_3).call() == refund

    events = refund_log.get_all_entries()
    assert len(events) == 3
    event_args = events[-2]['args']
    assert event_args['sender'] == creator
    assert event_args['bidder'] == group[0]
    assert event_args['refundETH'] == refund
    event_args = events[-1]['args']
    assert event_args['sender'] == creator
    assert event_args['bidder'] == group[1]
    assert event_args['refundETH'] == refund

    # Can't verify yet
    assert worklock.functions.ethToTokens(hidden_whales_bid).call() > token_economics.maximum_allowed_locked
    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.verifyBiddingCorrectness(gas_to_save_state).transact()
        testerchain.wait_for_receipt(tx)

    # But can verify only one of them
    assert worklock.functions.nextBidderToCheck().call() == 0
    tx = worklock.functions.verifyBiddingCorrectness(gas_to_save_state)\
        .transact({'gas': gas_to_save_state + 35000, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert worklock.functions.nextBidderToCheck().call() == 1

    # Full force refund
    group = sorted(whales + hidden_whales, key=str.casefold)
    balances = [testerchain.w3.eth.getBalance(bidder) for bidder in group]
    bids = [worklock.functions.workInfo(bidder).call()[0] for bidder in group]
    refunds = [worklock.functions.compensation(bidder).call() for bidder in group]

    tx = worklock.functions.forceRefund(group).transact({'from': whale_1})
    testerchain.wait_for_receipt(tx)
    assert worklock.functions.ethToTokens(normal_bid).call() == token_economics.maximum_allowed_locked
    events = refund_log.get_all_entries()
    assert len(events) == 3 + len(group)

    for i, bidder in enumerate(group):
        assert worklock.functions.workInfo(bidder).call()[0] == normal_bid
        refund = bids[i] - normal_bid
        assert refund > 0
        assert testerchain.w3.eth.getBalance(bidder) == balances[i]
        assert worklock.functions.compensation(bidder).call() == refunds[i] + refund
        event_args = events[3 + i]['args']
        assert event_args['sender'] == whale_1
        assert event_args['bidder'] == bidder
        assert event_args['refundETH'] == refund

    assert testerchain.w3.eth.getBalance(worklock.address) == worklock_balance

    # Now verify will work
    assert worklock.functions.nextBidderToCheck().call() == 0
    tx = worklock.functions.verifyBiddingCorrectness(gas_to_save_state).transact()
    testerchain.wait_for_receipt(tx)
    assert worklock.functions.nextBidderToCheck().call() == len(bidders)

    # Test extreme case with random values
    bidders = testerchain.w3.eth.accounts[1:]
    worklock_supply = 10 * token_economics.maximum_allowed_locked
    max_bid = 2000 * MIN_ALLOWED_BID
    worklock = worklock_factory(supply=worklock_supply,
                                bidding_delay=0,
                                additional_time_to_cancel=0,
                                boosting_refund=boosting_refund)

    small_bids = [random.randrange(MIN_ALLOWED_BID, int(1.5 * MIN_ALLOWED_BID)) for _ in range(10)]
    total_small_bids = sum(small_bids)
    min_potential_whale_bid = (max_bid - total_small_bids) // 9
    whales_bids = [random.randrange(min_potential_whale_bid, max_bid) for _ in range(9)]
    initial_bids = small_bids + whales_bids
    for i, bid in enumerate(initial_bids):
        bidder = bidders[i]
        do_bids(testerchain, worklock, [bidder], bid)

    # Wait end of bidding
    testerchain.time_travel(seconds=ONE_HOUR)

    # Can't verify yet
    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.verifyBiddingCorrectness(gas_to_save_state).transact()
        testerchain.wait_for_receipt(tx)

    # Force refund
    whales = bidders[len(small_bids):len(initial_bids)]
    whales = sorted(whales, key=str.casefold)
    tx = worklock.functions.forceRefund(whales).transact()
    testerchain.wait_for_receipt(tx)

    # Bids are correct now
    for whale in whales:
        bid = worklock.functions.workInfo(whale).call()[0]
        assert worklock.functions.ethToTokens(bid).call() <= token_economics.maximum_allowed_locked
    tx = worklock.functions.verifyBiddingCorrectness(gas_to_save_state).transact()
    testerchain.wait_for_receipt(tx)

    # Special case: there are less bidders than n, where n is `worklock_supply // maximum_allowed_locked`
    worklock_supply = 10 * token_economics.maximum_allowed_locked
    worklock = worklock_factory(supply=worklock_supply,
                                bidding_delay=0,
                                additional_time_to_cancel=0,
                                boosting_refund=boosting_refund)
    shutdown_log = worklock.events.Shutdown.createFilter(fromBlock='latest')

    bidders = bidders[0:9]
    do_bids(testerchain, worklock, bidders, 10 * MIN_ALLOWED_BID)
    # Wait end of bidding
    testerchain.time_travel(seconds=ONE_HOUR)

    bidder1 = bidders[0]
    worklock_tokens = token.functions.balanceOf(worklock.address).call()
    creator_tokens = token.functions.balanceOf(creator).call()
    bidder1_tokens = token.functions.balanceOf(bidder1).call()

    bidders = sorted(bidders, key=str.casefold)
    tx = worklock.functions.forceRefund(bidders).transact({'from': bidder1})
    testerchain.wait_for_receipt(tx)

    end_cancellation_date = worklock.functions.endCancellationDate().call()
    now = testerchain.w3.eth.getBlock('latest').timestamp
    assert end_cancellation_date > now
    assert token.functions.balanceOf(worklock.address).call() == 0
    assert token.functions.balanceOf(creator).call() == creator_tokens + worklock_tokens
    assert token.functions.balanceOf(bidder1).call() == bidder1_tokens

    # Distribution is canceled
    with pytest.raises((TransactionFailed, ValueError)):
        do_bids(testerchain, worklock, [bidder1], MIN_ALLOWED_BID)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.claim().transact({'from': bidder1, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)

    assert worklock.functions.workInfo(bidder1).call()[0] > 0
    tx = worklock.functions.cancelBid().transact({'from': bidder1, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert worklock.functions.workInfo(bidder1).call()[0] == 0

    events = shutdown_log.get_all_entries()
    assert len(events) == 1
    event_args = events[-1]['args']
    assert event_args['sender'] == bidder1


def test_shutdown(testerchain, token_economics, deploy_contract, worklock_factory, token):
    creator, bidder, *everyone_else = testerchain.w3.eth.accounts
    boosting_refund = 100
    gas_to_save_state = 30000

    # Shutdown before start of bidding
    now = testerchain.get_blocktime()
    start_bid_date = now + ONE_HOUR
    end_bid_date = start_bid_date + ONE_HOUR
    end_cancellation_date = end_bid_date + ONE_HOUR
    worklock = worklock_factory(supply=0,
                                bidding_delay=ONE_HOUR,
                                additional_time_to_cancel=ONE_HOUR,
                                boosting_refund=boosting_refund)
    shutdown_log = worklock.events.Shutdown.createFilter(fromBlock='latest')

    # Only owner can do shutdown
    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.shutdown().transact({'from': bidder})
        testerchain.wait_for_receipt(tx)

    creator_tokens = token.functions.balanceOf(creator).call()
    assert token.functions.balanceOf(worklock.address).call() == 0
    assert worklock.functions.startBidDate().call() == start_bid_date
    assert worklock.functions.endBidDate().call() == end_bid_date
    assert worklock.functions.endCancellationDate().call() == end_cancellation_date
    tx = worklock.functions.shutdown().transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert worklock.functions.startBidDate().call() == 0
    assert worklock.functions.endBidDate().call() == 0
    assert worklock.functions.endCancellationDate().call() > end_cancellation_date
    assert token.functions.balanceOf(worklock.address).call() == 0
    assert token.functions.balanceOf(creator).call() == creator_tokens

    events = shutdown_log.get_all_entries()
    assert len(events) == 1
    event_args = events[-1]['args']
    assert event_args['sender'] == creator

    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.bid().transact({'from': bidder, 'value': MIN_ALLOWED_BID, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)

    # Shutdown after start of bidding
    now = testerchain.get_blocktime()
    start_bid_date = now
    end_bid_date = start_bid_date + ONE_HOUR
    end_cancellation_date = end_bid_date + ONE_HOUR
    worklock_supply = token_economics.maximum_allowed_locked
    worklock = worklock_factory(supply=worklock_supply,
                                bidding_delay=0,
                                additional_time_to_cancel=ONE_HOUR,
                                boosting_refund=boosting_refund)
    shutdown_log = worklock.events.Shutdown.createFilter(fromBlock='latest')
    do_bids(testerchain, worklock, [bidder], MIN_ALLOWED_BID)

    # Only owner can do shutdown
    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.shutdown().transact({'from': bidder})
        testerchain.wait_for_receipt(tx)

    creator_tokens = token.functions.balanceOf(creator).call()
    assert token.functions.balanceOf(worklock.address).call() == worklock_supply
    assert worklock.functions.startBidDate().call() == start_bid_date
    assert worklock.functions.endBidDate().call() == end_bid_date
    assert worklock.functions.endCancellationDate().call() == end_cancellation_date
    tx = worklock.functions.shutdown().transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert worklock.functions.startBidDate().call() == 0
    assert worklock.functions.endBidDate().call() == 0
    assert worklock.functions.endCancellationDate().call() > end_cancellation_date
    assert token.functions.balanceOf(worklock.address).call() == 0
    assert token.functions.balanceOf(creator).call() == creator_tokens + worklock_supply

    events = shutdown_log.get_all_entries()
    assert len(events) == 1
    event_args = events[-1]['args']
    assert event_args['sender'] == creator

    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.bid().transact({'from': bidder, 'value': MIN_ALLOWED_BID, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)
    tx = token.functions.approve(worklock.address, worklock_supply).transact()
    testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.tokenDeposit(worklock_supply).transact()
        testerchain.wait_for_receipt(tx)

    assert worklock.functions.workInfo(bidder).call()[0] > 0
    tx = worklock.functions.cancelBid().transact({'from': bidder, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert worklock.functions.workInfo(bidder).call()[0] == 0

    # Shutdown after end of bidding
    now = testerchain.get_blocktime()
    start_bid_date = now
    end_bid_date = start_bid_date + ONE_HOUR
    end_cancellation_date = end_bid_date + ONE_HOUR
    worklock = worklock_factory(supply=worklock_supply,
                                bidding_delay=0,
                                additional_time_to_cancel=ONE_HOUR,
                                boosting_refund=boosting_refund)
    shutdown_log = worklock.events.Shutdown.createFilter(fromBlock='latest')
    do_bids(testerchain, worklock, [bidder], MIN_ALLOWED_BID)

    # Wait end of bidding
    testerchain.time_travel(seconds=ONE_HOUR)

    # Only owner can do shutdown
    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.shutdown().transact({'from': bidder})
        testerchain.wait_for_receipt(tx)

    tx = worklock.functions.shutdown().transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert worklock.functions.startBidDate().call() == 0
    assert worklock.functions.endBidDate().call() == 0
    assert worklock.functions.endCancellationDate().call() > end_cancellation_date
    assert token.functions.balanceOf(worklock.address).call() == 0
    assert token.functions.balanceOf(creator).call() == creator_tokens + worklock_supply

    events = shutdown_log.get_all_entries()
    assert len(events) == 1
    event_args = events[-1]['args']
    assert event_args['sender'] == creator

    assert worklock.functions.workInfo(bidder).call()[0] > 0
    tx = worklock.functions.cancelBid().transact({'from': bidder, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert worklock.functions.workInfo(bidder).call()[0] == 0

    tx = token.functions.approve(worklock.address, worklock_supply).transact()
    testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.tokenDeposit(worklock_supply).transact()
        testerchain.wait_for_receipt(tx)

    # Shutdown after end of cancellation window
    now = testerchain.get_blocktime()
    start_bid_date = now
    end_bid_date = start_bid_date + ONE_HOUR
    end_cancellation_date = end_bid_date
    worklock = worklock_factory(supply=worklock_supply,
                                bidding_delay=0,
                                additional_time_to_cancel=0,
                                boosting_refund=boosting_refund)
    shutdown_log = worklock.events.Shutdown.createFilter(fromBlock='latest')
    do_bids(testerchain, worklock, [bidder], MIN_ALLOWED_BID)

    # Wait end of cancellation window
    testerchain.time_travel(seconds=ONE_HOUR)

    # Only owner can do shutdown
    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.shutdown().transact({'from': bidder})
        testerchain.wait_for_receipt(tx)

    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.cancelBid().transact({'from': bidder, 'gas_price': 0})
        testerchain.wait_for_receipt(tx)

    tx = worklock.functions.shutdown().transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert worklock.functions.startBidDate().call() == 0
    assert worklock.functions.endBidDate().call() == 0
    assert worklock.functions.endCancellationDate().call() > end_cancellation_date
    assert token.functions.balanceOf(worklock.address).call() == 0
    assert token.functions.balanceOf(creator).call() == creator_tokens + worklock_supply

    events = shutdown_log.get_all_entries()
    assert len(events) == 1
    event_args = events[-1]['args']
    assert event_args['sender'] == creator

    assert worklock.functions.workInfo(bidder).call()[0] > 0
    tx = worklock.functions.cancelBid().transact({'from': bidder, 'gas_price': 0})
    testerchain.wait_for_receipt(tx)
    assert worklock.functions.workInfo(bidder).call()[0] == 0

    # Shutdown after enabling of claiming
    worklock = worklock_factory(supply=worklock_supply,
                                bidding_delay=0,
                                additional_time_to_cancel=0,
                                boosting_refund=boosting_refund)
    do_bids(testerchain, worklock, [bidder], MIN_ALLOWED_BID)

    # Wait end of cancellation window
    testerchain.time_travel(seconds=ONE_HOUR)

    tx = worklock.functions.verifyBiddingCorrectness(gas_to_save_state).transact()
    testerchain.wait_for_receipt(tx)
    assert worklock.functions.isClaimingAvailable().call()

    # Can't call shutdown after enabling of claiming
    with pytest.raises((TransactionFailed, ValueError)):
        tx = worklock.functions.shutdown().transact({'from': creator})
        testerchain.wait_for_receipt(tx)
