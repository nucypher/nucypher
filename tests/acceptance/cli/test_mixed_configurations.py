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

import os
import pytest
import shutil
from pathlib import Path

from nucypher.blockchain.eth.actors import Worker
from nucypher.cli.main import nucypher_cli
from nucypher.config.characters import AliceConfiguration, FelixConfiguration, UrsulaConfiguration
from nucypher.config.constants import NUCYPHER_ENVVAR_KEYRING_PASSWORD, TEMPORARY_DOMAIN
from nucypher.config.keyring import NucypherKeyring
from nucypher.network.nodes import Teacher
from tests.constants import (
    INSECURE_DEVELOPMENT_PASSWORD,
    MOCK_CUSTOM_INSTALLATION_PATH,
    MOCK_IP_ADDRESS,
    MOCK_IP_ADDRESS_2,
    TEST_PROVIDER_URI
)


@pytest.fixture(scope='function')
def custom_filepath():
    _path = str(MOCK_CUSTOM_INSTALLATION_PATH)
    shutil.rmtree(_path, ignore_errors=True)
    assert not Path(_path).exists()
    yield Path(_path)
    shutil.rmtree(_path, ignore_errors=True)


def test_destroy_with_no_configurations(click_runner, custom_filepath):
    """Provide useful error messages when attempting to destroy when there is nothing to destroy"""
    assert not custom_filepath.exists()
    ursula_file_location = custom_filepath / 'ursula.json'
    destruction_args = ('ursula', 'destroy', '--config-file', str(ursula_file_location))
    result = click_runner.invoke(nucypher_cli, destruction_args, catch_exceptions=False)
    assert result.exit_code == 2
    assert "Error: Invalid value for '--config-file':" in result.output
    assert str(ursula_file_location) in result.output
    assert not custom_filepath.exists()


def test_coexisting_configurations(click_runner,
                                   custom_filepath,
                                   testerchain,
                                   agency_local_registry):
    #
    # Setup
    #

    if custom_filepath.exists():
        shutil.rmtree(str(custom_filepath), ignore_errors=True)
    assert not custom_filepath.exists()

    # Parse node addresses
    # TODO: Is testerchain & Full contract deployment needed here (causes massive slowdown)?
    alice, ursula, another_ursula, felix, staker, *all_yall = testerchain.unassigned_accounts

    envvars = {NUCYPHER_ENVVAR_KEYRING_PASSWORD: INSECURE_DEVELOPMENT_PASSWORD,
               'NUCYPHER_FELIX_DB_SECRET': INSECURE_DEVELOPMENT_PASSWORD}

    # Future configuration filepaths for assertions...
    public_keys_dir = custom_filepath / 'keyring' / 'public'
    known_nodes_dir = custom_filepath / 'known_nodes'

    # ... Ensure they do not exist to begin with.

    # No keys have been generated...
    assert not public_keys_dir.exists()

    # No known nodes exist...
    assert not known_nodes_dir.exists()

    # Not the configuration root...
    assert not os.path.isdir(custom_filepath)

    # ... nothing
    None

    #
    # Create
    #

    # Expected config files
    felix_file_location = custom_filepath / FelixConfiguration.generate_filename()
    alice_file_location = custom_filepath / AliceConfiguration.generate_filename()
    ursula_file_location = custom_filepath / UrsulaConfiguration.generate_filename()
    another_ursula_configuration_file_location = custom_filepath / UrsulaConfiguration.generate_filename(modifier=another_ursula)

    # Felix creates a system configuration
    felix_init_args = ('felix', 'init',
                       '--config-root', custom_filepath,
                       '--network', TEMPORARY_DOMAIN,
                       '--provider', TEST_PROVIDER_URI,
                       '--checksum-address', felix,
                       '--registry-filepath', agency_local_registry.filepath,
                       '--debug')

    result = click_runner.invoke(nucypher_cli, felix_init_args, catch_exceptions=False, env=envvars)
    assert result.exit_code == 0

    # All configuration files still exist.
    assert os.path.isdir(custom_filepath)
    assert os.path.isfile(felix_file_location)
    assert os.path.isdir(public_keys_dir)
    assert len(os.listdir(public_keys_dir)) == 3

    # Use a custom local filepath to init a persistent Alice
    alice_init_args = ('alice', 'init',
                       '--network', TEMPORARY_DOMAIN,
                       '--provider', TEST_PROVIDER_URI,
                       '--pay-with', alice,
                       '--registry-filepath', agency_local_registry.filepath,
                       '--config-root', custom_filepath)

    result = click_runner.invoke(nucypher_cli, alice_init_args, catch_exceptions=False, env=envvars)
    assert result.exit_code == 0

    # All configuration files still exist.
    assert os.path.isfile(felix_file_location)
    assert os.path.isfile(alice_file_location)
    assert len(os.listdir(public_keys_dir)) == 5

    # Use the same local filepath to init a persistent Ursula
    init_args = ('ursula', 'init',
                 '--network', TEMPORARY_DOMAIN,
                 '--provider', TEST_PROVIDER_URI,
                 '--worker-address', ursula,
                 '--rest-host', MOCK_IP_ADDRESS,
                 '--registry-filepath', agency_local_registry.filepath,
                 '--config-root', custom_filepath)

    result = click_runner.invoke(nucypher_cli, init_args, catch_exceptions=False, env=envvars)
    assert result.exit_code == 0

    # All configuration files still exist.
    assert len(os.listdir(public_keys_dir)) == 8
    assert os.path.isfile(felix_file_location)
    assert os.path.isfile(alice_file_location)
    assert os.path.isfile(ursula_file_location)

    # Use the same local filepath to init another persistent Ursula
    init_args = ('ursula', 'init',
                 '--network', TEMPORARY_DOMAIN,
                 '--worker-address', another_ursula,
                 '--rest-host', MOCK_IP_ADDRESS_2,
                 '--registry-filepath', agency_local_registry.filepath,
                 '--provider', TEST_PROVIDER_URI,
                 '--config-root', custom_filepath)

    result = click_runner.invoke(nucypher_cli, init_args, catch_exceptions=False, env=envvars)
    assert result.exit_code == 0

    # All configuration files still exist.
    assert os.path.isfile(felix_file_location)
    assert os.path.isfile(alice_file_location)
    assert os.path.isfile(another_ursula_configuration_file_location)
    assert os.path.isfile(ursula_file_location)
    assert len(os.listdir(public_keys_dir)) == 11

    #
    # Run
    #

    # Run an Ursula amidst the other configuration files
    run_args = ('ursula', 'run',
                '--dry-run',
                '--config-file', another_ursula_configuration_file_location)

    user_input = f'{INSECURE_DEVELOPMENT_PASSWORD}\n' * 2

    Worker.BONDING_POLL_RATE = 1
    Worker.BONDING_TIMEOUT = 1
    with pytest.raises(Teacher.UnbondedWorker):  # TODO: Why is this being checked here?
        # Worker init success, but not bonded.
        result = click_runner.invoke(nucypher_cli, run_args, input=user_input, catch_exceptions=False)
    assert result.exit_code == 0
    Worker.BONDING_TIMEOUT = None

    # All configuration files still exist.
    assert os.path.isfile(felix_file_location)
    assert os.path.isfile(alice_file_location)
    assert os.path.isfile(another_ursula_configuration_file_location)
    assert os.path.isfile(ursula_file_location)
    assert len(os.listdir(public_keys_dir)) == 11

    # Check that the proper Ursula console is attached
    assert another_ursula in result.output

    #
    # Destroy
    #

    another_ursula_destruction_args = ('ursula', 'destroy',
                                       '--force',
                                       '--config-file', another_ursula_configuration_file_location)
    result = click_runner.invoke(nucypher_cli, another_ursula_destruction_args, catch_exceptions=False, env=envvars)
    assert result.exit_code == 0
    assert len(os.listdir(public_keys_dir)) == 8
    assert not os.path.isfile(another_ursula_configuration_file_location)

    ursula_destruction_args = ('ursula', 'destroy', '--config-file', ursula_file_location)
    result = click_runner.invoke(nucypher_cli, ursula_destruction_args, input='Y', catch_exceptions=False, env=envvars)
    assert result.exit_code == 0
    assert 'y/N' in result.output
    assert len(os.listdir(public_keys_dir)) == 5
    assert not os.path.isfile(ursula_file_location)

    alice_destruction_args = ('alice', 'destroy', '--force', '--config-file', alice_file_location)
    result = click_runner.invoke(nucypher_cli, alice_destruction_args, catch_exceptions=False, env=envvars)
    assert result.exit_code == 0
    assert len(os.listdir(public_keys_dir)) == 3
    assert not os.path.isfile(alice_file_location)

    felix_destruction_args = ('felix', 'destroy', '--force', '--config-file', felix_file_location)
    result = click_runner.invoke(nucypher_cli, felix_destruction_args, catch_exceptions=False, env=envvars)
    assert result.exit_code == 0
    assert len(os.listdir(public_keys_dir)) == 0
    assert not os.path.isfile(felix_file_location)


def test_corrupted_configuration(click_runner,
                                 custom_filepath,
                                 testerchain,
                                 agency_local_registry):

    #
    # Setup
    #

    # Please tell me why
    if custom_filepath.exists():
        shutil.rmtree(custom_filepath, ignore_errors=True)
    assert not custom_filepath.exists()
    
    alice, ursula, another_ursula, felix, staker, *all_yall = testerchain.unassigned_accounts

    #
    # Chaos
    #

    init_args = ('ursula', 'init',
                 '--provider', TEST_PROVIDER_URI,
                 '--worker-address', another_ursula,
                 '--network', TEMPORARY_DOMAIN,
                 '--rest-host', MOCK_IP_ADDRESS,
                 '--config-root', custom_filepath,
                 )

    # Fails because password is too short and the command uses incomplete args (needs either -F or blockchain details)
    envvars = {NUCYPHER_ENVVAR_KEYRING_PASSWORD: ''}

    with pytest.raises(NucypherKeyring.AuthenticationFailed):
        result = click_runner.invoke(nucypher_cli, init_args, catch_exceptions=False, env=envvars)
        assert result.exit_code != 0

    # Ensure there is no unintentional file creation (keys, config, etc.)
    top_level_config_root = os.listdir(custom_filepath)
    assert 'ursula.config' not in top_level_config_root                         # no config file was created

    assert Path(custom_filepath).exists()
    keyring = custom_filepath / 'keyring'
    assert not keyring.exists()

    known_nodes = 'known_nodes'
    path = custom_filepath / known_nodes
    assert not path.exists()

    # Attempt installation again, with full args
    init_args = ('ursula', 'init',
                 '--network', TEMPORARY_DOMAIN,
                 '--provider', TEST_PROVIDER_URI,
                 '--worker-address', another_ursula,
                 '--rest-host', MOCK_IP_ADDRESS,
                 '--registry-filepath', agency_local_registry.filepath,
                 '--config-root', custom_filepath)

    envvars = {NUCYPHER_ENVVAR_KEYRING_PASSWORD: INSECURE_DEVELOPMENT_PASSWORD}
    result = click_runner.invoke(nucypher_cli, init_args, catch_exceptions=False, env=envvars)
    assert result.exit_code == 0

    default_filename = UrsulaConfiguration.generate_filename()

    # Ensure configuration creation
    top_level_config_root = os.listdir(custom_filepath)
    assert default_filename in top_level_config_root, "JSON configuration file was not created"
    assert len(os.listdir(custom_filepath / 'keyring' / 'private')) == 4   # keys were created
    for field in ['known_nodes', 'keyring', default_filename]:
        assert field in top_level_config_root

    # "Corrupt" the configuration by removing the contract registry
    os.remove(agency_local_registry.filepath)

    # Attempt destruction with invalid configuration (missing registry)
    ursula_file_location = custom_filepath / default_filename
    destruction_args = ('ursula', 'destroy', '--debug', '--config-file', ursula_file_location)
    result = click_runner.invoke(nucypher_cli, destruction_args, input='Y\n', catch_exceptions=False, env=envvars)
    assert result.exit_code == 0

    # Ensure character destruction
    top_level_config_root = os.listdir(custom_filepath)
    assert default_filename not in top_level_config_root                               # config file was destroyed
    assert len(os.listdir(custom_filepath / 'keyring' / 'private')) == 0   # keys were destroyed
