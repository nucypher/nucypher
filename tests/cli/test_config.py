import contextlib
import os

import pytest
import shutil
from click.testing import CliRunner

from cli.main import cli
from nucypher.config.node import NodeConfiguration


@pytest.fixture(scope='function')
def custom_filepath():
    custom_filepath = '/tmp/nucypher-tmp-test-custom'
    yield custom_filepath
    with contextlib.suppress(FileNotFoundError):
        shutil.rmtree(custom_filepath)


@pytest.mark.skip()
def test_initialize_configuration_directory(custom_filepath):
    runner = CliRunner()

    # Use the system temporary storage area
    result = runner.invoke(cli, ['--dev', 'configure', 'install', '--no-registry'], input='Y', catch_exceptions=False)
    assert '/tmp' in result.output, "Configuration not in system temporary directory"
    assert NodeConfiguration._NodeConfiguration__TEMP_CONFIGURATION_DIR_PREFIX in result.output
    assert result.exit_code == 0

    args = ['--config-root', custom_filepath, 'configure', 'install', '--no-registry']
    result = runner.invoke(cli, args, input='Y', catch_exceptions=False)
    assert '[y/N]' in result.output, "'configure init' did not prompt the user before attempting to write files"
    assert '/tmp' in result.output, "Configuration not in system temporary directory"
    assert 'Created' in result.output
    assert custom_filepath in result.output
    assert result.exit_code == 0
    assert os.path.isdir(custom_filepath)

    # Ensure that there are not pre-existing configuration files at config_root
    with pytest.raises(NodeConfiguration.ConfigurationError):
        _result = runner.invoke(cli, args, input='Y', catch_exceptions=False)

    args = ['--config-root', custom_filepath, 'configure', 'destroy']
    result = runner.invoke(cli, args, input='Y', catch_exceptions=False)
    assert '[y/N]' in result.output
    assert '/tmp' in result.output, "Configuration not in system temporary directory"
    assert 'Deleted' in result.output
    assert custom_filepath in result.output
    assert result.exit_code == 0
    assert not os.path.isdir(custom_filepath)

    # # TODO: Integrate with run ursula


@pytest.mark.skip()
def test_validate_runtime_filepaths(custom_filepath):
    runner = CliRunner()

    args = ['--config-root', custom_filepath, 'configure', 'install', '--no-registry']
    result = runner.invoke(cli, args, input='Y', catch_exceptions=False)
    result = runner.invoke(cli, ['--config-root', custom_filepath,
                                 'configure', 'validate',
                                 '--filesystem',
                                 '--no-registry'], catch_exceptions=False)
    assert custom_filepath in result.output
    assert 'Valid' in result.output
    assert result.exit_code == 0

    # Remove the known nodes dir to "corrupt" the tree
    shutil.rmtree(os.path.join(custom_filepath, 'known_nodes'))
    result = runner.invoke(cli, ['--config-root', custom_filepath,
                                 'configure', 'validate',
                                 '--filesystem',
                                 '--no-registry'], catch_exceptions=False)
    assert custom_filepath in result.output
    assert 'Invalid' in result.output
    assert result.exit_code == 0  # TODO: exit differently for invalidity?
