from nkms_eth import token
from nkms_eth import ursula

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
    token.create_escrow()
    airdrop(chain)
    ursula.lock(1000 * M, 100, chain.web3.eth.accounts[1])
