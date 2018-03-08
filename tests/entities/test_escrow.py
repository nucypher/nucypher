import random

import pytest
from populus.contracts.exceptions import NoKnownAddress
from pytest import raises

from nkms_eth.agents import MinerAgent, NuCypherKMSTokenAgent
from nkms_eth.actors import Miner

M = 10 ** 6


def test_create_escrow(testerchain):
    with raises(NoKnownAddress):
        NuCypherKMSTokenAgent.get(blockchain=testerchain)

    token = NuCypherKMSTokenAgent(blockchain=testerchain)
    token.arm()
    token.deploy()

    same_token = NuCypherKMSTokenAgent.get(blockchain=testerchain)
    with raises(NuCypherKMSTokenAgent.ContractDeploymentError):
        same_token.arm()
        same_token.deploy()

    assert len(token.__contract.address) == 42
    assert token.__contract.address == same_token._contract.address

    with raises(NoKnownAddress):
        MinerAgent.get(token=token)

    escrow = MinerAgent(token=token)
    escrow.arm()
    escrow.deploy()

    same_escrow = MinerAgent.get(token=token)
    with raises(MinerAgent.ContractDeploymentError):
        same_escrow.arm()
        same_escrow.deploy()

    assert len(escrow.__contract.address) == 42
    assert escrow.__contract.address == same_escrow._contract.address


def test_get_swarm(testerchain, token, escrow):
    token._airdrop(amount=10000)
    creator, *addresses = testerchain._chain.web3.eth.accounts

    # Create 9 Miners
    for address in addresses:
        miner = Miner(miner_agent=escrow, address=address)
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

