import random

import os
import pytest

from nkms_eth.agents import MinerAgent, NuCypherKMSTokenAgent
from nkms_eth.actors import Miner


M = 10 ** 6


def test_deposit(testerchain, token, escrow):
    token._airdrop(amount=10000)    # weeee

    ursula_address = testerchain._chain.web3.eth.accounts[1]
    miner = Miner(miner_agent=escrow, address=ursula_address)
    miner.lock(amount=1000*M, locktime=100)


def test_mine_withdraw(testerchain, token, escrow):
    token._airdrop(amount=10000)

    ursula_address = testerchain._chain.web3.eth.accounts[1]
    miner = Miner(miner_agent=escrow, address=ursula_address)

    ursula = miner
    initial_balance = token.balance(address=ursula.address)

    # Create a random set of miners (we have 9 in total)
    for address in testerchain._chain.web3.eth.accounts[1:]:
        miner = Miner(miner_agent=escrow, address=address)

        amount = (10+random.randrange(9000)) * M
        miner.lock(amount=amount, locktime=1)

    testerchain.wait_time(escrow.hours_per_period*2)

    ursula.mint()
    ursula.withdraw(entire_balance=True)
    final_balance = token.balance(ursula.address)

    assert final_balance > initial_balance


def test_publish_miner_id(testerchain, token, escrow):
    token._airdrop(amount=10000)    # weeee

    miner_addr = testerchain._chain.web3.eth.accounts[1]
    miner = Miner(miner_agent=escrow, address=miner_addr)

    balance = miner.token_balance()
    miner.lock(amount=balance, locktime=1)

    # Publish Miner IDs to the DHT
    mock_miner_id = os.urandom(32)

    txhash = miner.publish_miner_id(mock_miner_id)
    stored_miner_ids = miner.fetch_miner_ids()

    assert len(stored_miner_ids) == 1
    assert mock_miner_id == stored_miner_ids[0]

    another_mock_miner_id = os.urandom(32)
    txhash = miner.publish_miner_id(another_mock_miner_id)

    stored_miner_ids = miner.fetch_miner_ids()

    assert len(stored_miner_ids) == 2
    assert another_mock_miner_id == stored_miner_ids[1]

    # TODO change when v4 of web3.py is released
    assert another_mock_miner_id == escrow().getMinerId(miner_addr, 1).encode('latin-1')


def test_select_ursulas(testerchain, token, escrow):
    token._airdrop(amount=10000)

    # Create a random set of miners (we have 9 in total)
    for u in testerchain._chain.web3.eth.accounts[1:]:
        miner = Miner(miner_agent=escrow, address=u)
        amount = (10 + random.randrange(9000))*M
        miner.lock(amount=amount, locktime=100)

    testerchain.wait_time(escrow.hours_per_period)

    miners = escrow.sample(quantity=3)
    assert len(miners) == 3
    assert len(set(miners)) == 3

    with pytest.raises(MinerAgent.NotEnoughUrsulas):
        escrow.sample(quantity=100)  # Waay more than we have deployed
