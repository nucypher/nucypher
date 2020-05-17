import click
import pytest
from pathlib import Path

from nucypher.cli.actions.config import (
    destroy_configuration,
    forget,
    handle_invalid_configuration_file,
    handle_missing_configuration_file,
    update_configuration
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


def test_update_configuration(alice_blockchain_test_config,
                              test_emitter,
                              stdout_trap,
                              mocker,
                              test_registry_source_manager):

    # Setup
    config_class = alice_blockchain_test_config.__class__
    config_file = alice_blockchain_test_config.filepath

    # Test Data
    raw_payload = alice_blockchain_test_config.serialize()
    JSON_payload = alice_blockchain_test_config.deserialize(payload=raw_payload)

    # Isolate from filesystem and Spy on the methods we're testing here
    mocker.patch('__main__.open', return_value=raw_payload)
    mocker.patch.object(config_class, '_read_configuration_file', return_value=JSON_payload)
    ghostwriter = mocker.patch.object(config_class, '_write_configuration_file', return_value=config_file)
    spy_update = mocker.spy(config_class, 'update')

    # Test
    updates = dict(federated_only=True)
    assert not alice_blockchain_test_config.federated_only
    update_configuration(emitter=test_emitter,
                         config_class=config_class,
                         filepath=config_file,
                         updates=updates)

    # The stand-in configuration is untouched...
    assert not alice_blockchain_test_config.federated_only

    # ... but updates were passed aloing to the config file system writing handlers
    ghostwriter.assert_called_once_with(filepath=alice_blockchain_test_config.filepath, override=True)
    assert spy_update.call_args.kwargs == updates


def test_destroy_configuration(alice_blockchain_test_config,
                               test_emitter,
                               stdout_trap,
                               mocker,
                               mock_click_confirm):

    # Setup
    config = alice_blockchain_test_config
    config_class = alice_blockchain_test_config.__class__
    config_file = Path(alice_blockchain_test_config.filepath)

    # Isolate from filesystem and Spy on the methods we're testing here
    spy_keyring_attached = mocker.spy(CharacterConfiguration, 'attach_keyring')
    spy_keyring_destroy = mocker.spy(NucypherKeyring, 'destroy')
    mock_os_remove = mocker.patch('os.remove')

    # Test
    mock_click_confirm.return_value = YES
    destroy_configuration(emitter=test_emitter, character_config=alice_blockchain_test_config)

    output = stdout_trap.getvalue()
    assert SUCCESSFUL_DESTRUCTION in output

    spy_keyring_attached.assert_called_once()
    spy_keyring_destroy.assert_called_once()
    mock_os_remove.assert_called_with(str(config_file))

    if config_class is UrsulaConfiguration:
        mock_os_remove.assert_called_with(filepath=config.db_filepath)


def test_handle_missing_configuration_file(alice_blockchain_test_config):

    # Setup
    config_class = alice_blockchain_test_config.__class__
    config_file = Path(alice_blockchain_test_config.filepath)

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
                                           alice_blockchain_test_config,
                                           test_emitter,
                                           stdout_trap,
                                           bad_config_payload):

    # Setup
    config_class = alice_blockchain_test_config.__class__
    config_file = Path(alice_blockchain_test_config.filepath)

    # Assume the file exists but is full of garbage
    mocker.patch.object(CharacterConfiguration,
                        '_read_configuration_file',
                        return_value=bad_config_payload)

    # Test
    with pytest.raises(config_class.ConfigurationError):
        handle_invalid_configuration_file(emitter=test_emitter,
                                          config_class=config_class,
                                          filepath=config_file)
