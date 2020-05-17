import click
import pytest
from pathlib import Path

from nucypher.cli.actions import config as config_actions
from nucypher.cli.actions.config import (
    destroy_configuration,
    forget,
    handle_invalid_configuration_file,
    handle_missing_configuration_file,
    get_or_update_configuration
)
from nucypher.cli.literature import MISSING_CONFIGURATION_FILE, SUCCESSFUL_DESTRUCTION
from nucypher.config.characters import UrsulaConfiguration
from nucypher.config.keyring import NucypherKeyring
from nucypher.config.node import CharacterConfiguration
from tests.constants import YES


BAD_CONFIG_PAYLOADS = (
    {'some': 'garbage'},
    'some garbage',
    2,
    ''
)


def test_forget(alice_blockchain_test_config,
                test_emitter,
                stdout_trap,
                mock_click_confirm):
    mock_click_confirm.return_value = YES
    forget(emitter=test_emitter, configuration=alice_blockchain_test_config)
    # TODO: Finish me


CONFIGS = [
    'alice_blockchain_test_config',
    'bob_blockchain_test_config',
    'ursula_decentralized_test_config',
]


@pytest.fixture(scope='function', params=CONFIGS)
def config(request, mocker):

    # Setup
    config = request.getfixturevalue(request.param)
    config_class = config.__class__
    config_file = config.filepath

    # Test Data
    raw_payload = config.serialize()
    JSON_payload = config.deserialize(payload=raw_payload)

    # Isolate from filesystem
    mocker.patch('__main__.open', return_value=raw_payload)

    # Mock configuration disk I/O
    mocker.patch.object(config_class, '_read_configuration_file', return_value=JSON_payload)
    mocker.patch.object(config_class, '_write_configuration_file', return_value=config_file)

    # Spy on the code path
    mocker.spy(config_class, 'update')
    mocker.spy(config_actions, 'handle_invalid_configuration_file')
    mocker.spy(config_actions, 'handle_missing_configuration_file')

    return config


def test_update_configuration(config,
                              test_emitter,
                              stdout_trap,
                              test_registry_source_manager):

    # Setup
    config_class = config.__class__
    config_file = config.filepath

    # Test
    updates = dict(federated_only=True)
    assert not config.federated_only
    get_or_update_configuration(emitter=test_emitter,
                                config_class=config_class,
                                filepath=config_file,
                                updates=updates)

    # The stand-in configuration is untouched...
    assert not config.federated_only

    # ... but updates were passed along to the config file system writing handlers
    config._write_configuration_file.assert_called_once_with(filepath=config.filepath, override=True)
    assert config.update.call_args.kwargs == updates

    # Ensure only the affirmative path was followed
    config_actions.handle_invalid_configuration_file.assert_not_called()
    config_actions.handle_missing_configuration_file.assert_not_called()


def test_destroy_configuration(config,
                               test_emitter,
                               stdout_trap,
                               mocker,
                               mock_click_confirm):

    # Setup
    config_class = config.__class__
    config_file = config.filepath

    # Isolate from filesystem and Spy on the methods we're testing here
    spy_keyring_attached = mocker.spy(CharacterConfiguration, 'attach_keyring')
    spy_keyring_destroy = mocker.spy(NucypherKeyring, 'destroy')
    mock_os_remove = mocker.patch('os.remove')

    # Test
    mock_click_confirm.return_value = YES
    destroy_configuration(emitter=test_emitter, character_config=config)

    output = stdout_trap.getvalue()
    assert SUCCESSFUL_DESTRUCTION in output

    spy_keyring_attached.assert_called_once()
    spy_keyring_destroy.assert_called_once()
    mock_os_remove.assert_called_with(str(config_file))

    if config_class is UrsulaConfiguration:
        mock_os_remove.assert_called_with(filepath=config.db_filepath)


def test_handle_missing_configuration_file(config):

    # Setup
    config_class = config.__class__
    config_file = Path(config.filepath)

    # Test Data
    init_command = f"{config_class.NAME} init"
    name = config_class.NAME.capitalize()
    message = MISSING_CONFIGURATION_FILE.format(name=name, init_command=init_command)

    # Context: The config file does not exist
    assert not config_file.exists()

    # Test
    with pytest.raises(click.exceptions.FileError, match=message):
        handle_missing_configuration_file(config_file=str(config_file),
                                          character_config_class=config_class)


@pytest.mark.parametrize('bad_config_payload', BAD_CONFIG_PAYLOADS)
def test_handle_invalid_configuration_file(mocker,
                                           config,
                                           test_emitter,
                                           stdout_trap,
                                           bad_config_payload):

    # Setup
    config_class = config.__class__
    config_file = Path(config.filepath)

    # Assume the file exists but is full of garbage
    mocker.patch.object(CharacterConfiguration,
                        '_read_configuration_file',
                        return_value=bad_config_payload)

    # Test
    with pytest.raises(config_class.ConfigurationError):
        handle_invalid_configuration_file(emitter=test_emitter,
                                          config_class=config_class,
                                          filepath=config_file)
