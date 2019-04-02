import os

import pytest

from nucypher.blockchain.eth.registry import EthereumContractRegistry
from nucypher.cli import deploy
from nucypher.cli.main import nucypher_cli
from nucypher.config.keyring import NucypherKeyring
from nucypher.utilities.sandbox.constants import TEMPORARY_DOMAIN, INSECURE_DEVELOPMENT_PASSWORD, TEST_PROVIDER_URI, \
    MOCK_IP_ADDRESS, MOCK_IP_ADDRESS_2


def test_coexisting_configurations(click_runner,
                                   custom_filepath,
                                   mock_primary_registry_filepath,
                                   testerchain):

    # Parse node addresses
    deployer, alice, ursula, another_ursula, *all_yall = testerchain.interface.w3.eth.accounts

    envvars = {'NUCYPHER_KEYRING_PASSWORD': INSECURE_DEVELOPMENT_PASSWORD,
               'NUCYPHER_MINER_ESCROW_SECRET': INSECURE_DEVELOPMENT_PASSWORD,
               'NUCYPHER_POLICY_MANAGER_SECRET': INSECURE_DEVELOPMENT_PASSWORD,
               'NUCYPHER_USER_ESCROW_PROXY_SECRET': INSECURE_DEVELOPMENT_PASSWORD,
               'NUCYPHER_FELIX_DB_SECRET': INSECURE_DEVELOPMENT_PASSWORD}

    # Future configuration filepaths for assertions...
    public_keys_dir = os.path.join(custom_filepath, 'keyring', 'public')
    known_nodes_dir = os.path.join(custom_filepath, 'known_nodes')

    # ... Ensure they do not exist to begin with.
    assert not os.path.isdir(public_keys_dir)
    assert not os.path.isfile(known_nodes_dir)

    # Deploy contracts
    deploy_args = ('contracts',
                   '--registry-outfile', mock_primary_registry_filepath,
                   '--provider-uri', TEST_PROVIDER_URI,
                   '--deployer-address', deployer,
                   '--config-root', custom_filepath,
                   '--poa')

    result = click_runner.invoke(deploy.deploy, deploy_args, input='Y', catch_exceptions=False, env=envvars)
    assert result.exit_code == 0

    # No keys have been generated...
    with pytest.raises(FileNotFoundError):
        assert len(os.listdir(public_keys_dir)) == 0

    # No known nodes exist...
    with pytest.raises(FileNotFoundError):
        assert len(os.listdir(known_nodes_dir)) == 0

    # Just the configuration root...
    assert os.path.isdir(custom_filepath)

    # and the fresh registry.
    assert os.path.isfile(mock_primary_registry_filepath)

    #
    # Create
    #

    # Expected config files
    felix_file_location = os.path.join(custom_filepath, 'felix.config')
    alice_file_location = os.path.join(custom_filepath, 'alice.config')
    ursula_file_location = os.path.join(custom_filepath, 'ursula.config')
    another_ursula_configuration_file_location = os.path.join(custom_filepath, f'ursula-{another_ursula[:6]}.config')

    # Felix creates a system configuration
    felix_init_args = ('felix', 'init',
                       '--config-root', custom_filepath,
                       '--network', TEMPORARY_DOMAIN,
                       '--provider-uri', TEST_PROVIDER_URI,
                       '--checksum-address', deployer,
                       '--registry-filepath', mock_primary_registry_filepath
                       )

    result = click_runner.invoke(nucypher_cli, felix_init_args, catch_exceptions=False, env=envvars)
    assert result.exit_code == 0
    assert os.path.isfile(felix_file_location)
    assert len(os.listdir(public_keys_dir)) == 3

    # Use a custom local filepath to init a persistent Alice
    alice_init_args = ('alice', 'init',
                       '--network', TEMPORARY_DOMAIN,
                       '--provider-uri', TEST_PROVIDER_URI,
                       '--checksum-address', alice,
                       '--registry-filepath', mock_primary_registry_filepath,
                       '--config-root', custom_filepath)

    result = click_runner.invoke(nucypher_cli, alice_init_args, catch_exceptions=False, env=envvars)
    assert result.exit_code == 0
    assert os.path.isfile(alice_file_location)
    assert len(os.listdir(public_keys_dir)) == 5

    # Use the same local filepath to init a persistent Ursula
    init_args = ('ursula', 'init',
                 '--network', TEMPORARY_DOMAIN,
                 '--provider-uri', TEST_PROVIDER_URI,
                 '--checksum-address', ursula,
                 '--rest-host', MOCK_IP_ADDRESS,
                 '--registry-filepath', mock_primary_registry_filepath,
                 '--config-root', custom_filepath)

    result = click_runner.invoke(nucypher_cli, init_args, catch_exceptions=False, env=envvars)
    assert result.exit_code == 0
    assert len(os.listdir(public_keys_dir)) == 8
    assert os.path.isfile(ursula_file_location)

    # Use the same local filepath to init another persistent Ursula
    init_args = ('ursula', 'init',
                 '--network', TEMPORARY_DOMAIN,
                 '--checksum-address', another_ursula,
                 '--rest-host', MOCK_IP_ADDRESS_2,
                 '--registry-filepath', mock_primary_registry_filepath,
                 '--provider-uri', TEST_PROVIDER_URI,
                 '--config-root', custom_filepath)

    result = click_runner.invoke(nucypher_cli, init_args, catch_exceptions=False, env=envvars)
    assert result.exit_code == 0
    assert os.path.isfile(ursula_file_location)
    assert os.path.isfile(another_ursula_configuration_file_location)

    assert len(os.listdir(public_keys_dir)) == 11

    #
    # Run
    #

    # Run an Ursula amidst the other configuration files
    run_args = ('ursula', 'run', '--dry-run',
                '--config-file', another_ursula_configuration_file_location)

    user_input = f'{INSECURE_DEVELOPMENT_PASSWORD}'
    result = click_runner.invoke(nucypher_cli, run_args, input=user_input, catch_exceptions=False)
    assert result.exit_code == 0

    # Check that the proper Ursula console is attached
    assert another_ursula in result.output

    #
    # Destroy
    #

    another_ursula_destruction_args = ('ursula', 'destroy', '--force',
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

    felix_destruction_args = ('alice', 'destroy', '--force', '--config-file', alice_file_location)
    result = click_runner.invoke(nucypher_cli, felix_destruction_args, catch_exceptions=False, env=envvars)
    assert result.exit_code == 0
    assert len(os.listdir(public_keys_dir)) == 3
    assert not os.path.isfile(alice_file_location)

    felix_destruction_args = ('felix', 'destroy', '--force', '--config-file', felix_file_location)
    result = click_runner.invoke(nucypher_cli, felix_destruction_args, catch_exceptions=False, env=envvars)
    assert result.exit_code == 0
    assert len(os.listdir(public_keys_dir)) == 0
    assert not os.path.isfile(felix_file_location)


def test_destroy_with_no_configurations(click_runner, custom_filepath):
    """Provide useful error messages when attempting to destroy when there is nothing to destroy"""
    ursula_file_location = os.path.join(custom_filepath, 'ursula.config')
    destruction_args = ('ursula', 'destroy', '--config-file', ursula_file_location)
    result = click_runner.invoke(nucypher_cli, destruction_args, catch_exceptions=False)
    assert result.exit_code == 2
    assert 'Error: Invalid value for "--config-file":'
    assert f'"{ursula_file_location}" does not exist.' in result.output


def test_corrupted_configuration(click_runner, custom_filepath, testerchain, mock_primary_registry_filepath):
    deployer, alice, ursula, another_ursula, *all_yall = testerchain.interface.w3.eth.accounts

    init_args = ('ursula', 'init',
                 '--network', TEMPORARY_DOMAIN,
                 '--rest-host', MOCK_IP_ADDRESS,
                 '--config-root', custom_filepath)

    # Fails because password is too short and the command uses incomplete args (needs either -F or blockchain details)
    envvars = {'NUCYPHER_KEYRING_PASSWORD': ''}
    with pytest.raises(NucypherKeyring.AuthenticationFailed):
        result = click_runner.invoke(nucypher_cli, init_args, catch_exceptions=False, env=envvars)
        assert result.exit_code != 0

    # Ensure there is no unintentional file creation (keys, config, etc.)
    top_level_config_root = os.listdir(custom_filepath)
    assert 'ursula.config' not in top_level_config_root                         # no config file was created
    assert not os.listdir(os.path.join(custom_filepath, 'keyring', 'private'))  # no keys were created
    for field in ['known_nodes', 'keyring']:
        assert field in top_level_config_root                                   # only the empty default directories
        path = os.path.join(custom_filepath, field)
        assert os.path.isdir(path)
        assert len(os.listdir(path)) == 2   # public and private directories

    # Attempt installation again, with full args
    init_args = ('ursula', 'init',
                 '--network', TEMPORARY_DOMAIN,
                 '--provider-uri', TEST_PROVIDER_URI,
                 '--checksum-address', ursula,
                 '--rest-host', MOCK_IP_ADDRESS,
                 '--registry-filepath', mock_primary_registry_filepath,
                 '--config-root', custom_filepath)

    envvars = {'NUCYPHER_KEYRING_PASSWORD': INSECURE_DEVELOPMENT_PASSWORD}
    result = click_runner.invoke(nucypher_cli, init_args, catch_exceptions=False, env=envvars)
    assert result.exit_code == 0

    # Ensure configuration creation
    top_level_config_root = os.listdir(custom_filepath)
    assert 'ursula.config' in top_level_config_root                                    # config file was created
    assert len(os.listdir(os.path.join(custom_filepath, 'keyring', 'private'))) == 4   # keys were created
    for field in ['known_nodes', 'keyring', 'ursula.config']:
        assert field in top_level_config_root

    # "Corrupt" the configuration by removing the contract registry
    os.remove(mock_primary_registry_filepath)

    # Attempt destruction with invalid configuration (missing registry)
    ursula_file_location = os.path.join(custom_filepath, 'ursula.config')
    destruction_args = ('ursula', 'destroy', '--config-file', ursula_file_location)
    result = click_runner.invoke(nucypher_cli, destruction_args, input='Y\n', catch_exceptions=False, env=envvars)
    assert result.exit_code == 0

    # Ensure character destruction
    top_level_config_root = os.listdir(custom_filepath)
    assert 'ursula.config' not in top_level_config_root                                # config file was destroyed
    assert len(os.listdir(os.path.join(custom_filepath, 'keyring', 'private'))) == 0   # keys were destroyed


def test_nucypher_removal(click_runner, custom_filepath):
    """Remove all nucypher configuration files, keys, node metadata, and logs from the local filesystem"""

    # Remove nucypher completely
    destruction_args = ('remove', '--force', '--config-root', custom_filepath)
    result = click_runner.invoke(nucypher_cli, destruction_args, catch_exceptions=False)
    assert result.exit_code == 0
    assert not os.path.isdir(custom_filepath)

    # Everything is gone, but we'll try again anyways...
    destruction_args = ('remove', '--config-root', custom_filepath)
    result = click_runner.invoke(nucypher_cli, destruction_args, input='Y\n', catch_exceptions=False)
    assert result.exit_code == 0
    assert not os.path.isdir(custom_filepath)
    assert "No NuCypher configuration root directory found" in result.output  # Graceful crash
