import pytest
import rlp
from eth_tester.exceptions import TransactionFailed
from eth_utils import to_canonical_address, keccak, to_checksum_address

from nucypher.blockchain.eth.agents import WorkLockAgent, ContractAgency, NucypherTokenAgent
from nucypher.blockchain.eth.token import NU
from nucypher.crypto.powers import TransactingPower
from nucypher.utilities.sandbox.constants import INSECURE_DEVELOPMENT_PASSWORD

DEPOSIT_RATE = 100


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
        receipt = agent.bid(sender_address=bidder, value=bid)
        assert receipt['status'] == 1

    # Round 2
    for multiplier, bidder in enumerate(testerchain.unassigned_accounts[:3], start=1):
        bid = (minimum_deposit_eth * 2) * multiplier
        receipt = agent.bid(sender_address=bidder, value=bid)
        assert receipt['status'] == 1

    big_bidder = testerchain.unassigned_accounts[-1]
    bid_wei = maximum_deposit_eth - 1
    receipt = agent.bid(sender_address=big_bidder, value=bid_wei)
    assert receipt['status'] == 1


def test_get_remaining_work_before_bidding_ends(testerchain, agency, token_economics, test_registry):
    agent = ContractAgency.get_agent(WorkLockAgent, registry=test_registry)
    preallocation_address = next_address(testerchain, agent.contract)
    remaining = agent.get_remaining_work(allocation_address=preallocation_address)
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
    allocation_address = next_address(testerchain, agent.contract)
    with pytest.raises(TransactionFailed):
        _receipt = agent.refund(sender_address=bidder, allocation_address=allocation_address)


def test_successful_claim(testerchain, agency, token_economics, test_registry):
    # Wait exactly 1 hour + 1 second
    testerchain.time_travel(seconds=(60*60)+1)

    agent = ContractAgency.get_agent(WorkLockAgent, registry=test_registry)
    bidder = testerchain.unassigned_accounts[-1]
    receipt = agent.claim(sender_address=bidder)
    assert receipt


def test_get_remaining_work(testerchain, agency, token_economics, test_registry):
    agent = ContractAgency.get_agent(WorkLockAgent, registry=test_registry)
    bidder = testerchain.unassigned_accounts[-1]
    receipt = agent.claim(sender_address=bidder)
    agent = ContractAgency.get_agent(WorkLockAgent, registry=test_registry)
    preallocation_address = next_address(testerchain, agent.contract)
    remaining_work = agent.get_remaining_work(allocation_address=preallocation_address)
    assert remaining_work
