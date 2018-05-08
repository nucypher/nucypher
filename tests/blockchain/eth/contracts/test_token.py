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
    token, txhash = chain.provider.deploy_contract('NuCypherKMSToken', 10 ** 9)
    assert txhash is not None

    # Account balances
    assert token.functions.balanceOf(creator).call() == 10 ** 9
    assert token.functions.balanceOf(account1).call() == 0

    # Basic properties
    assert token.functions.name().call() == 'NuCypher KMS'
    assert token.functions.decimals().call() == 18
    assert token.functions.symbol().call() == 'KMS'

    # Cannot send ethers to the contract
    with pytest.raises((TransactionFailed, ValueError)):
        tx = web3.eth.sendTransaction({'from': account1, 'to': token.address, 'value': 10 ** 9})
        chain.wait_for_receipt(tx)

    # Can transfer tokens
    tx =  token.functions.transfer(account1, 10000).transact({'from': creator})
    chain.wait_for_receipt(tx)
    assert token.functions.balanceOf(account1).call() == 10000
    assert token.functions.balanceOf(creator).call() == 10 ** 9 - 10000

    tx =  token.functions.transfer(account2, 10).transact({'from': account1})
    chain.wait_for_receipt(tx)
    assert token.functions.balanceOf(account1).call() == 10000 - 10
    assert token.functions.balanceOf(account2).call() == 10

    tx =  token.functions.transfer(token.address, 10).transact({'from': account1})
    chain.wait_for_receipt(tx)
    assert token.functions.balanceOf(token.address).call() == 10

    # Can burn own tokens
    tx =  token.functions.burn(1).transact({'from': account2})
    chain.wait_for_receipt(tx)
    assert token.functions.balanceOf(account2).call() == 9
    assert token.functions.totalSupply().call() == 10 ** 9 - 1
