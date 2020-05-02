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

from nucypher.blockchain.eth.actors import Bidder
from nucypher.blockchain.eth.token import NU
from nucypher.cli.commands.worklock import worklock
from nucypher.config.constants import NUCYPHER_ENVVAR_KEYRING_PASSWORD
from nucypher.utilities.sandbox.constants import (
    TEMPORARY_DOMAIN,
    INSECURE_DEVELOPMENT_PASSWORD,
    MOCK_PROVIDER_URI
)

ENV = {NUCYPHER_ENVVAR_KEYRING_PASSWORD: INSECURE_DEVELOPMENT_PASSWORD}
YES = 'Y\n'



@pytest.fixture(scope='module')
def surrogate_bidder(mock_testerchain, test_registry):
    address = mock_testerchain.etherbase_account
    bidder = Bidder(checksum_address=address, registry=test_registry)
    return bidder


def test_bid(mocker,
             mock_worklock_agent,
             click_runner,
             mock_testerchain,
             token_economics,
             test_registry_source_manager,
             test_registry,
             surrogate_bidder):

    mock_bidder = mocker.spy(Bidder, 'place_bid')
    bid_value = 50_000

    command = ('bid',
               '--provider', MOCK_PROVIDER_URI,
               '--network', TEMPORARY_DOMAIN,
               '--force',
               '--bidder-address', surrogate_bidder.checksum_address,
               '--value', bid_value)

    result = click_runner.invoke(worklock, command, catch_exceptions=False, input=YES, env=ENV)
    assert result.exit_code == 0

    # OK - Let's see what happened
    mock_bidder.assert_called_once()
    mock_bidder.assert_called_once_with(surrogate_bidder, value=NU.from_tokens(bid_value).to_nunits())
