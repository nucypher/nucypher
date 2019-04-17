"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""
import pytest

from nucypher.blockchain.eth import constants
from nucypher.blockchain.eth.actors import PolicyAuthor
from nucypher.utilities.sandbox.constants import TESTING_ETH_AIRDROP_AMOUNT


@pytest.mark.slow()
@pytest.fixture(scope='module')
def author(testerchain, three_agents):
    token_agent, miner_agent, policy_agent = three_agents
    _origin, ursula, alice, *everybody_else = testerchain.interface.w3.eth.accounts
    author = PolicyAuthor(checksum_address=alice)
    return author


@pytest.mark.slow()
def test_create_policy_author(testerchain, three_agents):
    _origin, ursula, alice, *everybody_else = testerchain.interface.w3.eth.accounts
    policy_author = PolicyAuthor(checksum_address=alice)
    assert policy_author.checksum_public_address == alice
