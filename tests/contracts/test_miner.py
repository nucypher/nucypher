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
        'MinerTest', deploy_args=[token.address, 10 ** 41],
        deploy_transaction={'from': creator})

    # Give rights for mining
    tx = token.transact({'from': creator}).addMiner(miner.address)
    chain.wait.for_receipt(tx)

    # Check reward
    # TODO uncomment or delete
    # assert miner.call().isEmptyReward(100, 100)
    # assert not miner.call().isEmptyReward(1000, 100)

    # # Try to mint using low value
    # TODO uncomment or delete
    # assert miner.call().testMint(ursula, 100, 200, 100, 0) == [0, 0]
    # tx = miner.transact().testMint(ursula, 100, 200, 100, 0)
    # chain.wait.for_receipt(tx)
    # assert token.call().totalSupply() == 10 ** 9
    # assert token.call().balanceOf(ursula) == 0
    # assert miner.call().lastMintedPoint() == 0

    # Mint some tokens
    tx = miner.transact().testMint(ursula, 1000, 2000, 100, 0)
    chain.wait.for_receipt(tx)
    assert 10 == token.call().balanceOf(ursula)
    assert 10 ** 30 + 10 == token.call().totalSupply()

    # Mint more tokens
    tx = miner.transact().testMint(ursula, 500, 500, 200, 0)
    chain.wait.for_receipt(tx)
    assert 50 == token.call().balanceOf(ursula)
    assert 10 ** 30 + 50 == token.call().totalSupply()
