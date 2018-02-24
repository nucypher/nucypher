import random
import pytest

from nkms_eth.escrow import Escrow
from nkms_eth.miner import Miner
from nkms_eth.token import NuCypherKMSToken


M = 10 ** 6


def test_deposit(testerchain, token, escrow):
    token._airdrop(amount=10000)
    ursula_address = testerchain.web3.eth.accounts[1]
    miner = Miner(blockchain=testerchain, token=token, escrow=escrow, address=ursula_address)
    miner.lock(amount=1000*M, locktime=100)


def test_mine_withdraw(testerchain, token, escrow):
    token._airdrop(amount=10000)

    ursula_address = testerchain.web3.eth.accounts[1]
    miner = Miner(blockchain=testerchain, token=token, escrow=escrow, address=ursula_address)

    ursula = miner
    initial_balance = token.balance(address=ursula.address)

    # Create a random set of miners (we have 9 in total)
    for address in testerchain.web3.eth.accounts[1:]:
        miner = Miner(blockchain=testerchain, token=token,
                      escrow=escrow, address=address)

        amount = (10+random.randrange(9000)) * M
        miner.lock(amount=amount, locktime=1)

    testerchain.wait_time(escrow.hours_per_period*2)

    ursula.mint()
    ursula.withdraw()
    final_balance = token.balance(ursula.address)

    assert final_balance > initial_balance


def test_select_ursulas(testerchain, token, escrow):
    token._airdrop(amount=10000)

    # Create a random set of miners (we have 9 in total)
    for u in testerchain.web3.eth.accounts[1:]:
        miner = Miner(blockchain=testerchain, token=token, escrow=escrow, address=u)
        amount = (10 + random.randrange(9000))*M
        miner.lock(amount=amount, locktime=100)

    testerchain.wait_time(escrow.hours_per_period)

    miners = escrow.sample(quantity=3)
    assert len(miners) == 3
    assert len(set(miners)) == 3

    with pytest.raises(Exception):
        escrow.sample(quantity=100)  # Waay more than we have deployed
