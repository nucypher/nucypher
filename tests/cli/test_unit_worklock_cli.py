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
from hexbytes import HexBytes

from nucypher.blockchain.economics import EconomicsFactory
from nucypher.blockchain.eth.actors import Bidder
from nucypher.blockchain.eth.agents import ContractAgency
from nucypher.blockchain.eth.token import NU
from nucypher.cli.commands.worklock import worklock
from nucypher.config.constants import NUCYPHER_ENVVAR_KEYRING_PASSWORD
from nucypher.crypto.powers import TransactingPower
from nucypher.utilities.sandbox.constants import (
    TEST_PROVIDER_URI,
    TEMPORARY_DOMAIN, INSECURE_DEVELOPMENT_PASSWORD
)

ENV = {NUCYPHER_ENVVAR_KEYRING_PASSWORD: INSECURE_DEVELOPMENT_PASSWORD}
YES = 'Y\n'


@pytest.fixture(scope='module')
def surrogate_bidder(mock_testerchain, test_registry):
    address = mock_testerchain.unassigned_accounts[0]
    bidder = Bidder(checksum_address=address, registry=test_registry)
    return bidder


@pytest.fixture(scope='module')
def mock_worklock_agent(module_mocker, mock_testerchain, token_economics):

    blocktime = mock_testerchain.w3.eth.getBlock(block_identifier='latest')
    now = blocktime.timestamp
    current_block = blocktime.number

    class MockWorkLockAgent:

        # Fixtures
        FAKE_RECEIPT = {'transactionHash': HexBytes(b'FAKE29890FAKE8349804'),
                        'gasUsed': 1,
                        'blockNumber': current_block,
                        'blockHash': HexBytes(b'FAKE43434343FAKE43443434')}

        # Attributes
        start_bidding_date = now - 10
        end_bidding_date = now + 10
        minimum_allowed_bid = token_economics.worklock_min_allowed_bid
        blockchain = mock_testerchain

        # Methods
        bid = lambda *args, **kwargs: MockWorkLockAgent.FAKE_RECEIPT
        eth_to_tokens = lambda *args, **kwargs: 1
        get_deposited_eth = lambda *args, **kwargs: 1

    special_agent = MockWorkLockAgent()
    module_mocker.patch.object(ContractAgency, 'get_agent', return_value=special_agent)
    module_mocker.patch.object(EconomicsFactory, 'get_economics', return_value=token_economics)

    # TODO: Consider removal of this mock
    module_mocker.patch.object(TransactingPower, 'activate', return_value=True)

    return special_agent


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
               '--provider', TEST_PROVIDER_URI,
               '--network', TEMPORARY_DOMAIN,
               '--force',
               '--bidder-address', surrogate_bidder.checksum_address,
               '--value', bid_value)

    result = click_runner.invoke(worklock, command, catch_exceptions=False, input=YES, env=ENV)
    assert result.exit_code == 0

    # OK - Let's see what happened
    mock_bidder.assert_called_once()
    mock_bidder.assert_called_once_with(surrogate_bidder, value=NU.from_tokens(bid_value).to_nunits())
