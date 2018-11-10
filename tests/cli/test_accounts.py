"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""
import pytest
from click.testing import CliRunner

from nucypher.cli import cli


@pytest.mark.usefixtures("three_agents")
def test_list(testerchain):
    runner = CliRunner()
    account = testerchain.interface.w3.eth.accounts[0]
    args = '--dev --federated-only --provider-uri tester://pyevm accounts list'.split()
    result = runner.invoke(cli, args, catch_exceptions=False)
    assert result.exit_code == 0
    assert account in result.output


@pytest.mark.usefixtures("three_agents")
def test_balance(testerchain):
    runner = CliRunner()
    account = testerchain.interface.w3.eth.accounts[0]
    args = '--dev --federated-only --provider-uri tester://pyevm accounts balance'.split()
    result = runner.invoke(cli, args, catch_exceptions=False)
    assert result.exit_code == 0
    assert 'Tokens:' in result.output
    assert 'ETH:' in result.output
    assert account in result.output


@pytest.mark.usefixtures("three_agents")
def test_transfer_eth(testerchain):
    runner = CliRunner()
    account = testerchain.interface.w3.eth.accounts[1]
    args = '--dev --federated-only --provider-uri tester://pyevm accounts transfer-eth'.split()
    result = runner.invoke(cli, args, catch_exceptions=False, input=account+'\n100\nY\n')
    assert result.exit_code == 0


@pytest.mark.usefixtures("three_agents")
def test_transfer_tokens(testerchain):
    runner = CliRunner()
    account = testerchain.interface.w3.eth.accounts[2]
    args = '--dev --federated-only --provider-uri tester://pyevm accounts transfer-tokens'.split()
    result = runner.invoke(cli, args, catch_exceptions=False, input=account+'\n100\nY\n')
    assert result.exit_code == 0
