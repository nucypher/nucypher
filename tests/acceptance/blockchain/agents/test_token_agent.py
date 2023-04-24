


import pytest
from eth_tester.exceptions import TransactionFailed

from nucypher.blockchain.eth.agents import NucypherTokenAgent, ContractAgency
from nucypher.blockchain.eth.signers.software import Web3Signer
from nucypher.crypto.powers import TransactingPower


@pytest.fixture(scope='module')
def agent(testerchain, test_registry) -> NucypherTokenAgent:
    token_agent = ContractAgency.get_agent(NucypherTokenAgent, registry=test_registry)
    return token_agent


@pytest.mark.skip()
def test_token_properties(agent):
    testerchain = agent.blockchain

    # Internal
    assert 'NuCypher' == agent.contract.functions.name().call()
    assert 18 == agent.contract.functions.decimals().call()
    assert 'NU' == agent.contract.functions.symbol().call()

    # Cannot transfer any ETH to token contract
    with pytest.raises((TransactionFailed, ValueError)):
        origin = testerchain.client.coinbase
        payload = {'from': origin, 'to': agent.contract_address, 'value': 1}
        tx = testerchain.client.send_transaction(payload)
        testerchain.wait_for_receipt(tx)

    assert len(agent.contract_address) == 42
    assert agent.contract.address == agent.contract_address
    assert agent.contract_name == NucypherTokenAgent.contract_name
    assert not agent._proxy_name  # not upgradeable


@pytest.mark.skip()
def test_get_balance(agent, application_economics):
    testerchain = agent.blockchain
    deployer, someone, *everybody_else = testerchain.client.accounts
    balance = agent.get_balance(address=someone)
    assert balance == 0
    balance = agent.get_balance(address=deployer)
    assert balance == application_economics.erc20_total_supply


@pytest.mark.skip()
def test_approve_transfer(agent, application_economics):
    testerchain = agent.blockchain
    deployer, someone, *everybody_else = testerchain.client.accounts
    tpower = TransactingPower(account=someone, signer=Web3Signer(testerchain.client))

    # Approve
    receipt = agent.approve_transfer(amount=application_economics.min_authorization,
                                     spender_address=agent.contract_address,
                                     transacting_power=tpower)

    assert receipt['status'] == 1, "Transaction Rejected"
    assert receipt['logs'][0]['address'] == agent.contract_address


@pytest.mark.skip()
def test_transfer(agent, application_economics):
    testerchain = agent.blockchain
    origin, someone, *everybody_else = testerchain.client.accounts
    tpower = TransactingPower(account=origin, signer=Web3Signer(testerchain.client))

    old_balance = agent.get_balance(someone)
    receipt = agent.transfer(amount=application_economics.min_authorization,
                             target_address=someone,
                             transacting_power=tpower)

    assert receipt['status'] == 1, "Transaction Rejected"
    assert receipt['logs'][0]['address'] == agent.contract_address

    new_balance = agent.get_balance(someone)
    assert new_balance == old_balance + application_economics.min_authorization


@pytest.mark.skip()
def test_approve_and_call(agent, application_economics, deploy_contract):
    testerchain = agent.blockchain
    deployer, someone, *everybody_else = testerchain.client.accounts

    mock_target, _ = deploy_contract('ReceiveApprovalMethodMock')

    # Approve and call
    tpower = TransactingPower(account=someone, signer=Web3Signer(testerchain.client))
    call_data = b"Good morning, that's a nice tnetennba."
    receipt = agent.approve_and_call(amount=application_economics.min_authorization,
                                     target_address=mock_target.address,
                                     transacting_power=tpower,
                                     call_data=call_data)

    assert receipt['status'] == 1, "Transaction Rejected"
    assert receipt['logs'][0]['address'] == agent.contract_address

    assert mock_target.functions.extraData().call() == call_data
    assert mock_target.functions.sender().call() == someone
    assert mock_target.functions.value().call() == application_economics.min_authorization
