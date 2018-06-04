import pytest

from nucypher.blockchain.eth.agents import MinerAgent

M = 10 ** 6


@pytest.mark.slow()
@pytest.mark.usefixtures("mock_policy_agent")
def test_get_swarm(chain, mock_token_agent, mock_miner_agent):

    mock_token_agent.token_airdrop(amount=100000 * mock_token_agent.M)

    creator, *addresses = chain.interface.w3.eth.accounts

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


@pytest.mark.slow()
def test_sample_miners(chain, mock_miner_agent, mock_token_agent):
    mock_token_agent.token_airdrop(amount=100000 * mock_token_agent.M)

    # Have other address lock tokens
    _origin, ursula, *everybody_else = chain.interface.w3.eth.accounts
    mock_miner_agent.spawn_random_miners(addresses=everybody_else)

    chain.time_travel(periods=1)

    with pytest.raises(MinerAgent.NotEnoughUrsulas):
        mock_miner_agent.sample(quantity=100)  # Waay more than we have deployed

    miners = mock_miner_agent.sample(quantity=3)
    assert len(miners) == 3
    assert len(set(miners)) == 3
