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
from nucypher.cli.actions.confirm import confirm_deployment
from nucypher.cli.literature import ABORT_DEPLOYMENT


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
