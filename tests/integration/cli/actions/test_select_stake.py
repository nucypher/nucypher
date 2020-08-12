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
from typing import Callable, List

import click
import pytest

from nucypher.blockchain.eth.actors import StakeHolder
from nucypher.blockchain.eth.constants import NULL_ADDRESS
from nucypher.blockchain.eth.token import Stake
from nucypher.cli.actions.select import select_stake
from nucypher.cli.literature import NO_STAKES_FOUND, ONLY_DISPLAYING_DIVISIBLE_STAKES_NOTE
from nucypher.cli.painting.staking import STAKER_TABLE_COLUMNS, STAKE_TABLE_COLUMNS
from nucypher.types import SubStakeInfo, StakerInfo


def make_sub_stakes(current_period, token_economics, sub_stakes_functions: List[Callable]) -> List[SubStakeInfo]:
    sub_stakes = []
    for function in sub_stakes_functions:
        sub_stakes.extend(function(current_period, token_economics))
    return sub_stakes


def empty_sub_stakes(_current_period, _token_economics) -> List[SubStakeInfo]:
    return []


def inactive_sub_stakes(current_period, token_economics) -> List[SubStakeInfo]:
    stakes = [SubStakeInfo(first_period=1,
                           last_period=current_period - 2,
                           locked_value=token_economics.minimum_allowed_locked),
              SubStakeInfo(first_period=current_period - 4,
                           last_period=current_period - 3,
                           locked_value=2 * token_economics.minimum_allowed_locked + 1)]
    return stakes


def unlocked_sub_stakes(current_period, token_economics) -> List[SubStakeInfo]:
    stakes = [SubStakeInfo(first_period=1,
                           last_period=current_period - 1,
                           locked_value=token_economics.minimum_allowed_locked),
              SubStakeInfo(first_period=current_period - 3,
                           last_period=current_period - 1,
                           locked_value=2 * token_economics.minimum_allowed_locked + 1)]
    return stakes


def not_editable_sub_stakes(current_period, token_economics) -> List[SubStakeInfo]:
    stakes = [SubStakeInfo(first_period=1,
                           last_period=current_period,
                           locked_value=token_economics.minimum_allowed_locked),
              SubStakeInfo(first_period=current_period - 3,
                           last_period=current_period,
                           locked_value=2 * token_economics.minimum_allowed_locked + 1)]
    return stakes


def non_divisible_sub_stakes(current_period, token_economics) -> List[SubStakeInfo]:
    stakes = [SubStakeInfo(first_period=1,
                           last_period=current_period + 1,
                           locked_value=token_economics.minimum_allowed_locked),
              SubStakeInfo(first_period=current_period - 3,
                           last_period=current_period + 2,
                           locked_value=2 * token_economics.minimum_allowed_locked - 1),
              SubStakeInfo(first_period=current_period - 1,
                           last_period=current_period + 2,
                           locked_value=token_economics.minimum_allowed_locked + 1)]
    return stakes


def divisible_sub_stakes(current_period, token_economics) -> List[SubStakeInfo]:
    stakes = [SubStakeInfo(first_period=1,
                           last_period=current_period + 1,
                           locked_value=2 * token_economics.minimum_allowed_locked),
              SubStakeInfo(first_period=current_period - 3,
                           last_period=current_period + 2,
                           locked_value=2 * token_economics.minimum_allowed_locked + 1)]
    return stakes


@pytest.fixture()
def current_period(mock_staking_agent):
    current_period = 10
    return current_period


@pytest.fixture()
def stakeholder(current_period, mock_staking_agent, test_registry):
    mock_staking_agent.get_current_period.return_value = current_period

    staker_info = StakerInfo(current_committed_period=current_period-1,
                             next_committed_period=current_period,
                             value=0,
                             last_committed_period=0,
                             lock_restake_until_period=False,
                             completed_work=0,
                             worker_start_period=0,
                             worker=NULL_ADDRESS,
                             flags=bytes())
    mock_staking_agent.get_staker_info.return_value = staker_info

    return StakeHolder(registry=test_registry)


def assert_stake_table_painted(output: str) -> None:
    for column_name in (*STAKER_TABLE_COLUMNS, *STAKE_TABLE_COLUMNS):
        assert column_name in output


def assert_stake_table_not_painted(output: str) -> None:
    for column_name in (*STAKER_TABLE_COLUMNS, *STAKE_TABLE_COLUMNS):
        assert column_name not in output


@pytest.mark.parametrize('sub_stakes_functions', [
    [empty_sub_stakes],
    [inactive_sub_stakes],
    [unlocked_sub_stakes],
    [not_editable_sub_stakes],
    [inactive_sub_stakes, unlocked_sub_stakes, not_editable_sub_stakes]
])
def test_handle_selection_with_with_no_editable_stakes(test_emitter,
                                                       stakeholder,
                                                       mock_staking_agent,
                                                       mock_testerchain,
                                                       mock_stdin,  # used to assert user hasn't been prompted
                                                       capsys,
                                                       current_period,
                                                       token_economics,
                                                       sub_stakes_functions):
    mock_stakes = make_sub_stakes(current_period, token_economics, sub_stakes_functions)

    mock_staking_agent.get_all_stakes.return_value = mock_stakes
    staker = mock_testerchain.unassigned_accounts[0]
    stakeholder.set_staker(staker)

    # Test
    with pytest.raises(click.Abort):
        select_stake(emitter=test_emitter, staker=stakeholder)

    # Examine
    captured = capsys.readouterr()
    assert NO_STAKES_FOUND in captured.out
    assert_stake_table_not_painted(output=captured.out)
    assert mock_stdin.empty()


@pytest.mark.parametrize('sub_stakes_functions', [
    [non_divisible_sub_stakes],
    [divisible_sub_stakes],
    [inactive_sub_stakes, non_divisible_sub_stakes],
    [unlocked_sub_stakes, non_divisible_sub_stakes],
    [not_editable_sub_stakes, non_divisible_sub_stakes],
    [unlocked_sub_stakes, divisible_sub_stakes],
    [not_editable_sub_stakes, divisible_sub_stakes],
    [inactive_sub_stakes, divisible_sub_stakes],
    [inactive_sub_stakes, not_editable_sub_stakes, non_divisible_sub_stakes, unlocked_sub_stakes, divisible_sub_stakes]
])
def test_select_editable_stake(test_emitter,
                               stakeholder,
                               mock_staking_agent,
                               mock_testerchain,
                               mock_stdin,  # used to assert user hasn't been prompted
                               capsys,
                               current_period,
                               token_economics,
                               sub_stakes_functions):
    mock_stakes = make_sub_stakes(current_period, token_economics, sub_stakes_functions)

    mock_staking_agent.get_all_stakes.return_value = mock_stakes
    staker = mock_testerchain.unassigned_accounts[0]
    stakeholder.set_staker(staker)

    selection = len(mock_stakes) - 1
    expected_stake = Stake.from_stake_info(stake_info=mock_stakes[selection],
                                           staking_agent=mock_staking_agent,   # stakinator
                                           index=selection,
                                           checksum_address=stakeholder.checksum_address,
                                           economics=token_economics)

    # User's selection
    mock_stdin.line(str(selection))
    selected_stake = select_stake(emitter=test_emitter, staker=stakeholder)

    # Check stake accuracy
    assert isinstance(selected_stake, Stake)
    assert selected_stake == expected_stake

    # Examine the output
    captured = capsys.readouterr()
    assert NO_STAKES_FOUND not in captured.out
    assert ONLY_DISPLAYING_DIVISIBLE_STAKES_NOTE not in captured.out
    assert_stake_table_painted(output=captured.out)
    assert mock_stdin.empty()


def test_handle_selection_with_no_divisible_stakes(test_emitter,
                                                   stakeholder,
                                                   mock_staking_agent,
                                                   mock_testerchain,
                                                   mock_stdin,  # used to assert user hasn't been prompted
                                                   capsys,
                                                   current_period,
                                                   token_economics):

    # Setup
    mock_stakes = make_sub_stakes(current_period, token_economics, [non_divisible_sub_stakes])

    mock_staking_agent.get_all_stakes.return_value = mock_stakes
    staker = mock_testerchain.unassigned_accounts[0]
    stakeholder.set_staker(staker)

    # FAILURE: Divisible only with no divisible stakes on chain
    with pytest.raises(click.Abort):
        select_stake(emitter=test_emitter, staker=stakeholder, stakes_status=Stake.Status.DIVISIBLE)

    # Divisible warning was displayed, but having
    # no divisible stakes cases an expected failure
    captured = capsys.readouterr()
    assert NO_STAKES_FOUND in captured.out
    assert ONLY_DISPLAYING_DIVISIBLE_STAKES_NOTE in captured.out
    assert_stake_table_not_painted(output=captured.out)
    assert mock_stdin.empty()


@pytest.mark.parametrize('sub_stakes_functions', [
    [divisible_sub_stakes],
    [inactive_sub_stakes, divisible_sub_stakes],
    [unlocked_sub_stakes, divisible_sub_stakes],
    [not_editable_sub_stakes, divisible_sub_stakes],
    [non_divisible_sub_stakes, divisible_sub_stakes],
    [inactive_sub_stakes, not_editable_sub_stakes, non_divisible_sub_stakes, unlocked_sub_stakes, divisible_sub_stakes]
])
def test_select_divisible_stake(test_emitter,
                                stakeholder,
                                mock_staking_agent,
                                mock_testerchain,
                                mock_stdin,  # used to assert user hasn't been prompted
                                capsys,
                                current_period,
                                token_economics,
                                sub_stakes_functions):
    # Setup
    mock_stakes = make_sub_stakes(current_period, token_economics, sub_stakes_functions)

    mock_staking_agent.get_all_stakes.return_value = mock_stakes
    staker = mock_testerchain.unassigned_accounts[0]
    stakeholder.set_staker(staker)

    selection = len(mock_stakes) - 1
    expected_stake = Stake.from_stake_info(stake_info=mock_stakes[selection],
                                           staking_agent=mock_staking_agent,   # stakinator
                                           index=selection,
                                           checksum_address=stakeholder.checksum_address,
                                           economics=token_economics)

    # SUCCESS: Display all divisible-only stakes and make a selection
    mock_stdin.line(str(selection))
    selected_stake = select_stake(emitter=test_emitter, staker=stakeholder, stakes_status=Stake.Status.DIVISIBLE)

    assert isinstance(selected_stake, Stake)
    assert selected_stake == expected_stake

    # Examine the output
    captured = capsys.readouterr()
    assert NO_STAKES_FOUND not in captured.out
    assert ONLY_DISPLAYING_DIVISIBLE_STAKES_NOTE in captured.out
    assert_stake_table_painted(output=captured.out)
    assert mock_stdin.empty()


@pytest.mark.parametrize('sub_stakes_functions', [
    [not_editable_sub_stakes],
    [inactive_sub_stakes, not_editable_sub_stakes],
    [unlocked_sub_stakes, not_editable_sub_stakes],
    [divisible_sub_stakes, not_editable_sub_stakes],
    [non_divisible_sub_stakes, not_editable_sub_stakes],
    [inactive_sub_stakes, non_divisible_sub_stakes, unlocked_sub_stakes, divisible_sub_stakes, not_editable_sub_stakes]
])
def test_select_using_filter_function(test_emitter,
                                      stakeholder,
                                      mock_staking_agent,
                                      mock_testerchain,
                                      mock_stdin,  # used to assert user hasn't been prompted
                                      capsys,
                                      current_period,
                                      token_economics,
                                      sub_stakes_functions):
    # Setup
    mock_stakes = make_sub_stakes(current_period, token_economics, sub_stakes_functions)

    mock_staking_agent.get_all_stakes.return_value = mock_stakes
    staker = mock_testerchain.unassigned_accounts[0]
    stakeholder.set_staker(staker)

    selection = len(mock_stakes) - 1
    expected_stake = Stake.from_stake_info(stake_info=mock_stakes[selection],
                                           staking_agent=mock_staking_agent,   # stakinator
                                           index=selection,
                                           checksum_address=stakeholder.checksum_address,
                                           economics=token_economics)

    # SUCCESS: Display all editable-only stakes with specified final period
    mock_stdin.line(str(selection))
    selected_stake = select_stake(emitter=test_emitter,
                                  staker=stakeholder,
                                  stakes_status=Stake.Status.LOCKED,
                                  filter_function=lambda stake: stake.final_locked_period == current_period)

    assert isinstance(selected_stake, Stake)
    assert selected_stake == expected_stake

    # Examine the output
    captured = capsys.readouterr()
    assert NO_STAKES_FOUND not in captured.out
    assert_stake_table_painted(output=captured.out)
    assert mock_stdin.empty()


@pytest.mark.parametrize('sub_stakes_functions', [
    [inactive_sub_stakes],
    [unlocked_sub_stakes],
    [divisible_sub_stakes],
    [non_divisible_sub_stakes],
    [inactive_sub_stakes, non_divisible_sub_stakes, unlocked_sub_stakes, divisible_sub_stakes]
])
def test_no_stakes_with_filter_function(test_emitter,
                                        stakeholder,
                                        mock_staking_agent,
                                        mock_testerchain,
                                        mock_stdin,  # used to assert user hasn't been prompted
                                        capsys,
                                        current_period,
                                        token_economics,
                                        sub_stakes_functions):
    # Setup
    mock_stakes = make_sub_stakes(current_period, token_economics, sub_stakes_functions)

    mock_staking_agent.get_all_stakes.return_value = mock_stakes
    staker = mock_testerchain.unassigned_accounts[0]
    stakeholder.set_staker(staker)

    # FAILURE: no stakes with specified final period
    with pytest.raises(click.Abort):
        select_stake(emitter=test_emitter,
                     staker=stakeholder,
                     stakes_status=Stake.Status.LOCKED,
                     filter_function=lambda stake: stake.final_locked_period == current_period)

    # Divisible warning was displayed, but having
    # no divisible stakes causes an expected failure
    captured = capsys.readouterr()
    assert NO_STAKES_FOUND in captured.out
    assert_stake_table_not_painted(output=captured.out)
    assert mock_stdin.empty()
