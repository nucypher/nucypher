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
import inspect

import click
import pytest

import nucypher
from nucypher.cli.config import NucypherClickConfig
from nucypher.cli.commands.deploy import deploy
from nucypher.cli.main import nucypher_cli, ENTRY_POINTS

NUCYPHER_CLICK_CONFIG_OPTIONS = set(inspect.signature(NucypherClickConfig.set_options).parameters.keys())
NUCYPHER_CLICK_CONFIG_OPTIONS.remove('self')


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


@pytest.mark.parametrize('entry_point_name, entry_point', ([command.name, command] for command in ENTRY_POINTS))
def test_character_help_messages(click_runner, entry_point_name, entry_point):
    help_args = (entry_point_name, '--help')
    result = click_runner.invoke(nucypher_cli, help_args, catch_exceptions=False)
    assert result.exit_code == 0
    assert f'{entry_point_name}' in result.output, 'Missing or invalid help text was produced.'
    if isinstance(entry_point, click.Group):
        for sub_command in entry_point.commands:
            assert f'{sub_command}' in result.output, f'Sub command {sub_command} is missing from help text'


@pytest.mark.parametrize('entry_point_name, entry_point', ([command.name, command] for command in ENTRY_POINTS))
def test_character_sub_command_help_messages(click_runner, entry_point_name, entry_point):
    if isinstance(entry_point, click.Group):
        for sub_command in entry_point.commands:
            result = click_runner.invoke(nucypher_cli,
                                         (entry_point_name, sub_command, '--help'),
                                         catch_exceptions=False)
            assert result.exit_code == 0
            assert f'{entry_point_name} {sub_command}' in result.output, \
                f'Sub command {sub_command} has missing or invalid help text.'


def test_nucypher_deploy_help_message(click_runner):
    help_args = ('--help', )
    result = click_runner.invoke(deploy, help_args, catch_exceptions=False)
    assert result.exit_code == 0
    assert 'deploy [OPTIONS] COMMAND [ARGS]' in result.output, 'Missing or invalid help text was produced.'


@pytest.mark.parametrize('entry_point_name, entry_point', ([command.name, command] for command in ENTRY_POINTS))
def test_character_command_options_and_parameters_match(entry_point_name, entry_point):
    if isinstance(entry_point, click.Group):
        for sub_command in entry_point.commands.values():
            _check_command_options_and_parameters(sub_command)
    else:
        # Plain old command - currently just `moe`
        _check_command_options_and_parameters(entry_point)


def _check_command_options_and_parameters(command):
    command_signature = inspect.signature(command.callback)

    command_callback_params = set(command_signature.parameters.keys())
    assert 'click_config' in command_callback_params, f"{command.name} specifies 'click_config' as a method parameter"

    # remove click_config and add actual options
    command_callback_params.remove('click_config')
    command_callback_params.update(NUCYPHER_CLICK_CONFIG_OPTIONS)

    command_options = set(p.name for p in command.params)
    assert command_options == command_callback_params, \
        f"click options provided for '{command.name}' matches the corresponding method parameters"
