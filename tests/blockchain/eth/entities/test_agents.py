import pytest

from nucypher.blockchain.eth.agents import MinerAgent
from constant_sorrow import constants


M = 10 ** 6


@pytest.mark.slow()
@pytest.mark.usefixtures("miners")
@pytest.mark.usefixtures("mock_policy_agent")
def test_get_swarm(mock_miner_agent):

    swarm = mock_miner_agent.swarm()
    swarm_addresses = list(swarm)
    assert len(swarm_addresses) == constants.NUMBER_OF_TEST_ETH_ACCOUNTS - 1  # exclude etherbase

    # Grab a miner address from the swarm
    miner_addr = swarm_addresses[0]
    assert isinstance(miner_addr, str)

    # Verify the address is hex
    try:
        int(miner_addr, 16)
    except ValueError:
        pytest.fail()


@pytest.mark.slow()
@pytest.mark.usefixtures("miners")
def test_sample_miners(mock_miner_agent):

    miners_population = mock_miner_agent.get_miner_population()
    with pytest.raises(MinerAgent.NotEnoughMiners):
        mock_miner_agent.sample(quantity=miners_population + 1, duration=1)  # Way more than we have deployed

    miners = mock_miner_agent.sample(quantity=3, duration=1)
    assert len(miners) == 3       # Three..
    assert len(set(miners)) == 3  # ..unique addresses
