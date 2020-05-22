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

import click
import pytest

from nucypher.blockchain.eth.actors import StakeHolder
from nucypher.blockchain.eth.token import NU, Stake
from nucypher.blockchain.eth.utils import epoch_to_period
from nucypher.cli.actions.select import select_stake
from nucypher.cli.literature import NO_STAKES_FOUND, ONLY_DISPLAYING_DIVISIBLE_STAKES_NOTE
from nucypher.cli.painting.staking import STAKER_TABLE_COLUMNS, STAKE_TABLE_COLUMNS
from tests.constants import INSECURE_DEVELOPMENT_PASSWORD


SELECTION = 0


@pytest.fixture()
def non_divisible_stakes(mock_testerchain, token_economics):
    stakes = [(1, 2, 3)]
    return stakes


@pytest.fixture()
def divisible_stakes(mock_testerchain, token_economics):
    nu = (token_economics.minimum_allowed_locked * 2) + 1
    seconds_per_period = token_economics.seconds_per_period
    current_period = epoch_to_period(mock_testerchain.get_blocktime(), seconds_per_period=seconds_per_period)
    final_period = current_period + (token_economics.minimum_locked_periods * 3)
    divisible_stakes = [(current_period, final_period, nu)]
    return divisible_stakes


@pytest.fixture()
def stakeholder_with_no_divisible_stakes(mock_testerchain,
                                         token_economics,
                                         mock_staking_agent,
                                         test_registry,
                                         non_divisible_stakes):
    mock_staking_agent.get_all_stakes.return_value = non_divisible_stakes
    stakeholder = StakeHolder(registry=test_registry)
    account = mock_testerchain.etherbase_account
    stakeholder.assimilate(checksum_address=account, password=INSECURE_DEVELOPMENT_PASSWORD)
    return stakeholder


@pytest.fixture()
def stakeholder_with_divisible_stakes(mock_testerchain,
                                      token_economics,
                                      mock_staking_agent,
                                      test_registry,
                                      divisible_stakes):

    mock_staking_agent.get_all_stakes.return_value = divisible_stakes
    stakeholder = StakeHolder(registry=test_registry)
    account = mock_testerchain.etherbase_account
    stakeholder.assimilate(checksum_address=account, password=INSECURE_DEVELOPMENT_PASSWORD)
    return stakeholder


def assert_stake_table_painted(output: str) -> None:
    for column_name in (*STAKER_TABLE_COLUMNS, *STAKE_TABLE_COLUMNS):
        assert column_name in output


def assert_stake_table_not_painted(output: str) -> None:
    for column_name in (*STAKER_TABLE_COLUMNS, *STAKE_TABLE_COLUMNS):
        assert column_name not in output


def test_handle_select_stake_with_no_stakes(test_emitter,
                                            token_economics,
                                            mock_staking_agent,
                                            test_registry,
                                            mock_testerchain,
                                            mock_click_prompt,
                                            stdout_trap):

    # Setup
    mock_stakes = []
    mock_staking_agent.get_all_stakes.return_value = mock_stakes
    stakeholder = StakeHolder(registry=test_registry)

    # Test
    with pytest.raises(click.Abort):
        select_stake(emitter=test_emitter, stakeholder=stakeholder)

    # Examine
    output = stdout_trap.getvalue()
    assert NO_STAKES_FOUND in output
    assert_stake_table_not_painted(output=output)


def test_select_non_divisible_stake(test_emitter,
                                    token_economics,
                                    mock_staking_agent,
                                    test_registry,
                                    mock_testerchain,
                                    mock_click_prompt,
                                    stdout_trap,
                                    non_divisible_stakes,
                                    stakeholder_with_no_divisible_stakes):

    expected_stake = Stake.from_stake_info(stake_info=non_divisible_stakes[0],
                                           staking_agent=mock_staking_agent,   # stakinator
                                           index=0,
                                           checksum_address=stakeholder_with_no_divisible_stakes.checksum_address,
                                           economics=token_economics)

    # User's selection
    mock_click_prompt.return_value = SELECTION
    selected_stake = select_stake(emitter=test_emitter,
                                  divisible=False,
                                  stakeholder=stakeholder_with_no_divisible_stakes)

    # Check stake accuracy
    assert isinstance(selected_stake, Stake)
    assert selected_stake == expected_stake

    # Examine the output
    output = stdout_trap.getvalue()
    assert NO_STAKES_FOUND not in output
    assert ONLY_DISPLAYING_DIVISIBLE_STAKES_NOTE not in output
    assert_stake_table_painted(output=output)


def test_handle_selection_with_no_divisible_stakes(test_emitter,
                                                   token_economics,
                                                   mock_staking_agent,
                                                   test_registry,
                                                   mock_testerchain,
                                                   mock_click_prompt,
                                                   stdout_trap,
                                                   non_divisible_stakes):

    # Setup
    mock_staking_agent.get_all_stakes.return_value = non_divisible_stakes

    stakeholder = StakeHolder(registry=test_registry)
    stakeholder.assimilate(checksum_address=mock_testerchain.etherbase_account,
                           password=INSECURE_DEVELOPMENT_PASSWORD)

    # FAILURE: Divisible only with no divisible stakes on chain
    with pytest.raises(click.Abort):
        select_stake(emitter=test_emitter,
                     divisible=True,
                     stakeholder=stakeholder)

    # Divisible warning was displayed, but having
    # no divisible stakes cases an expected failure
    output = stdout_trap.getvalue()
    assert NO_STAKES_FOUND not in output
    assert ONLY_DISPLAYING_DIVISIBLE_STAKES_NOTE in output
    assert_stake_table_not_painted(output=output)


def test_select_divisible_stake(test_emitter,
                                token_economics,
                                mock_staking_agent,
                                test_registry,
                                mock_testerchain,
                                mock_click_prompt,
                                stdout_trap,
                                divisible_stakes,
                                stakeholder_with_divisible_stakes):

    expected_stake = Stake.from_stake_info(stake_info=divisible_stakes[0],
                                           staking_agent=mock_staking_agent,  # stakinator
                                           index=0,
                                           checksum_address=stakeholder_with_divisible_stakes.checksum_address,
                                           economics=token_economics)

    # SUCCESS: Display all divisible-only stakes and make a selection
    mock_click_prompt.return_value = SELECTION

    selected_stake = select_stake(emitter=test_emitter,
                                  divisible=True,
                                  stakeholder=stakeholder_with_divisible_stakes)

    assert isinstance(selected_stake, Stake)
    assert selected_stake == expected_stake

    # Examine the output
    output = stdout_trap.getvalue()
    assert NO_STAKES_FOUND not in output
    assert ONLY_DISPLAYING_DIVISIBLE_STAKES_NOTE in output
    assert_stake_table_painted(output=output)
