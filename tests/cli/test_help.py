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

import nucypher
from nucypher.cli.deploy import deploy
from nucypher.cli.main import nucypher_cli, ENTRY_POINTS


def test_echo_nucypher_version(click_runner):
    version_args = ('--version', )
    result = click_runner.invoke(nucypher_cli, version_args, catch_exceptions=False)
    assert result.exit_code == 0
    assert str(nucypher.__version__) in result.output, 'Version text was not produced.'


@pytest.mark.parametrize('command', (('--help', ), tuple()))
def test_nucypher_help_message(click_runner, command):
    entry_points = {command.name for command in ENTRY_POINTS}
    result = click_runner.invoke(nucypher_cli, tuple(), catch_exceptions=False)
    assert result.exit_code == 0
    assert '[OPTIONS] COMMAND [ARGS]' in result.output, 'Missing or invalid help text was produced.'
    assert all(e in result.output for e in entry_points)


@pytest.mark.parametrize('entry_point', tuple(command.name for command in ENTRY_POINTS))
def test_character_help_messages(click_runner, entry_point):
    help_args = (entry_point, '--help')
    result = click_runner.invoke(nucypher_cli, help_args, catch_exceptions=False)
    assert result.exit_code == 0
    assert f'{entry_point}' in result.output, 'Missing or invalid help text was produced.'


def test_nucypher_deploy_help_message(click_runner):
    help_args = ('--help', )
    result = click_runner.invoke(deploy, help_args, catch_exceptions=False)
    assert result.exit_code == 0
    assert 'deploy [OPTIONS] ACTION' in result.output, 'Missing or invalid help text was produced.'
