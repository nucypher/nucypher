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
from unittest.mock import call

import pytest
from eth_utils import to_wei

from nucypher.blockchain.eth.actors import Bidder
from nucypher.blockchain.eth.interfaces import BlockchainInterface
from nucypher.blockchain.eth.token import NU
from nucypher.cli.commands.worklock import worklock
from nucypher.config.constants import TEMPORARY_DOMAIN
from tests.constants import CLI_TEST_ENV, MOCK_PROVIDER_URI, YES, NO
from tests.mock.agents import MockContractAgent
from nucypher.cli.literature import CONFIRM_BID_VERIFICATION


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


@pytest.mark.usefixtures("test_registry_source_manager")
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


@pytest.mark.usefixtures("test_registry_source_manager")
def test_enable_claiming(click_runner,
                         mocker,
                         mock_worklock_agent,
                         surrogate_bidder,
                         token_economics,
                         mock_testerchain):

    # Spy on the corresponding CLI function we are testing
    mock_force_refund = mocker.spy(Bidder, 'force_refund')
    mock_verify = mocker.spy(Bidder, 'verify_bidding_correctness')
    mock_get_whales = mocker.spy(Bidder, 'get_whales')

    # Cancellation window is closed
    now = mock_testerchain.get_blocktime()
    sometime_later = now+(3600*30)
    mocker.patch.object(BlockchainInterface, 'get_blocktime', return_value=sometime_later)

    # Prepare bidders
    bidders = mock_testerchain.client.accounts[0:10]
    num_bidders = len(bidders)
    bonus_lot_value = token_economics.worklock_supply - token_economics.minimum_allowed_locked * num_bidders

    bids_before = [to_wei(50_000, 'ether')]
    min_bid_eth_value = to_wei(1, 'ether')
    max_bid_eth_value = to_wei(10, 'ether')
    for i in range(num_bidders - 1):
        bids_before.append(random.randrange(min_bid_eth_value, max_bid_eth_value))
    bonus_eth_supply_before = sum(bids_before) - token_economics.worklock_min_allowed_bid * num_bidders

    bids_after = [min_bid_eth_value] * num_bidders
    bonus_eth_supply_after = 0

    min_bid = min(bids_before)
    bidder_to_exclude = bids_before.index(min_bid)
    bidders_to_check = bidders.copy()
    del bidders_to_check[bidder_to_exclude]

    mock_worklock_agent.get_bonus_eth_supply.side_effect = [bonus_eth_supply_before, bonus_eth_supply_after, bonus_eth_supply_after]
    mock_worklock_agent.get_bonus_lot_value.return_value = bonus_lot_value
    mock_worklock_agent.get_bidders.return_value = bidders
    mock_worklock_agent.get_deposited_eth.side_effect = [*bids_before, *bids_after, *bids_after]
    mock_worklock_agent.bidders_checked.side_effect = [False, False, False, False, True]
    mock_worklock_agent.next_bidder_to_check.side_effect = [0, num_bidders // 2, num_bidders]
    mock_worklock_agent.estimate_verifying_correctness.side_effect = [3, 6]

    command = ('enable-claiming',
               '--bidder-address', surrogate_bidder.checksum_address,
               '--provider', MOCK_PROVIDER_URI,
               '--network', TEMPORARY_DOMAIN)

    gas_limit_1 = 200000
    gas_limit_2 = 300000
    user_input = YES + YES + str(gas_limit_1) + '\n' + NO + str(gas_limit_2) + '\n' + YES
    result = click_runner.invoke(worklock, command, input=user_input, env=CLI_TEST_ENV, catch_exceptions=False)
    assert result.exit_code == 0
    confirmation = CONFIRM_BID_VERIFICATION.format(bidder_address=surrogate_bidder.checksum_address,
                                                   gas_limit=gas_limit_1,
                                                   bidders_per_transaction=3)
    assert confirmation in result.output
    confirmation = CONFIRM_BID_VERIFICATION.format(bidder_address=surrogate_bidder.checksum_address,
                                                   gas_limit=gas_limit_2,
                                                   bidders_per_transaction=6)
    assert confirmation in result.output

    # Bidder
    mock_force_refund.assert_called_once()
    mock_verify.assert_called_once()
    mock_get_whales.assert_called()
    assert_successful_transaction_echo(bidder_address=surrogate_bidder.checksum_address, cli_output=result.output)

    # Manual checking of force_refund tx because of unpredictable order of actual bidders_to_check array
    transaction_executions = mock_worklock_agent.force_refund.call_args_list
    assert len(transaction_executions) == 1
    _agent_args, agent_kwargs = transaction_executions[0]
    checksum_address, addresses = agent_kwargs.values()
    assert checksum_address == surrogate_bidder.checksum_address
    assert sorted(addresses) == sorted(bidders_to_check)

    mock_worklock_agent.verify_bidding_correctness.assert_has_calls([
        call(checksum_address=surrogate_bidder.checksum_address, gas_limit=gas_limit_2),
        call(checksum_address=surrogate_bidder.checksum_address, gas_limit=gas_limit_2)
    ])
    mock_worklock_agent.assert_only_transactions([mock_worklock_agent.force_refund,
                                                  mock_worklock_agent.verify_bidding_correctness])

    # Calls
    mock_worklock_agent.estimate_verifying_correctness.assert_has_calls([
        call(gas_limit=gas_limit_1),
        call(gas_limit=gas_limit_2)
    ])
    mock_worklock_agent.get_bidders.assert_called()
    mock_worklock_agent.get_bonus_lot_value.assert_called()
    mock_worklock_agent.get_bonus_eth_supply.assert_called()
    mock_worklock_agent.next_bidder_to_check.assert_called()
    mock_worklock_agent.get_deposited_eth.assert_called()


@pytest.mark.usefixtures("test_registry_source_manager")
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


@pytest.mark.usefixtures("test_registry_source_manager")
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
    assert result.exit_code == 1

    # Bidder
    mock_withdraw_compensation.assert_called_once()
    assert_successful_transaction_echo(bidder_address=surrogate_bidder.checksum_address, cli_output=result.output)
    mock_claim.assert_not_called()

    # Transactions
    mock_worklock_agent.withdraw_compensation.assert_called_with(checksum_address=surrogate_bidder.checksum_address)
    mock_worklock_agent.claim.assert_not_called()


@pytest.mark.usefixtures("test_registry_source_manager")
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


@pytest.mark.usefixtures("test_registry_source_manager")
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


@pytest.mark.usefixtures("test_registry_source_manager")
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
                      mock_worklock_agent.get_completed_work,
                      mock_worklock_agent.get_refunded_work)
    # Calls
    for call in expected_calls:
        call.assert_called()
