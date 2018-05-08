import pytest

from tests.blockchain.eth.utilities import MockNuCypherMinerConfig

M = 10 ** 6


@pytest.mark.skip("Last 5 stubborn blockchain tests.")
def test_get_swarm(chain, mock_token_agent, mock_miner_agent):

    mock_token_agent._token_airdrop(amount=10000)

    creator, *addresses = chain.provider.w3.eth.accounts

    chain.spawn_miners(addresses=addresses, miner_agent=mock_miner_agent, locktime=1)

    default_period_duration = MockNuCypherMinerConfig._hours_per_period
    chain.time_travel(default_period_duration)

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

