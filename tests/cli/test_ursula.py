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
import json
import os
from json import JSONDecodeError

import pytest
import shutil

from nucypher.cli.main import nucypher_cli
from nucypher.cli.protocol import UrsulaCommandProtocol
from nucypher.config.characters import UrsulaConfiguration
from nucypher.config.constants import APP_DIR
from nucypher.utilities.sandbox.constants import INSECURE_DEVELOPMENT_PASSWORD, MOCK_CUSTOM_INSTALLATION_PATH, \
    MOCK_IP_ADDRESS


@pytest.fixture(scope='module')
def nominal_configuration_fields():
    config = UrsulaConfiguration(dev_mode=True)
    config_fields = config.static_payload
    del config_fields['is_me']
    yield tuple(config_fields.keys())
    del config


@pytest.fixture(scope='module')
def custom_filepath():
    custom_filepath = MOCK_CUSTOM_INSTALLATION_PATH

    with contextlib.suppress(FileNotFoundError):
        shutil.rmtree(custom_filepath, ignore_errors=True)
    try:
        yield custom_filepath
    finally:
        with contextlib.suppress(FileNotFoundError):
            shutil.rmtree(custom_filepath, ignore_errors=True)


def test_initialize_configuration_files_and_directories(custom_filepath, click_runner):
    init_args = ('ursula', 'init', '--config-root', custom_filepath, '--rest-port', '64454')

    # Use a custom local filepath for configuration
    user_input = '{password}\n{password}\n{ip}\n'.format(password=INSECURE_DEVELOPMENT_PASSWORD, ip=MOCK_IP_ADDRESS)
    result = click_runner.invoke(nucypher_cli, init_args, input=user_input, catch_exceptions=False)
    assert result.exit_code == 0

    assert 'password' in result.output, 'WARNING: User was not prompted for password'
    assert MOCK_CUSTOM_INSTALLATION_PATH in result.output, "Configuration not in system temporary directory"
    assert "nucypher ursula run" in result.output, 'Help message is missing suggested command'
    assert os.path.isdir(custom_filepath), 'Configuration file does not exist'
    assert os.path.isdir(os.path.join(custom_filepath, 'keyring')), 'Keyring does not exist'
    assert os.path.isdir(os.path.join(custom_filepath, 'known_nodes')), 'known_nodes directory does not exist'


def test_configuration_file_contents(custom_filepath, nominal_configuration_fields):
    custom_config_filepath = os.path.join(custom_filepath, UrsulaConfiguration.CONFIG_FILENAME)
    assert os.path.isfile(custom_config_filepath), 'Configuration file does not exist'

    # Check the contents of the configuration file
    with open(custom_config_filepath, 'r') as config_file:
        raw_contents = config_file.read()

        try:
            data = json.loads(raw_contents)
        except JSONDecodeError:
            raise pytest.fail(msg="Invalid JSON configuration file {}".format(custom_config_filepath))

        for field in nominal_configuration_fields:
            assert field in data, "Missing field '{}' from configuration file."
            if any(keyword in field for keyword in ('path', 'dir')):
                path = data[field]
                user_data_dir = APP_DIR.user_data_dir
                # assert os.path.exists(path), '{} does not exist'.format(path)
                assert user_data_dir not in path, '{} includes default appdir path {}'.format(field, user_data_dir)


def test_ursula_view_configuration(custom_filepath, click_runner, nominal_configuration_fields):
    custom_config_filepath = os.path.join(custom_filepath, UrsulaConfiguration.CONFIG_FILENAME)
    view_args = ('ursula', 'view', '--config-file', os.path.join(custom_filepath, 'ursula.config'))

    # View the configuration
    result = click_runner.invoke(nucypher_cli, view_args,
                                 input='{}\n'.format(INSECURE_DEVELOPMENT_PASSWORD),
                                 catch_exceptions=False)

    assert 'password' in result.output, 'WARNING: User was not prompted for password'
    assert MOCK_CUSTOM_INSTALLATION_PATH in result.output
    for field in nominal_configuration_fields:
        assert field in result.output, "Missing field '{}' from configuration file."

    # Make sure nothing crazy is happening...
    assert os.path.isfile(custom_config_filepath), 'Configuration file does not exist'


@pytest.mark.skip  # TODO
def test_run_ursula(custom_filepath, click_runner):
    custom_config_filepath = os.path.join(custom_filepath, UrsulaConfiguration.CONFIG_FILENAME)
    run_args = ('ursula', 'run', '--config-file', custom_config_filepath)

    result = click_runner.invoke(nucypher_cli, run_args,
                                 input='{}\nY\n'.format(INSECURE_DEVELOPMENT_PASSWORD),
                                 catch_exceptions=False)

    assert result.exit_code == 0
    assert 'password' in result.output, 'WARNING: User was not prompted for password'
    assert '? [y/N]:' in result.output, 'WARNING: User was to run Ursula'
    assert '>>>' in result.output


def test_ursula_init_does_not_overrides_existing_files(custom_filepath, click_runner):
    custom_config_filepath = os.path.join(custom_filepath, UrsulaConfiguration.CONFIG_FILENAME)
    init_args = ('ursula', 'init', '--config-root', custom_filepath, '--rest-host', MOCK_IP_ADDRESS)

    # Ensure that an existing configuration directory cannot be overridden
    with pytest.raises(UrsulaConfiguration.ConfigurationError):
        _bad_result = click_runner.invoke(nucypher_cli, init_args,
                                          input='{}\n'.format(INSECURE_DEVELOPMENT_PASSWORD),
                                          catch_exceptions=False)

        assert 'password' in _bad_result.output, 'WARNING: User was not prompted for password'

    # Really we want to keep this file until its destroyed
    assert os.path.isfile(custom_config_filepath), 'Configuration file does not exist'


def test_ursula_destroy_configuration(custom_filepath, click_runner):
    custom_config_filepath = os.path.join(custom_filepath, UrsulaConfiguration.CONFIG_FILENAME)
    destruction_args = ('ursula', 'destroy', '--config-file', custom_config_filepath)

    result = click_runner.invoke(nucypher_cli, destruction_args,
                                 input='{}\nY\n'.format(INSECURE_DEVELOPMENT_PASSWORD),
                                 catch_exceptions=False)

    assert 'password' in result.output, 'WARNING: User was not prompted for password'
    assert '? [y/N]:' in result.output, 'WARNING: User was not asked to destroy files'
    assert custom_filepath in result.output, 'WARNING: Configuration path not in output. Deleting the wrong path?'
    assert 'Deleted' in result.output, '"Deleted" not in output'
    assert result.exit_code == 0, 'Destruction did not succeed'

    # Ensure the files are deleted from the filesystem
    assert not os.path.isfile(custom_config_filepath), 'Files still exist'   # ... it's gone...
    assert not os.path.isdir(custom_filepath), 'Nucypher files still exist'  # it's all gone...
