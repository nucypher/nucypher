import pytest

from nucypher.blockchain.eth.agents import MinerAgent
from constant_sorrow import constants


M = 10 ** 6  # FIXME: Make this the same value as mining coeff?


@pytest.mark.slow()
def test_get_swarm(three_agents, non_ursula_miners):
    token_agent, miner_agent, policy_agent = three_agents

    swarm = miner_agent.swarm()
    swarm_addresses = list(swarm)
    assert len(swarm_addresses) == len(non_ursula_miners)

    # Grab a miner address from the swarm
    miner_addr = swarm_addresses[0]
    assert isinstance(miner_addr, str)

    # Verify the address is hex
    try:
        int(miner_addr, 16)
    except ValueError:
        pytest.fail()


@pytest.mark.slow()
@pytest.mark.usefixtures("non_ursula_miners")
def test_sample_miners(testerchain, three_agents):
    token_agent, miner_agent, policy_agent = three_agents
    miners_population = miner_agent.get_miner_population()

    testerchain.time_travel(periods=1)

    with pytest.raises(MinerAgent.NotEnoughMiners):
        miner_agent.sample(quantity=miners_population + 1, duration=1)  # One more than we have deployed

    miners = miner_agent.sample(quantity=3, duration=1)
    assert len(miners) == 3       # Three...
    assert len(set(miners)) == 3  # ...unique addresses
