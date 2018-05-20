import pytest
from eth_tester.exceptions import TransactionFailed


def test_create_token(web3, chain):
    """
    These are tests for standard tokens taken from Consensys github:
    https://github.com/ConsenSys/Tokens/
    but some of the tests are converted from javascript to python
    """

    creator = web3.eth.accounts[0]
    account1 = web3.eth.accounts[1]
    account2 = web3.eth.accounts[2]

    # Create an ERC20 token
    token, txhash = chain.provider.deploy_contract('NuCypherToken', 10 ** 9)
    assert txhash is not None

    # Account balances
    assert 10 ** 9 == token.functions.balanceOf(creator).call()
    assert 0 == token.functions.balanceOf(account1).call()

    # Basic properties
    assert 'NuCypher' == token.functions.name().call()
    assert 18 == token.functions.decimals().call()
    assert 'NU' == token.functions.symbol().call()

    # Cannot send ethers to the contract
    with pytest.raises((TransactionFailed, ValueError)):
        tx = web3.eth.sendTransaction({'from': account1, 'to': token.address, 'value': 10 ** 9})
        chain.wait_for_receipt(tx)

    # Can transfer tokens
    tx = token.functions.transfer(account1, 10000).transact({'from': creator})
    chain.wait_for_receipt(tx)
    assert 10000 == token.functions.balanceOf(account1).call()
    assert 10 ** 9 - 10000 == token.functions.balanceOf(creator).call()

    tx = token.functions.transfer(account2, 10).transact({'from': account1})
    chain.wait_for_receipt(tx)
    assert 10000 - 10 == token.functions.balanceOf(account1).call()
    assert 10 == token.functions.balanceOf(account2).call()

    tx = token.functions.transfer(token.address, 10).transact({'from': account1})
    chain.wait_for_receipt(tx)
    assert 10 == token.functions.balanceOf(token.address).call()

    # Can burn own tokens
    tx = token.functions.burn(1).transact({'from': account2})
    chain.wait_for_receipt(tx)
    assert 9 == token.functions.balanceOf(account2).call()
    assert 10 ** 9 - 1 == token.functions.totalSupply().call()


def test_approve_and_call(web3, chain):
    creator = web3.eth.accounts[0]
    account1 = web3.eth.accounts[1]
    account2 = web3.eth.accounts[2]

    token, _ = chain.provider.deploy_contract('NuCypherToken', 10 ** 9)
    mock, _ = chain.provider.deploy_contract('ReceiveApprovalMethodMock')

    tx = token.functions.approve(account1, 100).transact({'from': creator})
    chain.wait_for_receipt(tx)
    assert 100 == token.functions.allowance(creator, account1).call()
    assert 0 == token.functions.allowance(creator, account2).call()
    assert 0 == token.functions.allowance(account1, creator).call()
    assert 0 == token.functions.allowance(account1, account2).call()
    assert 0 == token.functions.allowance(account2, account1).call()

    tx = token.functions.transferFrom(creator, account2, 50).transact({'from': account1})
    chain.wait_for_receipt(tx)
    assert 50 == token.functions.balanceOf(account2).call()
    assert 50 == token.functions.allowance(creator, account1).call()

    tx = token.functions.approveAndCall(mock.address, 25, web3.toBytes(111)).transact({'from': account1})
    chain.wait_for_receipt(tx)
    assert 50 == token.functions.balanceOf(account2).call()
    assert 50 == token.functions.allowance(creator, account1).call()
    assert 25 == token.functions.allowance(account1, mock.address).call()
    assert account1 == mock.functions.sender().call()
    assert 25 == mock.functions.value().call()
    assert token.address == mock.functions.tokenContract().call()
    assert 111 == web3.toInt(mock.functions.extraData().call())
