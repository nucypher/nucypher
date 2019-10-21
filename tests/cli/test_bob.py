import os

from nucypher.cli.main import nucypher_cli
from nucypher.config.characters import BobConfiguration
from nucypher.utilities.sandbox.constants import INSECURE_DEVELOPMENT_PASSWORD, \
    MOCK_IP_ADDRESS, MOCK_CUSTOM_INSTALLATION_PATH, TEMPORARY_DOMAIN
from nucypher.cli.actions import SUCCESSFUL_DESTRUCTION


def test_bob_public_keys(click_runner):
    derive_key_args = ('bob', 'public-keys',
                       '--dev')

    result = click_runner.invoke(nucypher_cli, derive_key_args, catch_exceptions=False)

    assert result.exit_code == 0
    assert "bob_encrypting_key" in result.output
    assert "bob_verifying_key" in result.output


def test_initialize_bob_with_custom_configuration_root(custom_filepath, click_runner):
    # Use a custom local filepath for configuration
    init_args = ('bob', 'init',
                 '--network', TEMPORARY_DOMAIN,
                 '--federated-only',
                 '--config-root', custom_filepath)

    user_input = '{password}\n{password}'.format(password=INSECURE_DEVELOPMENT_PASSWORD, ip=MOCK_IP_ADDRESS)
    result = click_runner.invoke(nucypher_cli, init_args, input=user_input, catch_exceptions=False)
    assert result.exit_code == 0

    # CLI Output
    assert MOCK_CUSTOM_INSTALLATION_PATH in result.output, "Configuration not in system temporary directory"
    assert "nucypher bob run" in result.output, 'Help message is missing suggested command'
    assert 'IPv4' not in result.output

    # Files and Directories
    assert os.path.isdir(custom_filepath), 'Configuration file does not exist'
    assert os.path.isdir(os.path.join(custom_filepath, 'keyring')), 'Keyring does not exist'
    assert os.path.isdir(os.path.join(custom_filepath, 'known_nodes')), 'known_nodes directory does not exist'

    custom_config_filepath = os.path.join(custom_filepath, BobConfiguration.generate_filename())
    assert os.path.isfile(custom_config_filepath), 'Configuration file does not exist'

    # Auth
    assert 'Enter NuCypher keyring password:' in result.output, 'WARNING: User was not prompted for password'
    assert 'Repeat for confirmation:' in result.output, 'User was not prompted to confirm password'


def test_bob_control_starts_with_preexisting_configuration(click_runner, custom_filepath):
    custom_config_filepath = os.path.join(custom_filepath, BobConfiguration.generate_filename())

    init_args = ('bob', 'run',
                 '--dry-run',
                 '--config-file', custom_config_filepath)

    user_input = '{password}\n{password}\n'.format(password=INSECURE_DEVELOPMENT_PASSWORD)
    result = click_runner.invoke(nucypher_cli, init_args, input=user_input)
    assert result.exit_code == 0
    assert "Bob Verifying Key" in result.output
    assert "Bob Encrypting Key" in result.output


def test_bob_view_with_preexisting_configuration(click_runner, custom_filepath):
    custom_config_filepath = os.path.join(custom_filepath, BobConfiguration.generate_filename())

    view_args = ('bob', 'view',
                 '--config-file', custom_config_filepath)

    user_input = '{password}\n{password}\n'.format(password=INSECURE_DEVELOPMENT_PASSWORD)
    result = click_runner.invoke(nucypher_cli, view_args, input=user_input)

    assert result.exit_code == 0
    assert "checksum_address" in result.output
    assert "domains" in result.output
    assert TEMPORARY_DOMAIN in result.output
    assert custom_filepath in result.output


# Should be the last test since it deletes the configuration file
def test_bob_destroy(click_runner, custom_filepath):
    custom_config_filepath = os.path.join(custom_filepath, BobConfiguration.generate_filename())
    destroy_args = ('bob', 'destroy',
                    '--config-file', custom_config_filepath,
                    '--force')

    result = click_runner.invoke(nucypher_cli, destroy_args, catch_exceptions=False)
    assert result.exit_code == 0
    assert SUCCESSFUL_DESTRUCTION in result.output
    assert not os.path.exists(custom_config_filepath), "Bob config file was deleted"
