import os

from nucypher.cli.main import nucypher_cli
from nucypher.config.characters import AliceConfiguration
from nucypher.utilities.sandbox.constants import INSECURE_DEVELOPMENT_PASSWORD, \
    MOCK_IP_ADDRESS, MOCK_CUSTOM_INSTALLATION_PATH, TEMPORARY_DOMAIN


def test_initialize_alice_defaults(click_runner, mocker):
    # Mock out filesystem writes
    mocker.patch.object(AliceConfiguration, 'initialize', autospec=True)
    mocker.patch.object(AliceConfiguration, 'to_configuration_file', autospec=True)

    # Use default alice init args
    init_args = ('alice', 'init',
                 '--network', TEMPORARY_DOMAIN,
                 '--federated-only')
    user_input = '{password}\n{password}\n'.format(password=INSECURE_DEVELOPMENT_PASSWORD)
    result = click_runner.invoke(nucypher_cli, init_args, input=user_input, catch_exceptions=False)
    assert result.exit_code == 0

    # REST Host
    assert "nucypher alice run" in result.output

    # Auth
    assert 'Enter keyring password:' in result.output, 'WARNING: User was not prompted for password'
    assert 'Repeat for confirmation:' in result.output, 'User was not prompted to confirm password'


def test_alice_control_starts_with_mocked_keyring(click_runner, mocker):

    class MockKeyring:
        is_unlocked = False

        @classmethod
        def unlock(cls, password, *args, **kwargs):
            assert password == INSECURE_DEVELOPMENT_PASSWORD
            cls.is_unlocked = True

    mocker.patch.object(AliceConfiguration, "attach_keyring", return_value=None)
    good_enough_config = AliceConfiguration(dev_mode=True, federated_only=True, keyring=MockKeyring)
    mocker.patch.object(AliceConfiguration, "from_configuration_file", return_value=good_enough_config)
    init_args = ('alice', 'run', '-x')

    user_input = '{password}\n{password}\n'.format(password=INSECURE_DEVELOPMENT_PASSWORD)
    result = click_runner.invoke(nucypher_cli, init_args, input=user_input)
    assert result.exit_code == 0, result.exception


def test_initialize_alice_with_custom_configuration_root(custom_filepath, click_runner):

    # Use a custom local filepath for configuration
    init_args = ('alice', 'init',
                 '--network', TEMPORARY_DOMAIN,
                 '--federated-only',
                 '--config-root', custom_filepath)

    user_input = '{password}\n{password}'.format(password=INSECURE_DEVELOPMENT_PASSWORD, ip=MOCK_IP_ADDRESS)
    result = click_runner.invoke(nucypher_cli, init_args, input=user_input, catch_exceptions=False)
    assert result.exit_code == 0

    # CLI Output
    assert MOCK_CUSTOM_INSTALLATION_PATH in result.output, "Configuration not in system temporary directory"
    assert "nucypher alice run" in result.output, 'Help message is missing suggested command'
    assert 'IPv4' not in result.output

    # Files and Directories
    assert os.path.isdir(custom_filepath), 'Configuration file does not exist'
    assert os.path.isdir(os.path.join(custom_filepath, 'keyring')), 'Keyring does not exist'
    assert os.path.isdir(os.path.join(custom_filepath, 'known_nodes')), 'known_nodes directory does not exist'

    custom_config_filepath = os.path.join(custom_filepath, AliceConfiguration.generate_filename())
    assert os.path.isfile(custom_config_filepath), 'Configuration file does not exist'

    # Auth
    assert 'Enter keyring password:' in result.output, 'WARNING: User was not prompted for password'
    assert 'Repeat for confirmation:' in result.output, 'User was not prompted to confirm password'


def test_alice_control_starts_with_preexisting_configuration(click_runner, custom_filepath):

    custom_config_filepath = os.path.join(custom_filepath, AliceConfiguration.generate_filename())

    init_args = ('alice', 'run',
                 '--dry-run',
                 '--config-file', custom_config_filepath)

    user_input = '{password}\n{password}\n'.format(password=INSECURE_DEVELOPMENT_PASSWORD)
    result = click_runner.invoke(nucypher_cli, init_args, input=user_input)
    assert result.exit_code == 0


def test_alice_cannot_init_with_dev_flag(click_runner):
    init_args = ('alice', 'init',
                 '--network', TEMPORARY_DOMAIN,
                 '--federated-only',
                 '--dev')
    result = click_runner.invoke(nucypher_cli, init_args, catch_exceptions=False)
    assert result.exit_code == 2
    assert 'Cannot create a persistent development character' in result.output, 'Missing or invalid error message was produced.'
