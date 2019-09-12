import pytest
from eth_tester.exceptions import TransactionFailed
from web3 import Web3

from nucypher.blockchain.eth.agents import WorkLockAgent, ContractAgency, NucypherTokenAgent
from nucypher.blockchain.eth.deployers import WorkLockDeployer
from nucypher.blockchain.eth.interfaces import BlockchainInterface
from nucypher.crypto.powers import TransactingPower
from nucypher.utilities.sandbox.constants import INSECURE_DEVELOPMENT_PASSWORD


@pytest.fixture(scope="module", autouse=True)
def deploy_worklock(testerchain, agency, test_registry, token_economics):
    deployer = WorkLockDeployer(registry=test_registry,
                                deployer_address=testerchain.etherbase_account,
                                economics=token_economics)
    _deployment_receipts = deployer.deploy()
    return deployer


def test_create_worklock_agent(testerchain, test_registry, agency, token_economics, deploy_worklock):
    agent = WorkLockAgent(registry=test_registry)
    assert agent.contract_address
    same_agent = ContractAgency.get_agent(WorkLockAgent, registry=test_registry)
    assert agent == same_agent


def test_bid_rejection_before_funding(testerchain, agency, token_economics, test_registry):
    agent = ContractAgency.get_agent(WorkLockAgent, registry=test_registry)
    big_bidder = testerchain.unassigned_accounts[-1]
    with pytest.raises(TransactionFailed):
        _receipt = agent.bid(sender_address=big_bidder, value=int(Web3.fromWei(1, 'ether')))


def test_funding_worklock_contract(testerchain, agency, test_registry, token_economics, deploy_worklock):
    deployer = deploy_worklock
    assert deployer.contract_address
    assert deployer.contract_address is not BlockchainInterface.NULL_ADDRESS

    transacting_power = TransactingPower(account=testerchain.etherbase_account, password=INSECURE_DEVELOPMENT_PASSWORD)
    transacting_power.activate()

    # WorkLock contract is unfunded.
    token_agent = ContractAgency.get_agent(NucypherTokenAgent, registry=test_registry)
    assert token_agent.get_balance(deployer.contract_address) == 0

    # Funding account has enough tokens to fund the contract.
    assert token_agent.get_balance(testerchain.etherbase_account) > token_economics.maximum_allowed_locked

    # Fund.
    receipt = deployer.fund(sender_address=testerchain.etherbase_account)
    assert receipt['status'] == 1


def test_bidding(testerchain, agency, test_registry, token_economics, deploy_worklock):

    agent = ContractAgency.get_agent(WorkLockAgent, registry=test_registry)

    # Round 1
    for multiplier, bidder in enumerate(testerchain.unassigned_accounts[:3], start=1):
        bid = token_economics.minimum_bid * multiplier
        receipt = agent.bid(sender_address=bidder, value=bid)
        assert receipt['status'] == 1

    # Round 2
    for multiplier, bidder in enumerate(testerchain.unassigned_accounts[:3], start=1):
        bid = (token_economics.minimum_bid * 2) * multiplier
        receipt = agent.bid(sender_address=bidder, value=bid)
        assert receipt['status'] == 1

    big_bidder = testerchain.unassigned_accounts[-1]
    bid_wei = token_economics.maximum_bid - 1
    receipt = agent.bid(sender_address=big_bidder, value=bid_wei)
    assert receipt['status'] == 1


def test_get_remaining_work(testerchain, agency, token_economics, test_registry):
    agent = ContractAgency.get_agent(WorkLockAgent, registry=test_registry)
    bidder = testerchain.unassigned_accounts[-1]
    remaining = agent.get_remaining_work(target_address=bidder)
    assert remaining


def test_claim(testerchain, agency, token_economics, test_registry):
    testerchain.time_travel(seconds=(60*60)+1)  # Wait exactly 1 hour + 1 second
    agent = ContractAgency.get_agent(WorkLockAgent, registry=test_registry)
    bidder = testerchain.unassigned_accounts[-1]
    receipt = agent.claim(sender_address=bidder)
    assert receipt


def test_refund_rejection_without_work(testerchain, agency, token_economics, test_registry):
    agent = ContractAgency.get_agent(WorkLockAgent, registry=test_registry)
    bidder = testerchain.unassigned_accounts[-1]
    with pytest.raises(TransactionFailed):
        _receipt = agent.refund(sender_address=bidder)
