import pytest
from eth_tester.exceptions import TransactionFailed
from web3 import Web3

from nucypher.blockchain.eth.agents import WorkLockAgent, ContractAgency, NucypherTokenAgent
from nucypher.blockchain.eth.token import NU
from nucypher.crypto.powers import TransactingPower
from nucypher.utilities.sandbox.constants import INSECURE_DEVELOPMENT_PASSWORD

DEPOSIT_RATE = 100


def test_create_worklock_agent(testerchain, test_registry, agency, token_economics):
    agent = WorkLockAgent(registry=test_registry)
    assert agent.contract_address
    same_agent = ContractAgency.get_agent(WorkLockAgent, registry=test_registry)
    assert agent == same_agent


# def test_bid_before_funding(testerchain, agency, token_economics, test_registry):
#     agent = ContractAgency.get_agent(WorkLockAgent, registry=test_registry)
#     big_bidder = testerchain.unassigned_accounts[-1]
#     receipt = agent.bid(sender_address=big_bidder, eth_amount=int(Web3.fromWei(1, 'ether')))
#     assert receipt['status'] == 1


def test_funding_worklock_contract(testerchain, agency, test_registry, token_economics):
    transacting_power = TransactingPower(account=testerchain.etherbase_account, password=INSECURE_DEVELOPMENT_PASSWORD)
    transacting_power.activate()

    worklock_agent = ContractAgency.get_agent(WorkLockAgent, registry=test_registry)

    # WorkLock contract is unfunded.
    token_agent = ContractAgency.get_agent(NucypherTokenAgent, registry=test_registry)
    assert token_agent.get_balance(worklock_agent.contract_address) == 0

    # Funding account has enough tokens to fund the contract.
    worklock_supply = NU.from_nunits(2 * token_economics.maximum_allowed_locked - 1)
    assert token_agent.get_balance(testerchain.etherbase_account) > token_economics.maximum_allowed_locked

    # Fund.
    receipt = worklock_agent.fund(sender_address=testerchain.etherbase_account,
                                  supply=worklock_supply)
    assert receipt['status'] == 1


def test_bidding_post_funding(testerchain, agency, token_economics, test_registry):
    maximum_deposit_eth = token_economics.maximum_allowed_locked // DEPOSIT_RATE
    minimum_deposit_eth = token_economics.minimum_allowed_locked // DEPOSIT_RATE

    agent = ContractAgency.get_agent(WorkLockAgent, registry=test_registry)

    # Round 1
    for multiplier, bidder in enumerate(testerchain.unassigned_accounts[:3], start=1):
        bid = minimum_deposit_eth * multiplier
        receipt = agent.bid(sender_address=bidder, eth_amount=bid)
        assert receipt['status'] == 1

    # Round 2
    for multiplier, bidder in enumerate(testerchain.unassigned_accounts[:3], start=1):
        bid = (minimum_deposit_eth * 2) * multiplier
        receipt = agent.bid(sender_address=bidder, eth_amount=bid)
        assert receipt['status'] == 1

    big_bidder = testerchain.unassigned_accounts[-1]
    bid_wei = maximum_deposit_eth - 1
    receipt = agent.bid(sender_address=big_bidder, eth_amount=bid_wei)
    assert receipt['status'] == 1


def test_get_remaining_work_before_bidding_ends(testerchain, agency, token_economics, test_registry):
    agent = ContractAgency.get_agent(WorkLockAgent, registry=test_registry)
    bidder = testerchain.unassigned_accounts[-1]
    remaining = agent.get_remaining_work(target_address=bidder)
    assert remaining == 0


def test_early_claim(testerchain, agency, token_economics, test_registry):
    agent = ContractAgency.get_agent(WorkLockAgent, registry=test_registry)
    bidder = testerchain.unassigned_accounts[-1]
    with pytest.raises(TransactionFailed):
        receipt = agent.claim(sender_address=bidder)
        assert receipt


def test_refund_before_bidding_ends(testerchain, agency, token_economics, test_registry):
    agent = ContractAgency.get_agent(WorkLockAgent, registry=test_registry)
    bidder = testerchain.unassigned_accounts[-1]
    with pytest.raises(TransactionFailed):
        _receipt = agent.refund(sender_address=bidder)


def test_successful_claim(testerchain, agency, token_economics, test_registry):
    # Wait exactly 1 hour + 1 second
    testerchain.time_travel(seconds=(60*60)+1)

    agent = ContractAgency.get_agent(WorkLockAgent, registry=test_registry)
    bidder = testerchain.unassigned_accounts[-1]
    receipt = agent.claim(sender_address=bidder)
    assert receipt

