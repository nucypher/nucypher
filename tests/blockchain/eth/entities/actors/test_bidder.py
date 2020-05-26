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

from nucypher.blockchain.eth.actors import Bidder
from nucypher.blockchain.eth.agents import ContractAgency, StakingEscrowAgent, WorkLockAgent
from nucypher.blockchain.eth.constants import NULL_ADDRESS


def test_create_bidder(testerchain, test_registry, agency, token_economics):
    bidder_address = testerchain.unassigned_accounts[0]
    bidder = Bidder(checksum_address=bidder_address, registry=test_registry)
    assert bidder.checksum_address == bidder_address
    assert bidder.registry == test_registry

    assert not bidder.get_deposited_eth
    assert not bidder.completed_work
    assert not bidder.remaining_work
    assert not bidder.refunded_work


def test_bidding(testerchain, agency, token_economics, test_registry):
    min_allowed_bid = token_economics.worklock_min_allowed_bid
    max_bid = 2000 * min_allowed_bid
    small_bids = [random.randrange(min_allowed_bid, 2 * min_allowed_bid) for _ in range(10)]
    total_small_bids = sum(small_bids)
    min_potential_whale_bid = (max_bid - total_small_bids) // 9
    whales_bids = [random.randrange(min_potential_whale_bid, max_bid) for _ in range(9)]
    initial_bids = small_bids + whales_bids

    for i, bid in enumerate(initial_bids):
        bidder_address = testerchain.client.accounts[i]
        bidder = Bidder(checksum_address=bidder_address, registry=test_registry)

        assert bidder.get_deposited_eth == 0
        receipt = bidder.place_bid(value=bid)
        assert receipt['status'] == 1
        assert bidder.get_deposited_eth == bid


def test_cancel_bid(testerchain, agency, token_economics, test_registry):
    # Wait until the bidding window closes...
    testerchain.time_travel(seconds=token_economics.bidding_duration+1)

    bidder_address = testerchain.client.accounts[1]
    bidder = Bidder(checksum_address=bidder_address, registry=test_registry)
    assert bidder.get_deposited_eth        # Bid
    receipt = bidder.cancel_bid()    # Cancel
    assert receipt['status'] == 1
    assert not bidder.get_deposited_eth    # No more bid

    # Can't cancel a bid twice in a row
    with pytest.raises((TransactionFailed, ValueError)):
        _receipt = bidder.cancel_bid()


def test_get_remaining_work(testerchain, agency, token_economics, test_registry):
    bidder_address = testerchain.client.accounts[0]
    bidder = Bidder(checksum_address=bidder_address, registry=test_registry)
    remaining = bidder.remaining_work
    assert remaining


def test_verify_correctness_before_refund(testerchain, agency, token_economics, test_registry):
    bidder_address = testerchain.client.accounts[0]
    bidder = Bidder(checksum_address=bidder_address, registry=test_registry)
    worklock_agent = ContractAgency.get_agent(WorkLockAgent, registry=test_registry)

    with pytest.raises(Bidder.CancellationWindowIsOpen):
        _receipt = bidder.claim()

    # Wait until the cancellation window closes...
    testerchain.time_travel(seconds=token_economics.cancellation_window_duration+1)

    with pytest.raises(Bidder.BidderError):
        _receipt = bidder.verify_bidding_correctness(gas_limit=100000)
    assert not worklock_agent.bidders_checked()
    assert bidder.get_whales()
    assert not worklock_agent.is_claiming_available()


def test_force_refund(testerchain, agency, token_economics, test_registry):
    bidder_address = testerchain.client.accounts[0]
    bidder = Bidder(checksum_address=bidder_address, registry=test_registry)
    whales = bidder.get_whales()

    # Simulate force refund
    new_whales = whales.copy()
    while new_whales:
        whales.update(new_whales)
        whales = bidder._reduce_bids(whales)
        new_whales = bidder.get_whales()

    bidder_address = testerchain.client.accounts[1]
    bidder = Bidder(checksum_address=bidder_address, registry=test_registry)
    worklock_agent = ContractAgency.get_agent(WorkLockAgent, registry=test_registry)

    receipt = bidder.force_refund()
    assert receipt['status'] == 1
    assert not bidder.get_whales()
    assert not worklock_agent.bidders_checked()

    # Compare off-chain and on-chain calculations
    min_bid = token_economics.worklock_min_allowed_bid
    for whale, bonus in whales.items():
        contract_bid = worklock_agent.get_deposited_eth(whale)
        assert bonus == contract_bid - min_bid


def test_verify_correctness(testerchain, agency, token_economics, test_registry):
    bidder_address = testerchain.client.accounts[0]
    bidder = Bidder(checksum_address=bidder_address, registry=test_registry)
    worklock_agent = ContractAgency.get_agent(WorkLockAgent, registry=test_registry)

    assert not worklock_agent.bidders_checked()
    with pytest.raises(Bidder.ClaimError):
        _receipt = bidder.claim()

    receipts = bidder.verify_bidding_correctness(gas_limit=100000)
    assert worklock_agent.bidders_checked()
    assert worklock_agent.is_claiming_available()
    for iteration, receipt in receipts.items():
        assert receipt['status'] == 1


def test_withdraw_compensation(testerchain, agency, token_economics, test_registry):
    bidder_address = testerchain.client.accounts[12]
    bidder = Bidder(checksum_address=bidder_address, registry=test_registry)
    worklock_agent = ContractAgency.get_agent(WorkLockAgent, registry=test_registry)

    assert worklock_agent.get_available_compensation(checksum_address=bidder_address) > 0
    receipt = bidder.withdraw_compensation()
    assert receipt['status'] == 1
    assert worklock_agent.get_available_compensation(checksum_address=bidder_address) == 0


def test_claim(testerchain, agency, token_economics, test_registry):
    bidder_address = testerchain.client.accounts[11]
    bidder = Bidder(checksum_address=bidder_address, registry=test_registry)
    staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=test_registry)
    worklock_agent = ContractAgency.get_agent(WorkLockAgent, registry=test_registry)

    # Ensure that the bidder is not staking.
    locked_tokens = staking_agent.get_locked_tokens(staker_address=bidder.checksum_address, periods=10)
    assert locked_tokens == 0

    receipt = bidder.claim()
    assert receipt['status'] == 1

    # Cant claim more than once
    with pytest.raises(Bidder.ClaimError):
        _receipt = bidder.claim()

    assert bidder.get_deposited_eth > token_economics.worklock_min_allowed_bid
    assert bidder.completed_work == 0
    assert bidder.remaining_work <= token_economics.maximum_allowed_locked // 2
    assert bidder.refunded_work == 0

    # Ensure that the claimant is now the holder of an unbonded stake.
    locked_tokens = staking_agent.get_locked_tokens(staker_address=bidder.checksum_address, periods=10)
    assert locked_tokens <= token_economics.maximum_allowed_locked

    # Confirm the stake is unbonded
    worker_address = staking_agent.get_worker_from_staker(staker_address=bidder.checksum_address)
    assert worker_address == NULL_ADDRESS
