import pytest


M = 10 ** 6


@pytest.mark.skip("Last 5 stubborn blockchain tests.")
def test_get_swarm(chain, mock_token_agent, mock_miner_agent):

    mock_token_agent.token_airdrop(amount=100000 * mock_token_agent._M)

    creator, *addresses = chain.provider.w3.eth.accounts

    mock_miner_agent.spawn_random_miners(addresses=addresses)

    chain.time_travel(periods=1)

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

