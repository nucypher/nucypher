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

import json
import os
from json import JSONDecodeError

import pytest

from nucypher.cli.main import nucypher_cli
from nucypher.config.characters import UrsulaConfiguration
from nucypher.config.constants import APP_DIR, DEFAULT_CONFIG_ROOT
from nucypher.utilities.sandbox.constants import (
    INSECURE_DEVELOPMENT_PASSWORD,
    MOCK_CUSTOM_INSTALLATION_PATH,
    MOCK_IP_ADDRESS,
    MOCK_URSULA_STARTING_PORT,
    TEMPORARY_DOMAIN)


def test_initialize_ursula_defaults(click_runner, mocker):

    # Mock out filesystem writes
    mocker.patch.object(UrsulaConfiguration, 'initialize', autospec=True)
    mocker.patch.object(UrsulaConfiguration, 'to_configuration_file', autospec=True)

    # Use default ursula init args
    init_args = ('ursula', 'init',
                 '--network', TEMPORARY_DOMAIN,
                 '--federated-only')

    user_input = '{ip}\n{password}\n{password}\n'.format(password=INSECURE_DEVELOPMENT_PASSWORD, ip=MOCK_IP_ADDRESS)
    result = click_runner.invoke(nucypher_cli, init_args, input=user_input, catch_exceptions=False)
    assert result.exit_code == 0

    # REST Host
    assert 'Enter Ursula\'s public-facing IPv4 address' in result.output

    # Auth
    assert 'Enter keyring password:' in result.output, 'WARNING: User was not prompted for password'
    assert 'Repeat for confirmation:' in result.output, 'User was not prompted to confirm password'


def test_initialize_custom_configuration_root(custom_filepath, click_runner):

    # Use a custom local filepath for configuration
    init_args = ('ursula', 'init',
                 '--network', TEMPORARY_DOMAIN,
                 '--federated-only',
                 '--config-root', custom_filepath,
                 '--rest-host', MOCK_IP_ADDRESS,
                 '--rest-port', MOCK_URSULA_STARTING_PORT)

    user_input = '{password}\n{password}'.format(password=INSECURE_DEVELOPMENT_PASSWORD)
    result = click_runner.invoke(nucypher_cli, init_args, input=user_input, catch_exceptions=False)
    assert result.exit_code == 0

    # CLI Output
    assert MOCK_CUSTOM_INSTALLATION_PATH in result.output, "Configuration not in system temporary directory"
    assert "nucypher ursula run" in result.output, 'Help message is missing suggested command'
    assert 'IPv4' not in result.output

    # Files and Directories
    assert os.path.isdir(custom_filepath), 'Configuration file does not exist'
    assert os.path.isdir(os.path.join(custom_filepath, 'keyring')), 'Keyring does not exist'
    assert os.path.isdir(os.path.join(custom_filepath, 'known_nodes')), 'known_nodes directory does not exist'

    custom_config_filepath = os.path.join(custom_filepath, UrsulaConfiguration.CONFIG_FILENAME)
    assert os.path.isfile(custom_config_filepath), 'Configuration file does not exist'

    # Auth
    assert 'Enter keyring password:' in result.output, 'WARNING: User was not prompted for password'
    assert 'Repeat for confirmation:' in result.output, 'User was not prompted to confirm password'


def test_configuration_file_contents(custom_filepath, nominal_federated_configuration_fields):
    custom_config_filepath = os.path.join(custom_filepath, UrsulaConfiguration.CONFIG_FILENAME)
    assert os.path.isfile(custom_config_filepath), 'Configuration file does not exist'

    # Check the contents of the configuration file
    with open(custom_config_filepath, 'r') as config_file:
        raw_contents = config_file.read()

        try:
            data = json.loads(raw_contents)
        except JSONDecodeError:
            raise pytest.fail(msg="Invalid JSON configuration file {}".format(custom_config_filepath))

        for field in nominal_federated_configuration_fields:
            assert field in data, "Missing field '{}' from configuration file."
            if any(keyword in field for keyword in ('path', 'dir')):
                path = data[field]
                user_data_dir = APP_DIR.user_data_dir
                # assert os.path.exists(path), '{} does not exist'.format(path)
                assert user_data_dir not in path, '{} includes default appdir path {}'.format(field, user_data_dir)

    assert os.path.isfile(custom_config_filepath), 'Configuration file does not exist'


def test_password_prompt(click_runner, custom_filepath):

    # Ensure the configuration file still exists
    custom_config_filepath = os.path.join(custom_filepath, UrsulaConfiguration.CONFIG_FILENAME)
    assert os.path.isfile(custom_config_filepath), 'Configuration file does not exist'

    view_args = ('ursula', 'view', '--config-file', custom_config_filepath)

    user_input = '{}\n'.format(INSECURE_DEVELOPMENT_PASSWORD)
    result = click_runner.invoke(nucypher_cli, view_args, input=user_input, catch_exceptions=False, env=dict())
    assert 'password' in result.output, 'WARNING: User was not prompted for password'
    assert result.exit_code == 0

    envvars = {'NUCYPHER_KEYRING_PASSWORD': INSECURE_DEVELOPMENT_PASSWORD}
    result = click_runner.invoke(nucypher_cli, view_args, input=user_input, catch_exceptions=False, env=envvars)
    assert not 'password' in result.output, 'User was prompted for password'
    assert result.exit_code == 0


def test_ursula_view_configuration(custom_filepath, click_runner, nominal_federated_configuration_fields):

    # Ensure the configuration file still exists
    custom_config_filepath = os.path.join(custom_filepath, UrsulaConfiguration.CONFIG_FILENAME)
    assert os.path.isfile(custom_config_filepath), 'Configuration file does not exist'

    view_args = ('ursula', 'view', '--config-file', os.path.join(custom_filepath, UrsulaConfiguration.CONFIG_FILENAME))

    # View the configuration
    result = click_runner.invoke(nucypher_cli, view_args,
                                 input='{}\n'.format(INSECURE_DEVELOPMENT_PASSWORD),
                                 catch_exceptions=False)

    # CLI Output
    assert 'password' in result.output, 'WARNING: User was not prompted for password'
    assert MOCK_CUSTOM_INSTALLATION_PATH in result.output
    for field in nominal_federated_configuration_fields:
        assert field in result.output, "Missing field '{}' from configuration file."

    # Make sure nothing crazy is happening...
    assert os.path.isfile(custom_config_filepath), 'Configuration file does not exist'


def test_run_federated_ursula_from_config_file(custom_filepath, click_runner):

    # Ensure the configuration file still exists
    custom_config_filepath = os.path.join(custom_filepath, UrsulaConfiguration.CONFIG_FILENAME)
    assert os.path.isfile(custom_config_filepath), 'Configuration file does not exist'

    # Run Ursula
    run_args = ('ursula', 'run',
                '--dry-run',
                '--config-file', custom_config_filepath)

    result = click_runner.invoke(nucypher_cli, run_args,
                                 input='{}\nY\n'.format(INSECURE_DEVELOPMENT_PASSWORD),
                                 catch_exceptions=False)

    # CLI Output
    assert result.exit_code == 0
    assert 'Federated' in result.output, 'WARNING: Federated ursula is not running in federated mode'
    assert 'Connecting' in result.output
    assert 'Running' in result.output
    assert 'Attached' in result.output
    assert "'help' or '?'" in result.output


def test_empty_federated_status(click_runner, custom_filepath):

    custom_config_filepath = os.path.join(custom_filepath, UrsulaConfiguration.CONFIG_FILENAME)
    assert os.path.isfile(custom_config_filepath), 'Configuration file does not exist'

    status_args = ('status', '--config-file', custom_config_filepath)
    result = click_runner.invoke(nucypher_cli, status_args, catch_exceptions=True)

    assert result.exit_code == 0

    assert 'Federated Only' in result.output
    heading = 'Known Nodes (connected 0 / seen 0)'
    assert heading in result.output
    assert 'password' not in result.output


def test_ursula_destroy_configuration(custom_filepath, click_runner):

    preexisting_live_configuration = os.path.isdir(DEFAULT_CONFIG_ROOT)
    preexisting_live_configuration_file = os.path.isfile(os.path.join(DEFAULT_CONFIG_ROOT,
                                                                      UrsulaConfiguration.CONFIG_FILENAME))

    # Ensure the configuration file still exists
    custom_config_filepath = os.path.join(custom_filepath, UrsulaConfiguration.CONFIG_FILENAME)
    assert os.path.isfile(custom_config_filepath), 'Configuration file does not exist'

    # Run the destroy command
    destruction_args = ('ursula', 'destroy', '--config-file', custom_config_filepath)
    result = click_runner.invoke(nucypher_cli, destruction_args,
                                 input='{}\nY\n'.format(INSECURE_DEVELOPMENT_PASSWORD),
                                 catch_exceptions=False)

    # CLI Output
    assert not os.path.isfile(custom_config_filepath), 'Configuration file still exists'
    assert 'password' in result.output, 'WARNING: User was not prompted for password'
    assert '? [y/N]:' in result.output, 'WARNING: User was not asked to destroy files'
    assert custom_filepath in result.output, 'WARNING: Configuration path not in output. Deleting the wrong path?'
    assert f'Deleted' in result.output, '"Destroyed" not in output'
    assert custom_filepath in result.output
    assert result.exit_code == 0, 'Destruction did not succeed'

    # Ensure the files are deleted from the filesystem
    assert not os.path.isfile(custom_config_filepath), 'Files still exist'   # ... shes's gone...
    assert os.path.isdir(custom_filepath), 'Nucypher files no longer exist'  # ... but not NuCypher ...

    # If this test started off with a live configuration, ensure it still exists
    if preexisting_live_configuration:
        configuration_still_exists = os.path.isdir(DEFAULT_CONFIG_ROOT)
        assert configuration_still_exists

    if preexisting_live_configuration_file:
        file_still_exists = os.path.isfile(os.path.join(DEFAULT_CONFIG_ROOT, UrsulaConfiguration.CONFIG_FILENAME))
        assert file_still_exists, 'WARNING: Test command deleted live non-test files'
