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
from nucypher.blockchain.eth.interfaces import BlockchainInterface
from nucypher.blockchain.eth.token import NU
from nucypher.cli.commands.worklock import worklock
from nucypher.config.constants import TEMPORARY_DOMAIN
from tests.constants import CLI_TEST_ENV, MOCK_PROVIDER_URI, YES
from tests.mock.agents import MockContractAgent


@pytest.fixture()
def surrogate_bidder(mock_testerchain, test_registry, mock_worklock_agent):
    address = mock_testerchain.etherbase_account
    bidder = Bidder(checksum_address=address, registry=test_registry)
    return bidder


def assert_successful_transaction_echo(bidder_address: str, cli_output: str):
    expected = (bidder_address,
                MockContractAgent.FAKE_RECEIPT['blockHash'].hex(),
                MockContractAgent.FAKE_RECEIPT['blockNumber'],
                MockContractAgent.FAKE_RECEIPT['transactionHash'].hex())
    for output in expected:
        assert str(output) in cli_output, f'"{output}" not in bidding output'


def test_status(click_runner, mock_worklock_agent, test_registry_source_manager):
    command = ('status', '--provider', MOCK_PROVIDER_URI, '--network', TEMPORARY_DOMAIN)
    result = click_runner.invoke(worklock, command, catch_exceptions=False)
    assert result.exit_code == 0


@pytest.fixture()
def bidding_command(token_economics, surrogate_bidder):
    minimum = token_economics.worklock_min_allowed_bid
    bid_value = random.randint(minimum, minimum*100)
    command = ('bid',
               '--bidder-address', surrogate_bidder.checksum_address,
               '--value', bid_value,
               '--provider', MOCK_PROVIDER_URI,
               '--network', TEMPORARY_DOMAIN,
               '--force')
    return command


def test_bid_too_soon(click_runner,
                      mocker,
                      mock_worklock_agent,
                      token_economics,
                      test_registry_source_manager,
                      surrogate_bidder,
                      mock_testerchain,
                      bidding_command):

    # Bidding window is not open yet
    now = mock_testerchain.get_blocktime()
    a_month_too_soon = now-(3600*30)
    mocker.patch.object(BlockchainInterface, 'get_blocktime', return_value=a_month_too_soon)
    with pytest.raises(Bidder.BiddingIsClosed):
        result = click_runner.invoke(worklock, bidding_command, catch_exceptions=False, input=YES, env=CLI_TEST_ENV)
        assert result.exit_code != 0


def test_bid_too_late(click_runner,
                      mocker,
                      mock_worklock_agent,
                      token_economics,
                      test_registry_source_manager,
                      surrogate_bidder,
                      mock_testerchain,
                      bidding_command):

    # Bidding window is closed
    now = mock_testerchain.get_blocktime()
    a_month_too_late = now+(3600*30)
    mocker.patch.object(BlockchainInterface, 'get_blocktime', return_value=a_month_too_late)
    with pytest.raises(Bidder.BiddingIsClosed):
        result = click_runner.invoke(worklock, bidding_command, catch_exceptions=False, input=YES, env=CLI_TEST_ENV)
        assert result.exit_code != 0


def test_valid_bid(click_runner,
                   mocker,
                   mock_worklock_agent,
                   token_economics,
                   test_registry_source_manager,
                   surrogate_bidder,
                   mock_testerchain):

    now = mock_testerchain.get_blocktime()
    sometime_later = now + 100
    mocker.patch.object(BlockchainInterface, 'get_blocktime', return_value=sometime_later)

    # Spy on the corresponding CLI function we are testing
    # TODO: Mock at the agent layer instead
    mock_ensure = mocker.spy(Bidder, 'ensure_bidding_is_open')
    mock_bidder = mocker.spy(Bidder, 'place_bid')

    minimum = token_economics.worklock_min_allowed_bid
    bid_value = random.randint(minimum, minimum * 100)

    command = ('bid',
               '--bidder-address', surrogate_bidder.checksum_address,
               '--value', bid_value,
               '--provider', MOCK_PROVIDER_URI,
               '--network', TEMPORARY_DOMAIN,
               '--force')

    result = click_runner.invoke(worklock, command, catch_exceptions=False, input=YES, env=CLI_TEST_ENV)
    assert result.exit_code == 0

    # OK - Let's see what happened

    # Bidder
    mock_ensure.assert_called_once()  # checked that the bidding window was open via actors layer
    mock_bidder.assert_called_once()
    nunits = NU.from_tokens(bid_value).to_nunits()
    mock_bidder.assert_called_once_with(surrogate_bidder, value=nunits)
    assert_successful_transaction_echo(bidder_address=surrogate_bidder.checksum_address, cli_output=result.output)

    # Transactions
    mock_worklock_agent.assert_only_transactions(allowed=[mock_worklock_agent.bid])
    mock_worklock_agent.bid.assert_called_with(checksum_address=surrogate_bidder.checksum_address, value=nunits)

    # Calls
    expected_calls = (mock_worklock_agent.get_deposited_eth, mock_worklock_agent.eth_to_tokens)
    for call in expected_calls:
        call.assert_called()


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

    # Bidder
    mock_cancel.assert_called_once()
    assert_successful_transaction_echo(bidder_address=surrogate_bidder.checksum_address, cli_output=result.output)

    # Transactions
    mock_worklock_agent.assert_only_transactions(allowed=[mock_worklock_agent.cancel_bid])
    mock_worklock_agent.cancel_bid.called_once_with(checksum_address=surrogate_bidder.checksum_address)

    # Calls
    mock_worklock_agent.get_deposited_eth.assert_called_once()


@pytest.mark.skip  # TODO
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

    # Bidder
    mock_enable.assert_called_once()
    assert_successful_transaction_echo(bidder_address=surrogate_bidder.checksum_address, cli_output=result.output)

    # Transactions
    mock_worklock_agent.assert_only_transactions(allowed=mock_worklock_agent.enable_claiming)
    mock_worklock_agent.enable_claiming.assert_called_with(hecksum_address=surrogate_bidder.checksum_address)


def test_initial_claim(click_runner,
                       mocker,
                       mock_worklock_agent,
                       surrogate_bidder):

    # Spy on the corresponding CLI function we are testing
    mock_withdraw_compensation = mocker.spy(Bidder, 'withdraw_compensation')
    mock_claim = mocker.spy(Bidder, 'claim')

    # TODO: Test this functionality in isolation
    mocker.patch.object(Bidder, '_ensure_cancellation_window')

    # Bidder has not claimed yet
    mocker.patch.object(
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

    mock_worklock_agent.claim.assert_called_once_with(checksum_address=surrogate_bidder.checksum_address)

    # Bidder
    mock_withdraw_compensation.assert_called_once()
    mock_claim.assert_called_once()
    assert_successful_transaction_echo(bidder_address=surrogate_bidder.checksum_address, cli_output=result.output)

    # Transactions
    mock_worklock_agent.withdraw_compensation.assert_called_with(checksum_address=surrogate_bidder.checksum_address)
    mock_worklock_agent.claim.assert_called_with(checksum_address=surrogate_bidder.checksum_address)

    # Calls
    expected_calls = (mock_worklock_agent.get_deposited_eth,
                      mock_worklock_agent.eth_to_tokens)
    for call in expected_calls:
        call.assert_called()


def test_already_claimed(click_runner,
                         mocker,
                         mock_worklock_agent,
                         surrogate_bidder):

    # Spy on the corresponding CLI function we are testing
    mock_withdraw_compensation = mocker.spy(Bidder, 'withdraw_compensation')
    mock_claim = mocker.spy(Bidder, 'claim')

    # TODO: Test this functionality in isolation
    mocker.patch.object(Bidder, '_ensure_cancellation_window')

    # Bidder already claimed
    mocker.patch.object(
        Bidder, 'has_claimed',
        new_callable=mocker.PropertyMock,
        return_value=True
    )

    command = ('claim',
               '--bidder-address', surrogate_bidder.checksum_address,
               '--provider', MOCK_PROVIDER_URI,
               '--network', TEMPORARY_DOMAIN,
               '--force')

    result = click_runner.invoke(worklock, command, input=YES, env=CLI_TEST_ENV, catch_exceptions=False)
    assert result.exit_code == 0

    # Bidder
    mock_withdraw_compensation.assert_called_once()
    assert_successful_transaction_echo(bidder_address=surrogate_bidder.checksum_address, cli_output=result.output)
    mock_claim.assert_not_called()

    # Transactions
    mock_worklock_agent.withdraw_compensation.assert_called_with(checksum_address=surrogate_bidder.checksum_address)
    mock_worklock_agent.claim.assert_not_called()


def test_remaining_work(click_runner,
                        mocker,
                        mock_worklock_agent,
                        surrogate_bidder):

    remaining_work = 100
    mock_remaining_work = mocker.patch.object(Bidder,
                                              'remaining_work',
                                              new_callable=mocker.PropertyMock,
                                              return_value=remaining_work)

    command = ('remaining-work',
               '--bidder-address', surrogate_bidder.checksum_address,
               '--provider', MOCK_PROVIDER_URI,
               '--network', TEMPORARY_DOMAIN)

    result = click_runner.invoke(worklock, command, catch_exceptions=False)
    assert result.exit_code == 0
    assert str(remaining_work) in result.output, "Remaining work was not echoed."

    # Bidder
    mock_remaining_work.assert_called_once()

    # Transactions
    mock_worklock_agent.assert_no_transactions()


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

    # Bidder
    mock_refund.assert_called_once()
    assert_successful_transaction_echo(bidder_address=surrogate_bidder.checksum_address, cli_output=result.output)

    # Transactions
    mock_worklock_agent.assert_only_transactions(allowed=[mock_worklock_agent.refund])
    mock_worklock_agent.refund.assert_called_with(checksum_address=surrogate_bidder.checksum_address)


def test_participant_status(click_runner,
                            mock_worklock_agent,
                            surrogate_bidder):
    command = ('status',
               '--bidder-address', surrogate_bidder.checksum_address,
               '--provider', MOCK_PROVIDER_URI,
               '--network', TEMPORARY_DOMAIN)

    result = click_runner.invoke(worklock, command, catch_exceptions=False)
    assert result.exit_code == 0
    
    expected_calls = (mock_worklock_agent.check_claim,
                      mock_worklock_agent.eth_to_tokens,
                      mock_worklock_agent.get_deposited_eth,
                      mock_worklock_agent.get_eth_supply,
                      mock_worklock_agent.get_base_deposit_rate,
                      mock_worklock_agent.get_bonus_lot_value,
                      mock_worklock_agent.get_bonus_deposit_rate,
                      mock_worklock_agent.get_bonus_refund_rate,
                      mock_worklock_agent.get_base_refund_rate,
                      # 'get_completed_work',  # TODO Yes or no?
                      mock_worklock_agent.get_refunded_work)
    # Calls
    for call in expected_calls:
        call.assert_called()
