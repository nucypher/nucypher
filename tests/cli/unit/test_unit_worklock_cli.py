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
from tests.mock.agents import FAKE_RECEIPT


def assert_successful_transaction_echo(bidder_address: str, cli_output: str):
    expected = (bidder_address,
                FAKE_RECEIPT['blockHash'].hex(),
                FAKE_RECEIPT['blockNumber'],
                FAKE_RECEIPT['transactionHash'].hex())
    for output in expected:
        assert str(output) in cli_output, f'"{output}" not in bidding output'
    return True


@pytest.fixture(scope='module')
def surrogate_bidder(mock_testerchain, test_registry):
    address = mock_testerchain.etherbase_account
    bidder = Bidder(checksum_address=address, registry=test_registry)
    return bidder


def test_status(click_runner, mock_worklock_agent, test_registry_source_manager):
    command = ('status', '--provider', MOCK_PROVIDER_URI, '--network', TEMPORARY_DOMAIN)
    result = click_runner.invoke(worklock, command, catch_exceptions=False)
    assert result.exit_code == 0


def test_non_interactive_bid(click_runner,
                             mocker,
                             mock_worklock_agent,
                             token_economics,
                             test_registry_source_manager,
                             surrogate_bidder):

    # Spy on the corresponding CLI function we are testing
    mock_ensure = mocker.spy(Bidder, 'ensure_bidding_is_open')
    mock_bidder = mocker.spy(Bidder, 'place_bid')

    minimum = token_economics.worklock_min_allowed_bid
    bid_value = random.randint(minimum, minimum*100)

    command = ('bid',
               '--bidder-address', surrogate_bidder.checksum_address,
               '--value', bid_value,
               '--provider', MOCK_PROVIDER_URI,
               '--network', TEMPORARY_DOMAIN,
               '--force')

    result = click_runner.invoke(worklock, command, catch_exceptions=False, input=YES, env=CLI_TEST_ENV)
    assert result.exit_code == 0

    # OK - Let's see what happened
    mock_ensure.assert_called_once()  # checked that the bidding window was open
    mock_bidder.assert_called_once()

    nunits = NU.from_tokens(bid_value).to_nunits()
    mock_bidder.assert_called_once_with(surrogate_bidder, value=nunits)

    assert assert_successful_transaction_echo(bidder_address=surrogate_bidder.checksum_address, cli_output=result.output)


def test_cancel_bid(click_runner,
                    mocker,
                    mock_worklock_agent,
                    surrogate_bidder):

    # Spy on the corresponding CLI function we are testing
    mock_cancel = mocker.spy(Bidder, 'cancel_bid')

    command = ('cancel-bid',
               '--bidder-address', surrogate_bidder.checksum_address,
               '--provider', MOCK_PROVIDER_URI,
               '--network', TEMPORARY_DOMAIN,
               '--force')
    result = click_runner.invoke(worklock, command, input=YES, env=CLI_TEST_ENV, catch_exceptions=False)
    assert result.exit_code == 0

    # OK - Let's see what happened
    mock_cancel.assert_called_once()

    assert assert_successful_transaction_echo(bidder_address=surrogate_bidder.checksum_address, cli_output=result.output)


@pytest.mark.skip
def test_post_initialization(click_runner,
                             mocker,
                             mock_worklock_agent,
                             surrogate_bidder):

    # Spy on the corresponding CLI function we are testing
    mock_enable = mocker.spy(Bidder, 'enable_claiming')

    command = ('enable-claiming',
               '--bidder-address', surrogate_bidder.checksum_address,
               '--provider', MOCK_PROVIDER_URI,
               '--force',
               '--network', TEMPORARY_DOMAIN,
               '--gas-limit', 100000)

    result = click_runner.invoke(worklock, command, input=YES, env=CLI_TEST_ENV, catch_exceptions=False)
    assert result.exit_code == 0

    # OK - Let's see what happened
    mock_enable.assert_called_once()

    assert assert_successful_transaction_echo(bidder_address=surrogate_bidder.checksum_address, cli_output=result.output)


def test_claim(click_runner,
               mocker,
               mock_worklock_agent,
               surrogate_bidder):

    # Spy on the corresponding CLI function we are testing
    mock_withdraw_compensation = mocker.spy(Bidder, 'withdraw_compensation')
    mock_claim = mocker.spy(Bidder, 'claim')

    # Bidder has not claimed
    mocked_property = mocker.patch.object(
        Bidder, 'has_claimed',
        new_callable=mocker.PropertyMock,
        return_value=False
    )

    command = ('claim',
               '--bidder-address', surrogate_bidder.checksum_address,
               '--provider', MOCK_PROVIDER_URI,
               '--network', TEMPORARY_DOMAIN,
               '--force')

    result = click_runner.invoke(worklock, command, input=YES, env=CLI_TEST_ENV, catch_exceptions=False)
    assert result.exit_code == 0

    # OK - Let's see what happened
    mock_withdraw_compensation.assert_called_once()
    assert assert_successful_transaction_echo(bidder_address=surrogate_bidder.checksum_address, cli_output=result.output)

    mock_claim.assert_called_once()


def test_remaining_work(click_runner,
                        mocker,
                        mock_worklock_agent,
                        surrogate_bidder):

    # Spy on the corresponding CLI function we are testing
    mock_remaining_work = mocker.spy(Bidder, 'remaining_work')

    command = ('remaining-work',
               '--bidder-address', surrogate_bidder.checksum_address,
               '--provider', MOCK_PROVIDER_URI,
               '--network', TEMPORARY_DOMAIN)

    result = click_runner.invoke(worklock, command, catch_exceptions=False)
    assert result.exit_code == 0

    # OK - Let's see what happened
    mock_remaining_work.assert_called_once()


def test_refund(click_runner,
                mocker,
                mock_worklock_agent,
                surrogate_bidder):

    # Spy on the corresponding CLI function we are testing
    mock_refund = mocker.spy(Bidder, 'refund_deposit')

    command = ('refund',
               '--bidder-address', surrogate_bidder.checksum_address,
               '--provider', MOCK_PROVIDER_URI,
               '--network', TEMPORARY_DOMAIN,
               '--force')

    result = click_runner.invoke(worklock, command, input=YES, env=CLI_TEST_ENV, catch_exceptions=False)
    assert result.exit_code == 0

    # OK - Let's see what happened
    mock_refund.assert_called_once()

    assert assert_successful_transaction_echo(bidder_address=surrogate_bidder.checksum_address, cli_output=result.output)


def test_participant_status(click_runner,
                            mock_worklock_agent,
                            surrogate_bidder):
    command = ('status',
               '--bidder-address', surrogate_bidder.checksum_address,
               '--provider', MOCK_PROVIDER_URI,
               '--network', TEMPORARY_DOMAIN)

    result = click_runner.invoke(worklock, command, catch_exceptions=False)
    assert result.exit_code == 0
