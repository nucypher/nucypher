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


import random

import pytest

from nucypher.blockchain.eth.actors import Bidder
from nucypher.blockchain.eth.token import NU
from nucypher.cli.commands.worklock import worklock
from nucypher.utilities.sandbox.constants import (
    CLI_TEST_ENV,
    TEMPORARY_DOMAIN,
    MOCK_PROVIDER_URI,
    YES
)


@pytest.fixture(scope='module')
def surrogate_bidder(mock_testerchain, test_registry):
    address = mock_testerchain.etherbase_account
    bidder = Bidder(checksum_address=address, registry=test_registry)
    return bidder


def test_non_interactive_bid(click_runner,
                             mocker,
                             mock_worklock_agent,
                             token_economics,
                             test_registry_source_manager,
                             surrogate_bidder):

    # Spy on the corresponding CLI function we are testing
    mock_bidder = mocker.spy(Bidder, 'place_bid')

    minimum = token_economics.worklock_min_allowed_bid
    bid_value = random.randint(minimum, minimum*100)

    command = ('bid',
               '--provider', MOCK_PROVIDER_URI,
               '--network', TEMPORARY_DOMAIN,
               '--force',
               '--bidder-address', surrogate_bidder.checksum_address,
               '--value', bid_value)

    result = click_runner.invoke(worklock, command, catch_exceptions=False, input=YES, env=CLI_TEST_ENV)
    assert result.exit_code == 0

    # OK - Let's see what happened
    mock_bidder.assert_called_once()

    nunits = NU.from_tokens(bid_value).to_nunits()
    mock_bidder.assert_called_once_with(surrogate_bidder, value=nunits)
