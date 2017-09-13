import pytest
from ethereum.tester import TransactionFailed


def test_create_token(web3, chain):
    creator = web3.eth.accounts[1]
    account1 = web3.eth.accounts[0]

    # Create an ERC20 token
    token, txhash = chain.provider.get_or_deploy_contract(
            'HumanStandardToken', deploy_args=[
                10 ** 9, 'NuCypher KMS', 6, 'KMS'],
            deploy_transaction={
                'from': creator})
    assert txhash is not None

    # Account balances
    assert token.call().balanceOf(creator) == 10 ** 9
    assert token.call().balanceOf(account1) == 0

    # Basic properties
    assert token.call().name() == 'NuCypher KMS'
    assert token.call().decimals() == 6
    assert token.call().symbol() == 'KMS'

    # Cannot send ethers to the contract
    with pytest.raises(TransactionFailed):
        tx = web3.eth.sendTransaction({
            'from': account1, 'to': token.address, 'value': 10 ** 9})
        chain.wait.for_receipt(tx)

    # Can transfer tokens
    tx = token.transact({'from': creator}).transfer(account1, 10000)
    chain.wait.for_receipt(tx)
    assert token.call().balanceOf(account1) == 10000
    assert token.call().balanceOf(creator) == 10 ** 9 - 10000
