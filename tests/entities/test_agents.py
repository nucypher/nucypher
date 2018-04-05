import pytest

from nkms_eth.utilities import spawn_miners, MockNuCypherMinerConfig

M = 10 ** 6


def test_get_swarm(testerchain, mock_token_deployer, mock_miner_agent):

    mock_token_deployer._global_airdrop(amount=10000)

    creator, *addresses = testerchain._chain.web3.eth.accounts
    spawn_miners(addresses=addresses, miner_agent=mock_miner_agent, locktime=1, m=M)

    default_period_duration = MockNuCypherMinerConfig._hours_per_period
    testerchain.wait_time(default_period_duration)

    swarm = mock_miner_agent.swarm()
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

