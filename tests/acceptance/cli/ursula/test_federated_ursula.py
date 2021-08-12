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
from json import JSONDecodeError

import os
from pathlib import Path

from unittest.mock import PropertyMock

import pytest

from nucypher.cli.literature import SUCCESSFUL_DESTRUCTION, COLLECT_NUCYPHER_PASSWORD
from nucypher.cli.main import nucypher_cli
from nucypher.config.base import CharacterConfiguration
from nucypher.config.characters import UrsulaConfiguration
from nucypher.config.constants import APP_DIR, DEFAULT_CONFIG_ROOT, NUCYPHER_ENVVAR_KEYSTORE_PASSWORD, TEMPORARY_DOMAIN
from nucypher.crypto.keystore import Keystore
from tests.constants import (
    FAKE_PASSWORD_CONFIRMED, INSECURE_DEVELOPMENT_PASSWORD,
    MOCK_CUSTOM_INSTALLATION_PATH,
    MOCK_IP_ADDRESS, YES_ENTER)
from tests.utils.ursula import MOCK_URSULA_STARTING_PORT, select_test_port


def test_initialize_ursula_defaults(click_runner, mocker, tmpdir):

    # Mock out filesystem writes
    mocker.patch.object(UrsulaConfiguration, 'initialize', autospec=True)
    mocker.patch.object(UrsulaConfiguration, 'to_configuration_file', autospec=True)

    # Mock Keystore init
    keystore = Keystore.generate(keystore_dir=tmpdir, password=INSECURE_DEVELOPMENT_PASSWORD)
    mocker.patch.object(CharacterConfiguration, 'keystore', return_value=keystore, new_callable=PropertyMock)

    # Use default ursula init args
    init_args = ('ursula', 'init', '--network', TEMPORARY_DOMAIN, '--federated-only')

    user_input = YES_ENTER + FAKE_PASSWORD_CONFIRMED
    result = click_runner.invoke(nucypher_cli, init_args, input=user_input, catch_exceptions=False)
    assert result.exit_code == 0

    # REST Host
    assert "Is this the public-facing address of Ursula? " in result.output

    # Auth
    assert COLLECT_NUCYPHER_PASSWORD in result.output, 'WARNING: User was not prompted for password'
    assert 'Repeat for confirmation:' in result.output, 'User was not prompted to confirm password'


def test_initialize_custom_configuration_root(click_runner, custom_filepath: Path):

    deploy_port = select_test_port()
    # Use a custom local filepath for configuration
    init_args = ('ursula', 'init',
                 '--network', TEMPORARY_DOMAIN,
                 '--federated-only',
                 '--config-root', str(custom_filepath.absolute()),
                 '--rest-host', MOCK_IP_ADDRESS,
                 '--rest-port', deploy_port)
    result = click_runner.invoke(nucypher_cli, init_args, input=FAKE_PASSWORD_CONFIRMED, catch_exceptions=False)
    assert result.exit_code == 0

    # CLI Output
    assert str(MOCK_CUSTOM_INSTALLATION_PATH) in result.output, "Configuration not in system temporary directory"
    assert "nucypher ursula run" in result.output, 'Help message is missing suggested command'
    assert 'IPv4' not in result.output

    # Files and Directories
    assert custom_filepath.is_dir(), 'Configuration file does not exist'
    assert (custom_filepath / 'keystore').is_dir(), 'KEYSTORE does not exist'
    assert (custom_filepath / 'known_nodes').is_dir(), 'known_nodes directory does not exist'

    custom_config_filepath = custom_filepath / UrsulaConfiguration.generate_filename()
    assert custom_config_filepath.is_file(), 'Configuration file does not exist'

    # Auth
    assert COLLECT_NUCYPHER_PASSWORD in result.output, 'WARNING: User was not prompted for password'
    assert 'Repeat for confirmation:' in result.output, 'User was not prompted to confirm password'


def test_configuration_file_contents(custom_filepath: Path, nominal_federated_configuration_fields):
    custom_config_filepath = custom_filepath / UrsulaConfiguration.generate_filename()
    assert custom_config_filepath.is_file(), 'Configuration file does not exist'

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

    assert custom_config_filepath.is_file(), 'Configuration file does not exist'


def test_ursula_view_configuration(custom_filepath: Path, click_runner, nominal_federated_configuration_fields):

    # Ensure the configuration file still exists
    custom_config_filepath = custom_filepath / UrsulaConfiguration.generate_filename()
    assert custom_config_filepath.is_file(), 'Configuration file does not exist'

    view_args = ('ursula', 'config', '--config-file', str(custom_config_filepath.absolute()))

    # View the configuration
    result = click_runner.invoke(nucypher_cli, view_args,
                                 input='{}\n'.format(INSECURE_DEVELOPMENT_PASSWORD),
                                 catch_exceptions=False)

    # CLI Output
    assert str(MOCK_CUSTOM_INSTALLATION_PATH) in result.output
    for field in nominal_federated_configuration_fields:
        assert field in result.output, "Missing field '{}' from configuration file."

    # Make sure nothing crazy is happening...
    assert custom_config_filepath.is_file(), 'Configuration file does not exist'


def test_run_federated_ursula_from_config_file(custom_filepath: Path, click_runner):

    # Ensure the configuration file still exists
    custom_config_filepath = custom_filepath / UrsulaConfiguration.generate_filename()
    assert custom_config_filepath.is_file(), 'Configuration file does not exist'

    # Run Ursula
    run_args = ('ursula', 'run',
                '--dry-run',
                '--interactive',
                '--lonely',
                '--config-file', str(custom_config_filepath.absolute()))

    result = click_runner.invoke(nucypher_cli, run_args,
                                 input='{}\nY\n'.format(INSECURE_DEVELOPMENT_PASSWORD),
                                 catch_exceptions=False)

    # CLI Output
    assert result.exit_code == 0, result.output
    assert 'Federated' in result.output, 'WARNING: Federated ursula is not running in federated mode'
    assert 'Running' in result.output
    assert "'help' or '?'" in result.output


def test_ursula_save_metadata(click_runner, custom_filepath):
    # Run Ursula
    save_metadata_args = ('ursula', 'save-metadata',
                          '--dev',
                          '--federated-only')

    result = click_runner.invoke(nucypher_cli, save_metadata_args, catch_exceptions=False)

    assert result.exit_code == 0
    assert "Successfully saved node metadata" in result.output, "Node metadata successfully saved"


# Should be the last test since it deletes the configuration file
def test_ursula_destroy_configuration(custom_filepath, click_runner):

    preexisting_live_configuration = DEFAULT_CONFIG_ROOT.is_dir()
    preexisting_live_configuration_file = (DEFAULT_CONFIG_ROOT / UrsulaConfiguration.generate_filename()).is_file()

    # Ensure the configuration file still exists
    custom_config_filepath = custom_filepath / UrsulaConfiguration.generate_filename()
    assert custom_config_filepath.is_file(), 'Configuration file does not exist'

    # Run the destroy command
    destruction_args = ('ursula', 'destroy', '--config-file', str(custom_config_filepath.absolute()))
    result = click_runner.invoke(nucypher_cli, destruction_args,
                                 input='Y\n'.format(INSECURE_DEVELOPMENT_PASSWORD),
                                 catch_exceptions=False,
                                 env={NUCYPHER_ENVVAR_KEYSTORE_PASSWORD: INSECURE_DEVELOPMENT_PASSWORD})

    # CLI Output
    assert not custom_config_filepath.is_file(), 'Configuration file still exists'
    assert '? [y/N]:' in result.output, 'WARNING: User was not asked to destroy files'
    assert str(custom_filepath) in result.output, 'WARNING: Configuration path not in output. Deleting the wrong path?'
    assert SUCCESSFUL_DESTRUCTION in result.output, '"Destroyed" not in output'
    assert str(custom_filepath) in result.output
    assert result.exit_code == 0, 'Destruction did not succeed'

    # Ensure the files are deleted from the filesystem
    assert not custom_config_filepath.is_file(), 'Files still exist'   # ... shes's gone...
    assert custom_filepath.is_dir(), 'Nucypher files no longer exist'  # ... but not NuCypher ...

    # If this test started off with a live configuration, ensure it still exists
    if preexisting_live_configuration:
        configuration_still_exists = DEFAULT_CONFIG_ROOT.is_dir()
        assert configuration_still_exists

    if preexisting_live_configuration_file:
        file_still_exists = (DEFAULT_CONFIG_ROOT / UrsulaConfiguration.generate_filename()).is_file()
        assert file_still_exists, 'WARNING: Test command deleted live non-test files'
