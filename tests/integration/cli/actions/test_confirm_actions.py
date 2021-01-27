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

from nucypher.blockchain.eth.clients import EthereumTesterClient, PUBLIC_CHAINS
from nucypher.blockchain.eth.token import NU
from nucypher.cli.actions.confirm import (confirm_deployment, confirm_enable_restaking,
                                          confirm_enable_winding_down, confirm_large_stake, confirm_staged_stake)
from nucypher.cli.literature import (ABORT_DEPLOYMENT, RESTAKING_AGREEMENT,
                                     WINDING_DOWN_AGREEMENT, CONFIRM_STAGED_STAKE,
                                     CONFIRM_LARGE_STAKE_VALUE, CONFIRM_LARGE_STAKE_DURATION)

from tests.constants import YES, NO


def test_confirm_deployment_cli_action(mocker, mock_stdin, test_emitter, capsys, mock_testerchain):
    mock_stdin.line('foo') # anything different from `deployer_interface.client.chain_name.upper()`
    with pytest.raises(click.Abort):
        confirm_deployment(emitter=test_emitter, deployer_interface=mock_testerchain)
    captured = capsys.readouterr()
    assert ABORT_DEPLOYMENT in captured.out
    assert mock_stdin.empty()

    mock_stdin.line('DEPLOY') # say the magic word
    result = confirm_deployment(emitter=test_emitter, deployer_interface=mock_testerchain)
    assert result
    captured = capsys.readouterr()
    assert "Type 'DEPLOY' to continue: " in captured.out
    assert mock_stdin.empty()

    # Mimick a known chain name
    llamanet, llamanet_chain_id = 'llamanet', 1123589012901209
    mocker.patch.dict(PUBLIC_CHAINS, {'llamanet': llamanet_chain_id})

    mocker.patch.object(EthereumTesterClient,
                        'chain_id',
                        return_value=llamanet_chain_id,
                        new_callable=mocker.PropertyMock)

    mocker.patch.object(EthereumTesterClient,
                        'chain_name',
                        return_value=llamanet,
                        new_callable=mocker.PropertyMock)
    mock_testerchain.client.is_local = False

    mock_stdin.line('DEPLOY') # say the (wrong) magic word
    with pytest.raises(click.Abort):
        confirm_deployment(emitter=test_emitter, deployer_interface=mock_testerchain)
    assert mock_stdin.empty()
    captured = capsys.readouterr()
    assert f"Type '{llamanet.upper()}' to continue: " in captured.out
    assert ABORT_DEPLOYMENT in captured.out

    mock_stdin.line(llamanet)  # say the (almost correct) magic word
    with pytest.raises(click.Abort):
        confirm_deployment(emitter=test_emitter, deployer_interface=mock_testerchain)
    assert mock_stdin.empty()
    captured = capsys.readouterr()
    assert f"Type '{llamanet.upper()}' to continue: " in captured.out
    assert ABORT_DEPLOYMENT in captured.out

    mock_stdin.line(llamanet.upper())  # say the (correct, uppercase) network name
    result = confirm_deployment(emitter=test_emitter, deployer_interface=mock_testerchain)
    assert result
    assert mock_stdin.empty()
    captured = capsys.readouterr()
    assert f"Type '{llamanet.upper()}' to continue: " in captured.out


def test_confirm_enable_restaking_cli_action(test_emitter, mock_stdin, capsys):

    # Positive Case
    mock_stdin.line(YES)
    staking_address = '0xdeadbeef'
    result = confirm_enable_restaking(emitter=test_emitter, staking_address=staking_address)
    assert result
    assert mock_stdin.empty()

    captured = capsys.readouterr()
    restake_agreement = RESTAKING_AGREEMENT.format(staking_address=staking_address)
    assert restake_agreement in captured.out

    # Negative case
    mock_stdin.line(NO)

    with pytest.raises(click.Abort):
        confirm_enable_restaking(emitter=test_emitter, staking_address=staking_address)
    captured = capsys.readouterr()
    assert mock_stdin.empty()

    restake_agreement = RESTAKING_AGREEMENT.format(staking_address=staking_address)
    assert restake_agreement in captured.out


def test_confirm_enable_winding_down_cli_action(test_emitter, mock_stdin, capsys):

    # Positive Case
    mock_stdin.line(YES)
    staking_address = '0xdeadbeef'
    result = confirm_enable_winding_down(emitter=test_emitter, staking_address=staking_address)
    assert result
    assert mock_stdin.empty()

    captured = capsys.readouterr()
    assert WINDING_DOWN_AGREEMENT in captured.out

    # Negative case
    mock_stdin.line(NO)

    with pytest.raises(click.Abort):
        confirm_enable_winding_down(emitter=test_emitter, staking_address=staking_address)
    captured = capsys.readouterr()
    assert mock_stdin.empty()
    assert WINDING_DOWN_AGREEMENT in captured.out


def test_confirm_staged_stake_cli_action(test_emitter, mock_stdin, capsys):

    staking_address, value, lock_periods = '0xdeadbeef', NU.from_tokens(1), 1
    confirmation = CONFIRM_STAGED_STAKE.format(staker_address=staking_address,
                                               lock_periods=lock_periods,
                                               tokens=value,
                                               nunits=value.to_nunits())

    # Positive Case
    mock_stdin.line(YES)

    result = confirm_staged_stake(staker_address=staking_address,
                                  value=value,
                                  lock_periods=lock_periods)
    assert result
    assert mock_stdin.empty()

    captured = capsys.readouterr()
    assert confirmation in captured.out

    # Negative case
    mock_stdin.line(NO)

    with pytest.raises(click.Abort):
        confirm_staged_stake(staker_address=staking_address,
                             value=value,
                             lock_periods=lock_periods)

    captured = capsys.readouterr()
    assert confirmation in captured.out
    assert mock_stdin.empty()


@pytest.mark.parametrize('value,duration,must_confirm_value,must_confirm_duration', (
        (NU.from_tokens(1), 1, False, False),
        (NU.from_tokens(1), 31, False, False),
        (NU.from_tokens(15), 31, False, False),
        (NU.from_tokens(150001), 31, True, False),
        (NU.from_tokens(150000), 366, False, True),
        (NU.from_tokens(150001), 366, True, True),
))
def test_confirm_large_stake_cli_action(test_emitter,
                                        mock_stdin,
                                        capsys,
                                        value,
                                        duration,
                                        must_confirm_value,
                                        must_confirm_duration):

    asked_about_value = lambda output: CONFIRM_LARGE_STAKE_VALUE.format(value=value) in output
    asked_about_duration = lambda output: CONFIRM_LARGE_STAKE_DURATION.format(lock_periods=duration) in output

    # Positive Cases - either do not need to confirm anything, or say yes
    if must_confirm_value:
        mock_stdin.line(YES)
    if must_confirm_duration:
        mock_stdin.line(YES)
    result = confirm_large_stake(value=value, lock_periods=duration)
    assert result
    captured = capsys.readouterr()
    assert must_confirm_value == asked_about_value(captured.out)
    assert must_confirm_duration == asked_about_duration(captured.out)
    assert mock_stdin.empty()

    if must_confirm_value or must_confirm_duration:
        # Negative cases - must confirm something and say no
        if must_confirm_value and must_confirm_duration:
            # yes to the former but not to the latter
            mock_stdin.line(YES)
            mock_stdin.line(NO)
        else:
            # no to whatever one we are asked about
            mock_stdin.line(NO)

        with pytest.raises(click.Abort):
            confirm_large_stake(value=value, lock_periods=duration)
        captured = capsys.readouterr()
        assert must_confirm_value == asked_about_value(captured.out)
        assert must_confirm_duration == asked_about_duration(captured.out)
        assert mock_stdin.empty()
