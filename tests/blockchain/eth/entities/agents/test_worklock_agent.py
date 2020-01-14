import pytest
import rlp
from eth_tester.exceptions import TransactionFailed
from eth_utils import to_canonical_address, keccak, to_checksum_address

from nucypher.blockchain.eth.agents import WorkLockAgent, ContractAgency


def next_address(testerchain, worklock):
    # https://github.com/ethereum/wiki/wiki/Subtleties#nonces
    nonce = testerchain.w3.eth.getTransactionCount(worklock.address)
    data_to_encode = [to_canonical_address(worklock.address), nonce]
    return to_checksum_address(keccak(rlp.codec.encode(data_to_encode))[12:])


def test_create_worklock_agent(testerchain, test_registry, agency, token_economics):
    agent = WorkLockAgent(registry=test_registry)
    assert agent.contract_address
    same_agent = ContractAgency.get_agent(WorkLockAgent, registry=test_registry)
    assert agent == same_agent


def test_bidding(testerchain, agency, token_economics, test_registry):
    big_bid = token_economics.maximum_allowed_locked // 100
    small_bid = token_economics.minimum_allowed_locked // 100

    agent = ContractAgency.get_agent(WorkLockAgent, registry=test_registry)

    # Round 1
    for multiplier, bidder in enumerate(testerchain.unassigned_accounts[:3], start=1):
        bid = big_bid * multiplier
        receipt = agent.bid(bidder_address=bidder, value=bid)
        assert receipt['status'] == 1

    # Round 2
    for multiplier, bidder in enumerate(testerchain.unassigned_accounts[:3], start=1):
        bid = (small_bid * 2) * multiplier
        receipt = agent.bid(bidder_address=bidder, value=bid)
        assert receipt['status'] == 1


def test_get_bid(testerchain, agency, token_economics, test_registry):
    big_bid = token_economics.maximum_allowed_locked // 10
    big_bidder = testerchain.unassigned_accounts[-1]
    agent = ContractAgency.get_agent(WorkLockAgent, registry=test_registry)
    receipt = agent.bid(bidder_address=big_bidder, value=big_bid)
    assert receipt['status'] == 1
    bid = agent.get_bid(big_bidder)
    assert bid == big_bid


def test_cancel_bid(testerchain, agency, token_economics, test_registry):
    bidder = testerchain.unassigned_accounts[1]
    agent = ContractAgency.get_agent(WorkLockAgent, registry=test_registry)
    receipt = agent.cancel_bid(bidder)
    assert receipt['status'] == 1
    # Can't cancel a bid twice in a row
    with pytest.raises((TransactionFailed, ValueError)):
        _receipt = agent.cancel_bid(bidder)


def test_get_remaining_work(testerchain, agency, token_economics, test_registry):
    agent = ContractAgency.get_agent(WorkLockAgent, registry=test_registry)
    bidder = testerchain.unassigned_accounts[0]
    remaining = agent.get_remaining_work(bidder_address=bidder)
    assert remaining == 35905203136136849607983


def test_early_claim(testerchain, agency, token_economics, test_registry):
    agent = ContractAgency.get_agent(WorkLockAgent, registry=test_registry)
    bidder = testerchain.unassigned_accounts[0]
    with pytest.raises(TransactionFailed):
        receipt = agent.claim(bidder_address=bidder)
        assert receipt


def test_successful_claim(testerchain, agency, token_economics, test_registry):

    # Wait until the bidding window closes...
    testerchain.time_travel(seconds=token_economics.bidding_duration+1)

    agent = ContractAgency.get_agent(WorkLockAgent, registry=test_registry)
    bidder = testerchain.unassigned_accounts[0]
    receipt = agent.claim(bidder_address=bidder)
    assert receipt

    # Cant claim more than once
    with pytest.raises(TransactionFailed):
        _receipt = agent.claim(bidder_address=bidder)
