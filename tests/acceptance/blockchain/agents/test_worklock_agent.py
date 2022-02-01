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

from nucypher.blockchain.eth.signers.software import Web3Signer
from nucypher.crypto.powers import TransactingPower
from nucypher.blockchain.eth.agents import ContractAgency, StakingEscrowAgent, WorkLockAgent
from nucypher.blockchain.eth.interfaces import BlockchainInterface


@pytest.mark.skip()
def test_create_worklock_agent(testerchain, test_registry, agency, token_economics):
    agent = WorkLockAgent(registry=test_registry)
    assert agent.contract_address
    same_agent = ContractAgency.get_agent(WorkLockAgent, registry=test_registry)
    assert agent == same_agent
    assert not agent.is_claiming_available()


@pytest.mark.skip()
def test_bidding(testerchain, agency, token_economics, test_registry):
    small_bid = token_economics.worklock_min_allowed_bid
    big_bid = 5 * token_economics.worklock_min_allowed_bid
    agent = ContractAgency.get_agent(WorkLockAgent, registry=test_registry)

    # Round 1
    for multiplier, bidder in enumerate(testerchain.client.accounts[:11], start=1):
        bid = big_bid * multiplier
        tpower = TransactingPower(account=bidder, signer=Web3Signer(testerchain.client))
        receipt = agent.bid(transacting_power=tpower, value=bid)
        assert receipt['status'] == 1

    # Round 2
    for multiplier, bidder in enumerate(testerchain.client.accounts[:11], start=1):
        bid = (small_bid * 2) * multiplier
        tpower = TransactingPower(account=bidder, signer=Web3Signer(testerchain.client))
        receipt = agent.bid(transacting_power=tpower, value=bid)
        assert receipt['status'] == 1


@pytest.mark.skip()
def test_get_deposited_eth(testerchain, agency, token_economics, test_registry):
    small_bid = token_economics.worklock_min_allowed_bid
    small_bidder = testerchain.client.accounts[-1]
    tpower = TransactingPower(account=small_bidder, signer=Web3Signer(testerchain.client))
    agent = ContractAgency.get_agent(WorkLockAgent, registry=test_registry)
    receipt = agent.bid(transacting_power=tpower, value=small_bid)
    assert receipt['status'] == 1
    bid = agent.get_deposited_eth(small_bidder)
    assert bid == small_bid


@pytest.mark.skip()
def test_get_base_deposit_rate(agency, token_economics, test_registry):
    agent = ContractAgency.get_agent(WorkLockAgent, registry=test_registry)
    base_deposit_rate = agent.get_base_deposit_rate()
    assert base_deposit_rate == token_economics.minimum_allowed_locked / token_economics.worklock_min_allowed_bid


@pytest.mark.skip()
def test_get_base_refund_rate(testerchain, agency, token_economics, test_registry):
    agent = ContractAgency.get_agent(WorkLockAgent, registry=test_registry)
    base_refund_rate = agent.get_base_refund_rate()

    slowing_refund = agent.contract.functions.SLOWING_REFUND().call()
    assert base_refund_rate == (token_economics.minimum_allowed_locked / token_economics.worklock_min_allowed_bid) * \
           (slowing_refund / token_economics.worklock_boosting_refund_rate)


@pytest.mark.skip()
def test_cancel_bid(testerchain, agency, token_economics, test_registry):
    bidder = testerchain.client.accounts[1]
    agent = ContractAgency.get_agent(WorkLockAgent, registry=test_registry)
    tpower = TransactingPower(account=bidder, signer=Web3Signer(testerchain.client))

    assert agent.get_deposited_eth(bidder)        # Bid
    receipt = agent.cancel_bid(transacting_power=tpower)  # Cancel
    assert receipt['status'] == 1
    assert not agent.get_deposited_eth(bidder)    # No more bid

    # Can't cancel a bid twice in a row
    with pytest.raises((TransactionFailed, ValueError)):
        _receipt = agent.cancel_bid(transacting_power=tpower)


@pytest.mark.skip()
def test_get_remaining_work(testerchain, agency, token_economics, test_registry):
    agent = ContractAgency.get_agent(WorkLockAgent, registry=test_registry)
    bidder = testerchain.client.accounts[0]
    remaining = agent.get_remaining_work(checksum_address=bidder)
    assert remaining > 0


@pytest.mark.skip()
def test_early_claim(testerchain, agency, token_economics, test_registry):
    agent = ContractAgency.get_agent(WorkLockAgent, registry=test_registry)
    bidder = testerchain.client.accounts[0]
    tpower = TransactingPower(account=bidder, signer=Web3Signer(testerchain.client))
    with pytest.raises(TransactionFailed):
        _receipt = agent.claim(transacting_power=tpower)


@pytest.mark.skip()
def test_cancel_after_bidding(testerchain, agency, token_economics, test_registry):

    # Wait until the bidding window closes...
    testerchain.time_travel(seconds=token_economics.bidding_duration+1)

    bidder = testerchain.client.accounts[0]
    tpower = TransactingPower(account=bidder, signer=Web3Signer(testerchain.client))

    agent = ContractAgency.get_agent(WorkLockAgent, registry=test_registry)

    assert agent.get_deposited_eth(bidder)        # Bid
    receipt = agent.cancel_bid(transacting_power=tpower)  # Cancel
    assert receipt['status'] == 1
    assert not agent.get_deposited_eth(bidder)    # No more bid


@pytest.mark.skip()
def test_claim_before_checking(testerchain, agency, token_economics, test_registry):
    agent = ContractAgency.get_agent(WorkLockAgent, registry=test_registry)
    bidder = testerchain.client.accounts[2]
    tpower = TransactingPower(account=bidder, signer=Web3Signer(testerchain.client))

    assert not agent.is_claiming_available()
    with pytest.raises(TransactionFailed):
        _receipt = agent.claim(transacting_power=tpower)

    # Wait until the cancellation window closes...
    testerchain.time_travel(seconds=token_economics.cancellation_end_date+1)

    assert not agent.is_claiming_available()
    with pytest.raises(TransactionFailed):
        _receipt = agent.claim(transacting_power=tpower)


@pytest.mark.skip()
def test_force_refund(testerchain, agency, token_economics, test_registry):
    agent = ContractAgency.get_agent(WorkLockAgent, registry=test_registry)
    caller = testerchain.client.accounts[0]
    tpower = TransactingPower(account=caller, signer=Web3Signer(testerchain.client))

    with pytest.raises(BlockchainInterface.InterfaceError):
        _receipt = agent.verify_bidding_correctness(transacting_power=tpower, gas_limit=100000)

    receipt = agent.force_refund(transacting_power=tpower, addresses=testerchain.client.accounts[2:11])
    assert receipt['status'] == 1
    assert agent.get_available_compensation(testerchain.client.accounts[2]) > 0


@pytest.mark.skip()
def test_verify_correctness(testerchain, agency, token_economics, test_registry):
    agent = ContractAgency.get_agent(WorkLockAgent, registry=test_registry)  # type: WorkLockAgent
    caller = testerchain.client.accounts[0]
    tpower = TransactingPower(account=caller, signer=Web3Signer(testerchain.client))
    assert not agent.bidders_checked()
    assert agent.estimate_verifying_correctness(gas_limit=100000) == 10
    receipt = agent.verify_bidding_correctness(transacting_power=tpower, gas_limit=100000)
    assert receipt['status'] == 1
    assert agent.bidders_checked()
    assert agent.is_claiming_available()


@pytest.mark.skip()
def test_withdraw_compensation(testerchain, agency, token_economics, test_registry):
    agent = ContractAgency.get_agent(WorkLockAgent, registry=test_registry)
    bidder = testerchain.client.accounts[2]
    tpower = TransactingPower(account=bidder, signer=Web3Signer(testerchain.client))
    balance = testerchain.w3.eth.getBalance(bidder)
    receipt = agent.withdraw_compensation(transacting_power=tpower)
    assert receipt['status'] == 1
    assert testerchain.w3.eth.getBalance(bidder) > balance
    assert agent.get_available_compensation(testerchain.client.accounts[2]) == 0


@pytest.mark.skip()
def test_successful_claim(testerchain, agency, token_economics, test_registry):

    agent = ContractAgency.get_agent(WorkLockAgent, registry=test_registry)
    staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=test_registry)

    bidder = testerchain.client.accounts[2]
    tpower = TransactingPower(account=bidder, signer=Web3Signer(testerchain.client))

    # Ensure that the bidder is not staking.
    locked_tokens = staking_agent.get_locked_tokens(staker_address=bidder, periods=5)
    assert locked_tokens == 0

    receipt = agent.claim(transacting_power=tpower)
    assert receipt['status'] == 1

    # Cant claim more than once
    with pytest.raises(TransactionFailed):
        _receipt = agent.claim(transacting_power=tpower)

    # Ensure that the claimant is now the holder of a stake.
    locked_tokens = staking_agent.get_locked_tokens(staker_address=bidder, periods=5)
    assert locked_tokens > 0
