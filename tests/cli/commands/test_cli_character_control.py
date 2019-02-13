from nucypher.cli.main import nucypher_cli
from nucypher.config.characters import AliceConfiguration
from nucypher.utilities.sandbox.constants import MOCK_URSULA_STARTING_PORT, INSECURE_DEVELOPMENT_PASSWORD, \
    MOCK_IP_ADDRESS


def test_initialize_alice_defaults(click_runner, mocker):
    # Mock out filesystem writes
    mocker.patch.object(AliceConfiguration, 'initialize', autospec=True)
    mocker.patch.object(AliceConfiguration, 'to_configuration_file', autospec=True)

    # Use default ursula init args
    init_args = ('alice', 'init', '--federated-only')
    user_input = '{password}\n{password}\n'.format(password=INSECURE_DEVELOPMENT_PASSWORD)
    result = click_runner.invoke(nucypher_cli, init_args, input=user_input, catch_exceptions=False)
    assert result.exit_code == 0

    # REST Host
    assert "nucypher alice run" in result.output

    # Auth
    assert 'Enter keyring password:' in result.output, 'WARNING: User was not prompted for password'
    assert 'Repeat for confirmation:' in result.output, 'User was not prompted to confirm password'


def test_alice_control_starts(click_runner, mocker):
    class MockKeyring:
        is_unlocked = False

        @classmethod
        def unlock(cls, password, *args, **kwargs):
            assert password == INSECURE_DEVELOPMENT_PASSWORD
            cls.is_unlocked = True

    good_enough_config = AliceConfiguration(dev_mode=True, federated_only=True, keyring=MockKeyring)

    mocker.patch.object(AliceConfiguration, "from_configuration_file", return_value=good_enough_config)
    init_args = ('alice', 'run', '-x')

    user_input = '{password}\n{password}\n'.format(password=INSECURE_DEVELOPMENT_PASSWORD)
    result = click_runner.invoke(nucypher_cli, init_args, input=user_input)
    assert result.exit_code == 0
    assert MockKeyring.is_unlocked
    assert 'Alice character controller starting' in result.output
