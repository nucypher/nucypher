from nkms_eth import token
from nkms_eth import escrow
from nkms_eth import ursula
import random
import pytest

M = 10 ** 6


def airdrop(chain):
    """
    Airdrops from accounts[0] to others
    """
    web3 = chain.web3
    tok = token.get()
    txs = [
            tok.transact({'from': web3.eth.accounts[0]}).transfer(account, 10000 * M)
            for account in web3.eth.accounts[1:]]
    for tx in txs:
        chain.wait.for_receipt(tx, timeout=10)


def test_deposit(chain):
    token.create()
    escrow.create()
    airdrop(chain)
    ursula.lock(1000 * M, 100, chain.web3.eth.accounts[1])


def test_select_ursulas(chain):
    token.create()
    escrow.create()
    airdrop(chain)

    # Create a random set of miners (we have 9 in total)
    for u in chain.web3.eth.accounts[1:]:
        ursula.lock((10 + random.randrange(9000)) * M, 100, u)
    chain.wait.for_block(chain.web3.eth.blockNumber + 50)

    miners = escrow.sample(3)
    assert len(miners) == 3
    assert len(set(miners)) == 3

    with pytest.raises(Exception):
        escrow.sample(100)  # Waay more than we have deployed


def test_mine_withdraw(chain):
    token.create()
    escrow.create()
    airdrop(chain)

    addr = chain.web3.eth.accounts[1]
    initial_balance = token.balance(addr)

    # Create a random set of miners (we have 9 in total)
    for u in chain.web3.eth.accounts[1:]:
        ursula.lock((10 + random.randrange(9000)) * M, 100, u)

    chain.wait.for_block(chain.web3.eth.blockNumber + 150)

    ursula.mine(addr)
    ursula.withdraw(addr)
    final_balance = token.balance(addr)

    assert final_balance > initial_balance
