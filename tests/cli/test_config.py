import contextlib
import os
import shutil

from click.testing import CliRunner

from cli.main import cli
from nucypher.config.constants import DEFAULT_CONFIG_ROOT, DEFAULT_CONFIG_FILE_LOCATION
import pytest

from nucypher.config.node import NodeConfiguration


def test_initialize_configuration_directory():
    runner = CliRunner()

    # Use the system temporary storage area
    result = runner.invoke(cli, ['configure', 'init', '--temp'], input='Y', catch_exceptions=False)
    assert '/tmp' in result.output, "Configuration not in system temporary directory"
    assert NodeConfiguration.TEMP_CONFIGURATION_DIR_PREFIX in result.output
    assert result.exit_code == 0

    # Use an custom configuration directory
    custom_filepath = '/tmp/nucypher-tmp-test-custom'

    try:
        os.mkdir(custom_filepath)  # TODO: Create a top-level installation directory, instead of writing only subdirs

        args = ['configure', 'init', '--config-root', custom_filepath]
        result = runner.invoke(cli, args, input='Y', catch_exceptions=False)
        assert '[y/N]' in result.output
        assert '/tmp' in result.output, "Configuration not in system temporary directory"
        assert 'Created' in result.output
        assert custom_filepath in result.output
        assert result.exit_code == 0
        assert os.path.isdir(custom_filepath)

        assert True
        
        # Ensure that there are not pre-existing configuration files at config_root
        with pytest.raises(NodeConfiguration.ConfigurationError):
            _result = runner.invoke(cli, args, input='Y', catch_exceptions=False)

        args = ['configure', 'destroy', '--config-root', custom_filepath]
        result = runner.invoke(cli, args, input='Y', catch_exceptions=False)
        assert '[y/N]' in result.output
        assert '/tmp' in result.output, "Configuration not in system temporary directory"
        assert 'Deleted' in result.output
        assert custom_filepath in result.output
        assert result.exit_code == 0
        assert not os.path.isdir(custom_filepath)

    finally:
        with contextlib.suppress(FileNotFoundError):
            shutil.rmtree(custom_filepath)

    # # TODO: Integrate with run ursula


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
