import pytest

from nucypher.blockchain.eth import constants
from nucypher.blockchain.eth.actors import PolicyAuthor


@pytest.mark.slow()
@pytest.fixture(scope='module')
def author(testerchain, three_agents):
    token_agent, miner_agent, policy_agent = three_agents
    token_agent.ether_airdrop(amount=100000 * constants.M)
    _origin, ursula, alice, *everybody_else = testerchain.interface.w3.eth.accounts
    author = PolicyAuthor(checksum_address=alice)
    return author


@pytest.mark.slow()
def test_create_policy_author(testerchain, three_agents):
    token_agent, miner_agent, policy_agent = three_agents
    _origin, ursula, alice, *everybody_else = testerchain.interface.w3.eth.accounts
    policy_author = PolicyAuthor(checksum_address=alice)
    assert policy_author.checksum_public_address == alice
