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
import contextlib
import os

import pytest
import shutil
from click.testing import CliRunner

from nucypher.cli import cli
from nucypher.config.node import NodeConfiguration
from nucypher.utilities.sandbox.constants import TEST_URSULA_INSECURE_DEVELOPMENT_PASSWORD


TEST_CUSTOM_INSTALLATION_PATH = '/tmp/nucypher-tmp-test-custom'


@pytest.fixture(scope='function')
def custom_filepath():
    custom_filepath = TEST_CUSTOM_INSTALLATION_PATH
    yield custom_filepath
    with contextlib.suppress(FileNotFoundError):
        shutil.rmtree(custom_filepath, ignore_errors=True)


@pytest.mark.skip()
def test_initialize_configuration_files_and_directories(custom_filepath):
    runner = CliRunner()

    # Use the system temporary storage area
    args = ['--dev', '--federated-only', 'configure', 'install', '--ursula', '--force']
    result = runner.invoke(cli, args,
                           input='{}\n{}'''.format(TEST_URSULA_INSECURE_DEVELOPMENT_PASSWORD,
                                                   TEST_URSULA_INSECURE_DEVELOPMENT_PASSWORD),
                           catch_exceptions=False)
    assert '/tmp' in result.output, "Configuration not in system temporary directory"
    assert NodeConfiguration._NodeConfiguration__TEMP_CONFIGURATION_DIR_PREFIX in result.output
    assert result.exit_code == 0

    # Use a custom local filepath
    args = ['--config-root', custom_filepath, '--federated-only', 'configure', 'install', '--ursula', '--force']
    result = runner.invoke(cli, args,
                           input='{}\n{}'''.format(TEST_URSULA_INSECURE_DEVELOPMENT_PASSWORD,
                                                   TEST_URSULA_INSECURE_DEVELOPMENT_PASSWORD),
                           catch_exceptions=False)
    assert TEST_CUSTOM_INSTALLATION_PATH in result.output, "Configuration not in system temporary directory"
    assert 'Created' in result.output
    assert custom_filepath in result.output
    assert "'nucypher ursula run'" in result.output
    assert result.exit_code == 0
    assert os.path.isdir(custom_filepath)

    # Ensure that there are not pre-existing configuration files at config_root
    _result = runner.invoke(cli, args,
                           input='{}\n{}'''.format(TEST_URSULA_INSECURE_DEVELOPMENT_PASSWORD,
                                                   TEST_URSULA_INSECURE_DEVELOPMENT_PASSWORD),
                           catch_exceptions=False)
    assert "There are existing configuration files" in _result.output

    # Destroy / Uninstall
    args = ['--config-root', custom_filepath, 'configure', 'destroy']
    result = runner.invoke(cli, args, input='Y', catch_exceptions=False)
    assert '[y/N]' in result.output
    assert TEST_CUSTOM_INSTALLATION_PATH in result.output, "Configuration not in system temporary directory"
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
