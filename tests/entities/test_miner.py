import random

import os
import pytest

from nkms_eth.escrow import Escrow
from nkms_eth.miner import Miner
from nkms_eth.token import NuCypherKMSToken


M = 10 ** 6


def test_deposit(testerchain, token, escrow):
    token._airdrop(amount=10000)    # weeee

    ursula_address = testerchain._chain.web3.eth.accounts[1]
    miner = Miner(blockchain=testerchain, token=token, escrow=escrow, address=ursula_address)
    miner.lock(amount=1000*M, locktime=100)


def test_mine_withdraw(testerchain, token, escrow):
    token._airdrop(amount=10000)

    ursula_address = testerchain._chain.web3.eth.accounts[1]
    miner = Miner(blockchain=testerchain, token=token, escrow=escrow, address=ursula_address)

    ursula = miner
    initial_balance = token.balance(address=ursula.address)

    # Create a random set of miners (we have 9 in total)
    for address in testerchain._chain.web3.eth.accounts[1:]:
        miner = Miner(blockchain=testerchain, token=token,
                      escrow=escrow, address=address)

        amount = (10+random.randrange(9000)) * M
        miner.lock(amount=amount, locktime=1)

    testerchain.wait_time(escrow.hours_per_period*2)

    ursula.mint()
    ursula.withdraw()
    final_balance = token.balance(ursula.address)

    assert final_balance > initial_balance


def test_publish_dht_key(testerchain, token, escrow):
    token._airdrop(amount=10000)    # weeee

    miner_addr = testerchain._chain.web3.eth.accounts[1]
    miner = Miner(blockchain=testerchain, token=token,
                  escrow=escrow, address=miner_addr)

    balance = miner.balance()
    miner.lock(amount=balance, locktime=1)

    # Publish DHT keys
    mock_dht_key = os.urandom(32)

    txhash = miner.publish_dht_key(mock_dht_key)
    stored_miner_dht_keys = miner.get_dht_key()

    assert len(stored_miner_dht_keys) == 1
    assert mock_dht_key == stored_miner_dht_keys[0]

    another_mock_dht_key = os.urandom(32)
    txhash = miner.publish_dht_key(another_mock_dht_key)

    stored_miner_dht_keys = miner.get_dht_key()

    assert len(stored_miner_dht_keys) == 2
    assert another_mock_dht_key == stored_miner_dht_keys[1]
    # TODO change when v4 web3.py will released
    assert another_mock_dht_key == escrow().getMinerInfo(escrow.MinerInfoField.MINER_ID.value, miner_addr, 1)\
        .encode('latin-1')


def test_select_ursulas(testerchain, token, escrow):
    token._airdrop(amount=10000)

    # Create a random set of miners (we have 9 in total)
    for u in testerchain._chain.web3.eth.accounts[1:]:
        miner = Miner(blockchain=testerchain, token=token, escrow=escrow, address=u)
        amount = (10 + random.randrange(9000))*M
        miner.lock(amount=amount, locktime=100)

    testerchain.wait_time(escrow.hours_per_period)

    miners = escrow.sample(quantity=3)
    assert len(miners) == 3
    assert len(set(miners)) == 3

    with pytest.raises(Escrow.NotEnoughUrsulas):
        escrow.sample(quantity=100)  # Waay more than we have deployed
