import click
import pytest
from json.decoder import JSONDecodeError
from pathlib import Path

from nucypher.cli.actions import config as config_actions
from nucypher.cli.actions.config import (
    destroy_configuration,
    forget,
    get_or_update_configuration,
    handle_invalid_configuration_file,
    handle_missing_configuration_file
)
from nucypher.cli.literature import MISSING_CONFIGURATION_FILE, SUCCESSFUL_DESTRUCTION
from nucypher.config.node import CharacterConfiguration
from tests.constants import YES

BAD_CONFIG_FILE_CONTENTS = (
    {'some': 'garbage'},
    'some garbage',
    2,
    '',
)


# For parameterized fixture
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


def test_forget(alice_blockchain_test_config, test_emitter, stdout_trap, mock_click_confirm, mocker):
    """Tes"""
    mock_forget = mocker.patch.object(CharacterConfiguration, 'forget_nodes')
    mock_click_confirm.return_value = YES
    forget(emitter=test_emitter, configuration=alice_blockchain_test_config)
    mock_forget.assert_called_once()


def test_update_configuration(config, test_emitter, stdout_trap, test_registry_source_manager):
    config_class = config.__class__
    config_file = config.filepath
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


def test_destroy_configuration_action(config, test_emitter, stdout_trap, mocker, mock_click_confirm):
    config_class = config.__class__
    mock_config_destroy = mocker.patch.object(config_class, 'destroy')
    mock_click_confirm.return_value = YES
    destroy_configuration(emitter=test_emitter, character_config=config)
    mock_config_destroy.assert_called_once()
    output = stdout_trap.getvalue()
    assert SUCCESSFUL_DESTRUCTION in output


def test_handle_missing_configuration_file(config):
    config_class = config.__class__
    config_file = Path(config.filepath)
    init_command = f"{config_class.NAME} init"
    name = config_class.NAME.capitalize()
    message = MISSING_CONFIGURATION_FILE.format(name=name, init_command=init_command)
    assert not config_file.exists()
    with pytest.raises(click.exceptions.FileError, match=message):
        handle_missing_configuration_file(config_file=str(config_file),
                                          character_config_class=config_class)


@pytest.mark.parametrize('bad_config_payload', BAD_CONFIG_FILE_CONTENTS)
def test_handle_invalid_configuration_file_action(mocker, config, test_emitter, stdout_trap, bad_config_payload):
    config_class = config.__class__
    config_file = Path(config.filepath)
    mocker.patch.object(CharacterConfiguration, '_read_configuration_file', return_value=bad_config_payload)
    with pytest.raises(config_class.ConfigurationError):
        handle_invalid_configuration_file(emitter=test_emitter,
                                          config_class=config_class,
                                          filepath=config_file)


@pytest.mark.parametrize('side_effect', (TypeError, JSONDecodeError))
def test_handle_corrupted_configuration_file(mocker, config, test_emitter, stdout_trap, side_effect):
    config_class = config.__class__
    config_file = Path(config.filepath)
    mocker.patch.object(CharacterConfiguration, '_read_configuration_file', side_effect=side_effect)
    with pytest.raises(config_class.ConfigurationError):
        handle_invalid_configuration_file(emitter=test_emitter,
                                          config_class=config_class,
                                          filepath=config_file)
