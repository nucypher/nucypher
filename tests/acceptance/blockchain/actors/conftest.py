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

from nucypher.blockchain.eth.actors import Staker
from tests.utils.blockchain import token_airdrop
from tests.constants import DEVELOPMENT_TOKEN_AIRDROP_AMOUNT


@pytest.fixture(scope='module')
def staker(testerchain, agency, test_registry):
    token_agent, staking_agent, policy_agent = agency
    origin, staker_account, *everybody_else = testerchain.client.accounts
    token_airdrop(token_agent=token_agent,
                  origin=testerchain.etherbase_account,
                  addresses=[staker_account],
                  amount=DEVELOPMENT_TOKEN_AIRDROP_AMOUNT)
    staker = Staker(checksum_address=staker_account, is_me=True, registry=test_registry)
    return staker
