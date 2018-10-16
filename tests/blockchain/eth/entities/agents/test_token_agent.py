import pytest
from eth_tester.exceptions import TransactionFailed

from nucypher.blockchain.eth.agents import NucypherTokenAgent
from nucypher.blockchain.eth.constants import TOKEN_SATURATION, MIN_ALLOWED_LOCKED
from nucypher.blockchain.eth.deployers import NucypherTokenDeployer


@pytest.fixture(scope='module')
def agent(testerchain):
    origin, *everybody_else = testerchain.interface.w3.eth.accounts
    token_deployer = NucypherTokenDeployer(blockchain=testerchain, deployer_address=origin)
    token_deployer.arm()
    token_deployer.deploy()
    token_agent = token_deployer.make_agent()
    return token_agent


def test_token_properties(agent):
    testerchain = agent.blockchain

    # Internal
    assert 'NuCypher' == agent.contract.functions.name().call()
    assert 18 == agent.contract.functions.decimals().call()
    assert 'NU' == agent.contract.functions.symbol().call()

    # Cannot transfer any ETH to token contract
    with pytest.raises((TransactionFailed, ValueError)):
        origin = testerchain.interface.w3.eth.coinbase
        payload = {'from': origin, 'to': agent.contract_address, 'value': 1}
        tx = testerchain.interface.w3.eth.sendTransaction(payload)
        testerchain.wait_for_receipt(tx)

    assert len(agent.contract_address) == 42
    assert agent.contract.address == agent.contract_address
    assert agent.contract_name == NucypherTokenAgent.principal_contract_name
    assert agent._upgradeable is False


def test_get_balance(agent):
    testerchain = agent.blockchain
    deployer, someone, *everybody_else = testerchain.interface.w3.eth.accounts
    balance = agent.get_balance(address=someone)
    assert balance == 0
    balance = agent.get_balance(address=deployer)
    assert balance == TOKEN_SATURATION


def test_approve_transfer(agent):
    testerchain = agent.blockchain
    deployer, someone, *everybody_else = testerchain.interface.w3.eth.accounts

    # Approve
    txhash = agent.approve_transfer(amount=MIN_ALLOWED_LOCKED,
                                    target_address=agent.contract_address,
                                    sender_address=someone)

    # Check the receipt for the contract address success code
    receipt = testerchain.wait_for_receipt(txhash)
    assert receipt['status'] == 1, "Transaction Rejected"
    assert receipt['logs'][0]['address'] == agent.contract_address


def test_transfer(agent):
    testerchain = agent.blockchain
    origin, someone, *everybody_else = testerchain.interface.w3.eth.accounts

    old_balance = agent.get_balance(someone)
    txhash = agent.transfer(amount=MIN_ALLOWED_LOCKED,
                            target_address=someone,
                            sender_address=origin)

    # Check the receipt for the contract address success code
    receipt = testerchain.wait_for_receipt(txhash)
    assert receipt['status'] == 1, "Transaction Rejected"
    assert receipt['logs'][0]['address'] == agent.contract_address

    new_balance = agent.get_balance(someone)
    assert new_balance == old_balance + MIN_ALLOWED_LOCKED

