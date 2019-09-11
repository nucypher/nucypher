import random

import pytest
from eth_tester.exceptions import TransactionFailed
from web3 import Web3

from nucypher.blockchain.eth.agents import WorkLockAgent, ContractAgency, NucypherTokenAgent
from nucypher.blockchain.eth.deployers import WorkLockDeployer
from nucypher.blockchain.eth.interfaces import BlockchainInterface
from nucypher.blockchain.eth.token import NU
from nucypher.crypto.powers import TransactingPower
from nucypher.utilities.sandbox.constants import INSECURE_DEVELOPMENT_PASSWORD


DEPOSIT_RATE = 100


@pytest.fixture(scope="module", autouse=True)
def deploy_worklock(testerchain, agency, test_registry, token_economics):

    # TODO: Move to "WorkLockEconomics" class #1126
    now = testerchain.w3.eth.getBlock(block_identifier='latest').timestamp
    start_bid_date = now + (60 * 60)  # 1 Hour
    end_bid_date = start_bid_date + (60 * 60)
    deposit_rate = DEPOSIT_RATE
    refund_rate = 200
    locked_periods = 2 * token_economics.minimum_locked_periods

    # Deploy
    deployer = WorkLockDeployer(registry=test_registry,
                                deployer_address=testerchain.etherbase_account,
                                start_date=start_bid_date,
                                end_date=end_bid_date,
                                refund_rate=refund_rate,
                                deposit_rate=deposit_rate,
                                locked_periods=locked_periods)
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
        _receipt = agent.bid(sender_address=big_bidder, eth_amount=int(Web3.fromWei(1, 'ether')))


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
    worklock_supply = 2 * token_economics.maximum_allowed_locked - 1
    assert token_agent.get_balance(testerchain.etherbase_account) > token_economics.maximum_allowed_locked

    # Fund.
    receipt = deployer.fund(sender_address=testerchain.etherbase_account, value=worklock_supply)
    assert receipt['status'] == 1


def test_bidding(testerchain, agency, token_economics, test_registry):
    maximum_deposit_eth = token_economics.maximum_allowed_locked // DEPOSIT_RATE
    minimum_deposit_eth = token_economics.minimum_allowed_locked // DEPOSIT_RATE

    testerchain.time_travel(seconds=3600)  # Wait exactly 1 hour, until bid start time
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
