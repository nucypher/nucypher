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

from nucypher.blockchain.eth.actors import PolicyAuthor
from nucypher.utilities.sandbox.constants import DEVELOPMENT_ETH_AIRDROP_AMOUNT


@pytest.mark.slow()
@pytest.fixture(scope='module')
def author(testerchain, agency, test_registry):
    _origin, ursula, alice, *everybody_else = testerchain.client.accounts
    author = PolicyAuthor(checksum_address=alice, registry=test_registry)
    return author


@pytest.mark.slow()
def test_create_policy_author(testerchain, agency, test_registry):
    _origin, ursula, alice, *everybody_else = testerchain.client.accounts
    policy_author = PolicyAuthor(checksum_address=alice, registry=test_registry)
    assert policy_author.checksum_address == alice
