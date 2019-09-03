import pytest
from web3 import Web3

from nucypher.blockchain.eth.agents import WorkLockAgent, ContractAgency
from nucypher.blockchain.eth.deployers import WorkLockDeployer
from nucypher.blockchain.eth.token import NU


@pytest.fixture(scope="module", autouse=True)
def deploy_worklock(testerchain, agency, test_registry, token_economics):

    # TODO: Move to "WorkLockEconomics" class #1126
    now = testerchain.w3.eth.getBlock(block_identifier='latest').timestamp
    start_bid_date = now + (60 * 60)  # 1 Hour
    end_bid_date = start_bid_date + (60 * 60)
    deposit_rate = 100
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


def test_create_worklock_agent(testerchain, test_registry, agency, token_economics, deploy_worklock):
    agent = WorkLockAgent(registry=test_registry)
    assert agent.contract_address
    same_agent = ContractAgency.get_agent(WorkLockAgent, registry=test_registry)
    assert agent == same_agent


def test_bid(testerchain, agency, token_economics, test_registry):
    agent = ContractAgency.get_agent(WorkLockAgent, registry=test_registry)
    big_bidder = testerchain.unassigned_accounts[-1]
    receipt = agent.bid(sender_address=big_bidder,
                        eth_amount=int(Web3.fromWei(1, 'ether')))
    assert receipt


def test_get_remaining_work(testerchain, agency, token_economics, test_registry):
    agent = ContractAgency.get_agent(WorkLockAgent, registry=test_registry)
    bidder = testerchain.unassigned_accounts[-1]
    receipt = agent.get_remaining_work(target_address=bidder)
    assert receipt


def test_claim(testerchain, agency, token_economics, test_registry):
    agent = ContractAgency.get_agent(WorkLockAgent, registry=test_registry)
    bidder = testerchain.unassigned_accounts[-1]
    receipt = agent.claim(sender_address=bidder)
    assert receipt


def test_refund(testerchain, agency, token_economics, test_registry):
    agent = ContractAgency.get_agent(WorkLockAgent, registry=test_registry)
    bidder = testerchain.unassigned_accounts[-1]
    receipt = agent.refund(sender_address=bidder)
    assert receipt

