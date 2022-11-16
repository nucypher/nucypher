


import click
import pytest

import nucypher
from nucypher.blockchain.eth.sol.__conf__ import SOLIDITY_COMPILER_VERSION
from nucypher.cli.commands.deploy import deploy
from nucypher.cli.main import ENTRY_POINTS, nucypher_cli
from nucypher.config.constants import USER_LOG_DIR, DEFAULT_CONFIG_ROOT


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
        for sub_command, config in entry_point.commands.items():
            if not config.hidden:
                assert f'{sub_command}' in result.output, f'Sub command {sub_command} is missing from help text'
            else:
                assert f'{sub_command}' not in result.output, f'Hidden command {sub_command} in help text'


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


def test_echo_solidity_version(click_runner):
    version_args = ('--solidity-version', )
    result = click_runner.invoke(deploy, version_args, catch_exceptions=False)
    assert result.exit_code == 0
    assert str(SOLIDITY_COMPILER_VERSION) in result.output, 'Solidity version text was not produced.'


def test_echo_config_root(click_runner):
    version_args = ('--config-path', )
    result = click_runner.invoke(nucypher_cli, version_args, catch_exceptions=False)
    assert result.exit_code == 0
    assert str(DEFAULT_CONFIG_ROOT.absolute()) in result.output, 'Configuration path text was not produced.'


def test_echo_logging_root(click_runner):
    version_args = ('--logging-path', )
    result = click_runner.invoke(nucypher_cli, version_args, catch_exceptions=False)
    assert result.exit_code == 0
    assert str(USER_LOG_DIR.absolute()) in result.output, 'Log path text was not produced.'
