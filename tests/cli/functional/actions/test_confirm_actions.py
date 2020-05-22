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
from nucypher.cli.actions.confirm import (confirm_deployment, confirm_enable_restaking, confirm_enable_restaking_lock,
                                          confirm_enable_winding_down, confirm_large_stake, confirm_staged_stake)
from nucypher.cli.literature import (ABORT_DEPLOYMENT, RESTAKING_AGREEMENT, RESTAKING_LOCK_AGREEMENT,
                                     WINDING_DOWN_AGREEMENT)


def test_confirm_deployment_cli_action(mocker, mock_click_prompt, test_emitter, stdout_trap, mock_testerchain):

    mock_click_prompt.return_value = False
    with pytest.raises(click.Abort):
        confirm_deployment(emitter=test_emitter, deployer_interface=mock_testerchain)
    output = stdout_trap.getvalue()
    assert ABORT_DEPLOYMENT in output

    stdout_trap.truncate(0)  # clear

    mock_click_prompt.return_value = 'DEPLOY'  # say the magic word
    result = confirm_deployment(emitter=test_emitter, deployer_interface=mock_testerchain)
    assert result
    output = stdout_trap.getvalue()
    assert not output

    stdout_trap.truncate(0)  # clear

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

    mock_click_prompt.return_value = 'DEPLOY'  # say the (wrong) magic word
    with pytest.raises(click.Abort):
        confirm_deployment(emitter=test_emitter, deployer_interface=mock_testerchain)

    mock_click_prompt.return_value = llamanet  # say the (almost correct) magic word
    with pytest.raises(click.Abort):
        confirm_deployment(emitter=test_emitter, deployer_interface=mock_testerchain)

    mock_click_prompt.return_value = llamanet.upper()  # say the (correct, uppercase) network name
    result = confirm_deployment(emitter=test_emitter, deployer_interface=mock_testerchain)
    assert result


def test_confirm_enable_restaking_lock_cli_action(mock_click_confirm, test_emitter, stdout_trap):

    # Test data
    staking_address, release_period = '0xdeadbeef', 1

    # Positive Case
    mock_click_confirm.return_value = True
    result = confirm_enable_restaking_lock(emitter=test_emitter,
                                           release_period=release_period,
                                           staking_address=staking_address)
    assert result
    output = stdout_trap.getvalue()
    restake_agreement = RESTAKING_LOCK_AGREEMENT.format(staking_address=staking_address, release_period=release_period)
    assert restake_agreement in output

    stdout_trap.truncate(0)  # clear

    # Negative case
    mock_click_confirm.side_effect = click.Abort

    with pytest.raises(click.Abort):
        confirm_enable_restaking_lock(emitter=test_emitter,
                                      release_period=release_period,
                                      staking_address=staking_address)
    output = stdout_trap.getvalue()
    restake_agreement = RESTAKING_LOCK_AGREEMENT.format(staking_address=staking_address,
                                                        release_period=release_period)
    assert restake_agreement in output


def test_confirm_enable_restaking_cli_action(test_emitter, mock_click_confirm, stdout_trap):

    # Positive Case
    mock_click_confirm.return_value = True
    staking_address = '0xdeadbeef'
    result = confirm_enable_restaking(emitter=test_emitter, staking_address=staking_address)
    assert result

    output = stdout_trap.getvalue()
    restake_agreement = RESTAKING_AGREEMENT.format(staking_address=staking_address)
    assert restake_agreement in output

    # Negative case
    stdout_trap.truncate(0)  # clear
    mock_click_confirm.side_effect = click.Abort

    with pytest.raises(click.Abort):
        confirm_enable_restaking(emitter=test_emitter, staking_address=staking_address)
    output = stdout_trap.getvalue()
    restake_agreement = RESTAKING_AGREEMENT.format(staking_address=staking_address)
    assert restake_agreement in output


def test_confirm_enable_winding_down_cli_action(test_emitter, mock_click_confirm, stdout_trap):

    # Positive Case
    mock_click_confirm.return_value = True
    staking_address = '0xdeadbeef'
    result = confirm_enable_winding_down(emitter=test_emitter, staking_address=staking_address)
    assert result

    output = stdout_trap.getvalue()
    assert WINDING_DOWN_AGREEMENT in output

    # Negative case
    stdout_trap.truncate(0)  # clear
    mock_click_confirm.side_effect = click.Abort

    with pytest.raises(click.Abort):
        confirm_enable_winding_down(emitter=test_emitter, staking_address=staking_address)
    output = stdout_trap.getvalue()
    assert WINDING_DOWN_AGREEMENT in output


def test_confirm_staged_stake_cli_action(test_emitter, mock_click_confirm, stdout_trap):

    # Positive Case
    mock_click_confirm.return_value = True
    staking_address, value, lock_periods = '0xdeadbeef', NU.from_tokens(1), 1
    result = confirm_staged_stake(staker_address=staking_address,
                                  value=value,
                                  lock_periods=lock_periods)
    assert result

    output = stdout_trap.getvalue()
    assert not output

    # Negative case
    stdout_trap.truncate(0)  # clear
    mock_click_confirm.side_effect = click.Abort

    with pytest.raises(click.Abort):
        confirm_staged_stake(staker_address=staking_address,
                             value=value,
                             lock_periods=lock_periods)
    output = stdout_trap.getvalue()
    assert not output


@pytest.mark.parametrize('value,duration,prompt_indicated', (
        (NU.from_tokens(1), 1, False),
        (NU.from_tokens(1), 31, False),
        (NU.from_tokens(15), 31, False),
        (NU.from_tokens(150001), 31, True),
        (NU.from_tokens(150000), 366, True),
        (NU.from_tokens(150001), 366, True),
))
def test_confirm_large_stake_cli_action(test_emitter, mock_click_confirm, stdout_trap, value, duration, prompt_indicated):

    # Positive Cases
    mock_click_confirm.return_value = True

    result = confirm_large_stake(value=value, lock_periods=duration)
    assert result
    output = stdout_trap.getvalue()
    assert not output
    stdout_trap.truncate(0)  # clear

    if prompt_indicated:
        # Negative cases
        mock_click_confirm.side_effect = click.Abort
        with pytest.raises(click.Abort):
            confirm_large_stake(value=value, lock_periods=duration)
        output = stdout_trap.getvalue()
        assert not output
