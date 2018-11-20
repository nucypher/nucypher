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

from nucypher.cli.main import nucypher_cli
from nucypher.config.node import NodeConfiguration
from nucypher.utilities.sandbox.constants import TEST_URSULA_INSECURE_DEVELOPMENT_PASSWORD


TEST_CUSTOM_INSTALLATION_PATH = '/tmp/nucypher-tmp-test-custom'


@pytest.fixture(scope='function')
def custom_filepath():
    custom_filepath = TEST_CUSTOM_INSTALLATION_PATH

    with contextlib.suppress(FileNotFoundError):
        shutil.rmtree(custom_filepath, ignore_errors=True)
    try:
        yield custom_filepath
    finally:
        with contextlib.suppress(FileNotFoundError):
            shutil.rmtree(custom_filepath, ignore_errors=True)


def test_initialize_configuration_files_and_directories(custom_filepath):
    runner = CliRunner()

    # Use a custom local filepath
    args = ['ursula', 'init', '--config-root', custom_filepath, '--rest-host', '0.0.0.0']
    result = runner.invoke(nucypher_cli, args,
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
    _result = runner.invoke(nucypher_cli, ('ursula', 'view', '--config-file', os.path.join(custom_filepath, 'ursula.config')), catch_exceptions=False)
    assert TEST_CUSTOM_INSTALLATION_PATH in _result.output

    # TODO : Crash earlier
    # And that existing configurations are not accidentally overridden
    _result = runner.invoke(nucypher_cli, args,
                            input='{}\n{}'''.format(TEST_URSULA_INSECURE_DEVELOPMENT_PASSWORD,
                                                    TEST_URSULA_INSECURE_DEVELOPMENT_PASSWORD),
                            catch_exceptions=False)
    assert "There are existing configuration files" in _result.output

    # Destroy / Uninstall
    args = ['ursula', 'destroy', '--config-root', custom_filepath]
    result = runner.invoke(nucypher_cli, args, input='Y', catch_exceptions=False)
    assert '[y/N]' in result.output
    assert TEST_CUSTOM_INSTALLATION_PATH in result.output, "Configuration not in system temporary directory"
    assert 'Deleted' in result.output
    assert custom_filepath in result.output
    assert result.exit_code == 0
    assert not os.path.isdir(custom_filepath)
