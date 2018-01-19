import pytest
from ethereum.tester import TransactionFailed


@pytest.fixture()
def token(web3, chain):
    creator = web3.eth.accounts[0]
    # Create an ERC20 token
    token, _ = chain.provider.get_or_deploy_contract(
        'NuCypherKMSToken', deploy_args=[10 ** 30, 2 * 10 ** 40],
        deploy_transaction={'from': creator})
    return token


def test_miner(web3, chain, token):
    creator = web3.eth.accounts[0]
    ursula = web3.eth.accounts[1]

    # Creator deploys the miner
    miner, _ = chain.provider.get_or_deploy_contract(
        'MinerTest', deploy_args=[token.address, 1, 10 ** 46, 10 ** 7, 10 ** 7],
        deploy_transaction={'from': creator})

    # Give rights for mining
    tx = token.transact({'from': creator}).addMiner(miner.address)
    chain.wait.for_receipt(tx)

    # Mint some tokens
    tx = miner.transact().testMint(ursula, 0, 1000, 2000, 0, 0)
    chain.wait.for_receipt(tx)
    assert 10 == token.call().balanceOf(ursula)
    assert 10 ** 30 + 10 == token.call().totalSupply()

    # Mint more tokens
    tx = miner.transact().testMint(ursula, 0, 500, 500, 0, 0)
    chain.wait.for_receipt(tx)
    assert 30 == token.call().balanceOf(ursula)
    assert 10 ** 30 + 30 == token.call().totalSupply()

    tx = miner.transact().testMint(ursula, 0, 500, 500, 10 ** 7, 0)
    chain.wait.for_receipt(tx)
    assert 70 == token.call().balanceOf(ursula)
    assert 10 ** 30 + 70 == token.call().totalSupply()

    tx = miner.transact().testMint(ursula, 0, 500, 500, 2 * 10 ** 7, 0)
    chain.wait.for_receipt(tx)
    assert 110 == token.call().balanceOf(ursula)
    assert 10 ** 30 + 110 == token.call().totalSupply()
