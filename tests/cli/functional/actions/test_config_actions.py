import click
import pytest
from pathlib import Path

from nucypher.cli.actions import configure
from nucypher.cli.actions.configure import (
    destroy_configuration,
    forget,
    get_or_update_configuration,
    handle_invalid_configuration_file,
    handle_missing_configuration_file
)
from nucypher.cli.literature import (
    INVALID_CONFIGURATION_FILE_WARNING,
    INVALID_JSON_IN_CONFIGURATION_WARNING,
    MISSING_CONFIGURATION_FILE,
    SUCCESSFUL_DESTRUCTION
)
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
    config_class, config_file = config.__class__, config.filepath

    # Test Data
    raw_payload = config.serialize()
    JSON_payload = config.deserialize(payload=raw_payload)

    # Isolate from filesystem
    mocker.patch('__main__.open', return_value=raw_payload)

    # Mock configuration disk I/O
    mocker.patch.object(config_class, '_read_configuration_file', return_value=JSON_payload)
    mocker.patch.object(config_class, '_write_configuration_file', return_value=config_file)

    # Spy on the code path
    mocker.patch.object(config_class, 'update', side_effect=config_class._write_configuration_file)
    mocker.spy(configure, 'handle_invalid_configuration_file')
    mocker.spy(configure, 'handle_missing_configuration_file')

    yield config
    mocker.resetall()  # dont carry over context between functions


def test_forget_cli_action(alice_blockchain_test_config, test_emitter, stdout_trap, mock_click_confirm, mocker):
    mock_forget = mocker.patch.object(CharacterConfiguration, 'forget_nodes')
    mock_click_confirm.return_value = YES
    forget(emitter=test_emitter, configuration=alice_blockchain_test_config)
    mock_forget.assert_called_once()


def test_update_configuration_cli_action(config, test_emitter, stdout_trap, test_registry_source_manager):
    config_class, config_file = config.__class__, config.filepath
    updates = dict(federated_only=True)
    get_or_update_configuration(emitter=test_emitter, config_class=config_class, filepath=config_file, updates=updates)
    config.update.assert_called_once_with(**updates)
    configure.handle_invalid_configuration_file.assert_not_called()
    configure.handle_missing_configuration_file.assert_not_called()


def test_handle_update_missing_configuration_file_cli_action(config,
                                                             test_emitter,
                                                             stdout_trap,
                                                             test_registry_source_manager,
                                                             mocker):
    config_class, config_file = config.__class__, config.filepath
    mocker.patch.object(config_class, '_read_configuration_file', side_effect=FileNotFoundError)
    updates = dict(federated_only=True)
    with pytest.raises(click.FileError):
        get_or_update_configuration(emitter=test_emitter,
                                    config_class=config_class,
                                    filepath=config_file,
                                    updates=updates)
    configure.handle_missing_configuration_file.assert_called()
    config._write_configuration_file.assert_not_called()
    configure.handle_invalid_configuration_file.assert_not_called()


def test_handle_update_invalid_configuration_file_cli_action(config,
                                                             test_emitter,
                                                             stdout_trap,
                                                             test_registry_source_manager,
                                                             mocker):
    config_class = config.__class__
    config_file = config.filepath
    mocker.patch.object(config_class, '_read_configuration_file', side_effect=config_class.ConfigurationError)
    updates = dict(federated_only=True)
    with pytest.raises(config_class.ConfigurationError):
        get_or_update_configuration(emitter=test_emitter,
                                    config_class=config_class,
                                    filepath=config_file,
                                    updates=updates)
    configure.handle_missing_configuration_file.assert_not_called()
    config._write_configuration_file.assert_not_called()
    configure.handle_invalid_configuration_file.assert_called()


def test_destroy_configuration_cli_action(config, test_emitter, stdout_trap, mocker, mock_click_confirm):
    config_class = config.__class__
    mock_config_destroy = mocker.patch.object(config_class, 'destroy')
    mock_click_confirm.return_value = YES
    destroy_configuration(emitter=test_emitter, character_config=config)
    mock_config_destroy.assert_called_once()
    output = stdout_trap.getvalue()
    assert SUCCESSFUL_DESTRUCTION in output


def test_handle_missing_configuration_file_cli_action(config):
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
def test_handle_invalid_configuration_file_cli_action(mocker, config, test_emitter, stdout_trap, bad_config_payload):
    config_class = config.__class__
    config_file = Path(config.filepath)
    mocker.patch.object(config_class, '_read_configuration_file', return_value=bad_config_payload)
    with pytest.raises(config_class.ConfigurationError):
        handle_invalid_configuration_file(emitter=test_emitter,
                                          config_class=config_class,
                                          filepath=config_file)
    output = stdout_trap.getvalue()
    message_1 = INVALID_CONFIGURATION_FILE_WARNING.format(filepath=config_file)
    assert message_1 in output


@pytest.mark.parametrize('side_effect', (TypeError,))
def test_handle_corrupted_configuration_file_cli_action(mocker, config, test_emitter, stdout_trap, side_effect):
    config_class = config.__class__
    config_file = Path(config.filepath)
    mocker.patch('__main__.open', return_value=b'AAAAAAAAAAAAA')
    mocker.patch.object(config_class, '_read_configuration_file', side_effect=side_effect)
    with pytest.raises(side_effect):
        handle_invalid_configuration_file(emitter=test_emitter,
                                          config_class=config_class,
                                          filepath=config_file)
    output = stdout_trap.getvalue()
    message_1 = INVALID_CONFIGURATION_FILE_WARNING.format(filepath=config_file)
    message_2 = INVALID_JSON_IN_CONFIGURATION_WARNING.format(filepath=config_file)
    assert message_1 in output
    assert message_2 in output
