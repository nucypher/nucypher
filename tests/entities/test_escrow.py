import random

import pytest
from populus.contracts.exceptions import NoKnownAddress
from pytest import raises

from nkms_eth.escrow import Escrow
from nkms_eth.miner import Miner
from nkms_eth.token import NuCypherKMSToken

M = 10 ** 6

def test_create_escrow(testerchain):
    with raises(NoKnownAddress):
        NuCypherKMSToken.get(blockchain=testerchain)

    token = NuCypherKMSToken(blockchain=testerchain)
    token.arm()
    token.deploy()

    same_token = NuCypherKMSToken.get(blockchain=testerchain)
    with raises(NuCypherKMSToken.ContractDeploymentError):
        same_token.arm()
        same_token.deploy()

    assert len(token.contract.address) == 42
    assert token.contract.address == same_token.contract.address

    with raises(NoKnownAddress):
        Escrow.get(blockchain=testerchain, token=token)

    escrow = Escrow(blockchain=testerchain, token=token)
    escrow.arm()
    escrow.deploy()

    same_escrow = Escrow.get(blockchain=testerchain, token=token)
    with raises(Escrow.ContractDeploymentError):
        same_escrow.arm()
        same_escrow.deploy()

    assert len(escrow.contract.address) == 42
    assert escrow.contract.address == same_escrow.contract.address


def test_get_swarm(testerchain, token, escrow):
    token._airdrop(amount=10000)

    # Create 9 Miners
    for u in testerchain._chain.web3.eth.accounts[1:]:
        miner = Miner(blockchain=testerchain, token=token, escrow=escrow, address=u)
        amount = (10+random.randrange(9000)) * M
        miner.lock(amount=amount, locktime=1)

    testerchain.wait_time(escrow.hours_per_period)

    swarm = escrow.swarm()
    swarm_addresses = list(swarm)
    assert len(swarm_addresses) == 9

    # Grab a miner address from the swarm
    miner_addr = swarm_addresses[0]
    assert isinstance(miner_addr, str)

    # Verify the address is hex
    try:
        int(miner_addr, 16)
    except ValueError:
        pytest.fail()

