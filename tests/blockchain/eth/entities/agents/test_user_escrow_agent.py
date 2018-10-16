import os

import pytest
from eth_utils import is_checksum_address

from nucypher.blockchain.eth.agents import UserEscrowAgent
from nucypher.blockchain.eth.constants import MIN_ALLOWED_LOCKED, MIN_LOCKED_PERIODS
from nucypher.blockchain.eth.deployers import UserEscrowDeployer, UserEscrowProxyDeployer


@pytest.fixture(scope='module')
def agent(three_agents, testerchain):
    deployer, someone, *everybody_else = testerchain.interface.w3.eth.accounts
    token_agent, miner_agent, policy_agent = three_agents

    proxy_deployer = UserEscrowProxyDeployer(deployer_address=deployer,
                                          policy_agent=policy_agent,
                                          secret_hash=os.urandom(32))
    assert proxy_deployer.arm()
    proxy_deployer.deploy()

    escrow_deployer = UserEscrowDeployer(policy_agent=policy_agent, deployer_address=deployer)
    assert escrow_deployer.arm()

    _txhash = escrow_deployer.deploy(beneficiary_address=someone)

    _agent = escrow_deployer.make_agent()
    # user_escrow_agent = UserEscrowAgent(policy_agent=policy_agent, beneficiary=someone)
    return _agent


def test_user_escrow_agent_represents_beneficiary(agent):
    assert agent.principal_contract_name == UserEscrowAgent.principal_contract_name
    assert agent != agent.miner_agent, "UserEscrow Agent is connected to the MinerEscrow's contract"
    assert agent.contract_address != agent.miner_agent.contract_address, "UserEscrow and MinerEscrow agents represent the same contract"


def test_read_beneficiary(agent):
    beneficiary_address = agent.beneficiary
    assert is_checksum_address(beneficiary_address)


def test_read_end_timestamp(agent):
    end_timestamp = agent.end_timestamp
    assert end_timestamp


def test_read_allocation(agent):
    allocation = agent.allocation
    assert allocation > 0 < MIN_ALLOWED_LOCKED


def test_initial_deposit(agent):
    testerchain = agent.blockchain
    origin, someone, *everybody_else = testerchain.interface.w3.eth.accounts
    token_agent = agent.token_agent

    _txhash = token_agent.transfer(amount=MIN_ALLOWED_LOCKED * 2,      # Transfer
                                   target_address=someone,
                                   sender_address=origin)

    _txhash = token_agent.approve_transfer(amount=MIN_ALLOWED_LOCKED,  # Approve
                                           target_address=agent.contract_address,
                                           sender_address=someone)

    #
    # Deposit
    #
    txhash = agent.deposit_tokens(amount=MIN_ALLOWED_LOCKED,
                                  lock_periods=MIN_LOCKED_PERIODS,
                                  sender_address=someone)

    # Check the receipt for the contract address success code
    receipt = testerchain.wait_for_receipt(txhash)
    assert receipt['status'] == 1, "Transaction Rejected"
    assert receipt['logs'][1]['address'] == agent.contract_address


def test_withdraw_tokens(agent):
    assert False


def test_withdraw_eth(agent):
    assert False


def test_transfer_as_miner(agent):
    assert False


def test_withdraw_as_miner(agent):
    assert False
