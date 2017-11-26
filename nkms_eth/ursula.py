from nkms_eth import token
from nkms_eth import blockchain
import nkms_eth.escrow


def lock(amount: int, locktime: int, address: str = None):
    """
    Deposit and lock coins for mining. Creating coins starts after it is done

    :param amount:      Amount of coins to lock (in smallest  indivisible
                            units)
    :param locktime:    Locktime in blocks
    :param address:     Optional address to get coins from (accounts[0] by
                        default)
    """
    chain = blockchain.chain()
    address = address or chain.web3.eth.accounts[0]
    escrow = nkms_eth.escrow.get()
    tx = token.get().transact({'from': address}).approve(
            escrow.address, amount)
    chain.wait.for_receipt(tx, timeout=blockchain.TIMEOUT)
    tx = escrow.transact({'from': address}).deposit(amount, locktime)
    chain.wait.for_receipt(tx, timeout=blockchain.TIMEOUT)


def mine():
    pass


def withdraw():
    pass
