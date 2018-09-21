import contextlib
import os
import shutil

from click.testing import CliRunner

from cli.main import cli
from nucypher.config.constants import DEFAULT_CONFIG_ROOT, DEFAULT_CONFIG_FILE_LOCATION
import pytest

from nucypher.config.node import NodeConfiguration


def test_initialize_temp_configuration_directory(temp_config_root):
    runner = CliRunner()

    result = runner.invoke(cli, ['configure', 'init', '--temp'], input='Y', catch_exceptions=False)
    assert '/tmp' in result.output, "Configuration not in system temporary directory"
    assert NodeConfiguration.TEMP_CONFIGURATION_DIR_PREFIX in result.output
    assert result.exit_code == 0

    result = runner.invoke(cli, ['configure', 'destroy', '--temp'], input='Y', catch_exceptions=False)
    assert NodeConfiguration.TEMP_CONFIGURATION_DIR_PREFIX in result.output
    assert result.exit_code == 0

    args = ['configure', 'init', '--config-root', temp_config_root]
    result = runner.invoke(cli, args, input='Y', catch_exceptions=False)
    assert '/tmp' in result.output, "Configuration not in system temporary directory"
    assert temp_config_root in result.output
    assert result.exit_code == 0

    args = ['configure', 'destroy', '--config-root', temp_config_root]
    result = runner.invoke(cli, args, input='Y', catch_exceptions=False)
    assert temp_config_root in result.output
    assert result.exit_code == 0


@pytest.mark.skip("To be implemented")
def test_write_default_configuration_file():
    runner = CliRunner()

    result = runner.invoke(cli, ['configure', 'init', '--temp'], input='Y', catch_exceptions=False)
    assert DEFAULT_CONFIG_ROOT in result.output
    assert result.exit_code == 0

    assert os.path.isfile(DEFAULT_CONFIG_FILE_LOCATION)
    with open(DEFAULT_CONFIG_FILE_LOCATION, 'r') as ini_file:
        assert ini_file.read()
        config_payload = ini_file.read()
        assert '[nucypher]' in config_payload

    result = runner.invoke(cli, ['configure', 'destroy'], input='Y', catch_exceptions=False)
    assert DEFAULT_CONFIG_ROOT in result.output
    assert result.exit_code == 0
    assert not os.path.isfile(DEFAULT_CONFIG_FILE_LOCATION)


@pytest.mark.skip("To be implemented")
def test_validate_configuration_file():
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ['configure', 'validate'], catch_exceptions=False)
        assert 'Valid'.casefold() in result.output
        assert result.exit_code == 0
