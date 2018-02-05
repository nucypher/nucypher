import random
import pytest


M = 10 ** 6


def airdrop(blockchain, token) -> None:
    """
    Airdrops from accounts[0] to others
    """
    web3 = blockchain.web3
    # token = Token.get(blockchain=blockchain)

    def txs():
        for account in web3.eth.accounts[1:]:
            tx = token.contract.transact({'from': web3.eth.accounts[0]}).transfer(account, 10000*M)
            yield tx

    for tx in txs():
        blockchain.chain.wait.for_receipt(tx, timeout=10)


def test_deposit(testerchain, miner, token):
    airdrop(testerchain, token)
    ursula.lock(amount=1000*M,
                locktime=100,
                address=testerchain.web3.eth.accounts[1])


def test_select_ursulas(testerchain, miner, escrow, token):
    airdrop(testerchain, token)

    # Create a random set of miners (we have 9 in total)
    for u in testerchain.web3.eth.accounts[1:]:
        miner.lock((10 + random.randrange(9000)) * M, 100, u)
        testerchain.wait.for_block(testerchain.web3.eth.blockNumber + escrow.BLOCKS_PER_PERIOD)

    miners = escrow.sample(3)
    assert len(miners) == 3
    assert len(set(miners)) == 3

    with pytest.raises(Exception):
        escrow.sample(100)  # Waay more than we have deployed


def test_mine_withdraw(testerchain, miner, token, escrow):
    airdrop(testerchain, token)

    addr = testerchain.web3.eth.accounts[1]
    initial_balance = token.balance(addr)

    # Create a random set of miners (we have 9 in total)
    for u in testerchain.web3.eth.accounts[1:]:
        miner.lock(amount=(10 + random.randrange(9000))*M,
                    locktime=1,
                    address=u)

        testerchain.chain.wait.for_block(testerchain.web3.eth.blockNumber + 2 * escrow.BLOCKS_PER_PERIOD)

    miner.mine(addr)
    miner.withdraw(addr)
    final_balance = token.balance(addr)

    assert final_balance > initial_balance