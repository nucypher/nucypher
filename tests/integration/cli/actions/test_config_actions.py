from pathlib import Path

import click
import pytest

from nucypher.cli.actions import configure
from nucypher.cli.actions.configure import (
    destroy_configuration,
    forget,
    get_or_update_configuration,
    handle_invalid_configuration_file,
    handle_missing_configuration_file,
)
from nucypher.cli.literature import (
    CONFIRM_FORGET_NODES,
    INVALID_CONFIGURATION_FILE_WARNING,
    INVALID_JSON_IN_CONFIGURATION_WARNING,
    MISSING_CONFIGURATION_FILE,
    SUCCESSFUL_DESTRUCTION,
    SUCCESSFUL_FORGET_NODES,
    SUCCESSFUL_UPDATE_CONFIGURATION_VALUES,
)
from nucypher.config.base import CharacterConfiguration
from nucypher.config.constants import TEMPORARY_DOMAIN_NAME
from tests.constants import YES

BAD_CONFIG_FILE_CONTENTS = (
    {'some': 'garbage'},
    'some garbage',
    2,
    '',
)


# For parameterized fixture
CONFIGS = [
    "alice_test_config",
    "bob_test_config",
    "ursula_test_config",
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


def test_forget_cli_action(alice_test_config, test_emitter, mock_stdin, mocker, capsys):
    mock_forget = mocker.patch.object(CharacterConfiguration, 'forget_nodes')
    mock_stdin.line(YES)
    forget(emitter=test_emitter, configuration=alice_test_config)
    mock_forget.assert_called_once()
    assert mock_stdin.empty()
    captured = capsys.readouterr()
    assert CONFIRM_FORGET_NODES in captured.out
    assert SUCCESSFUL_FORGET_NODES in captured.out


def test_update_configuration_cli_action(config, test_emitter, capsys):
    config_class, config_file = config.__class__, config.filepath
    updates = dict(domain=TEMPORARY_DOMAIN_NAME)
    get_or_update_configuration(emitter=test_emitter, config_class=config_class, filepath=config_file, updates=updates)
    config.update.assert_called_once_with(**updates)
    configure.handle_invalid_configuration_file.assert_not_called()
    configure.handle_missing_configuration_file.assert_not_called()
    captured = capsys.readouterr()
    assert SUCCESSFUL_UPDATE_CONFIGURATION_VALUES.format(fields='domain') in captured.out


def test_handle_update_missing_configuration_file_cli_action(config,
                                                             test_emitter,
                                                             mocker):
    config_class, config_file = config.__class__, config.filepath
    mocker.patch.object(config_class, '_read_configuration_file', side_effect=FileNotFoundError)
    updates = dict(domain=TEMPORARY_DOMAIN_NAME)
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
                                                             mocker,
                                                             capsys):
    config_class = config.__class__
    config_file = config.filepath
    mocker.patch.object(config_class, '_read_configuration_file', side_effect=config_class.ConfigurationError)
    updates = dict(domain=TEMPORARY_DOMAIN_NAME)
    with pytest.raises(config_class.ConfigurationError):
        get_or_update_configuration(emitter=test_emitter,
                                    config_class=config_class,
                                    filepath=config_file,
                                    updates=updates)
    configure.handle_missing_configuration_file.assert_not_called()
    config._write_configuration_file.assert_not_called()
    configure.handle_invalid_configuration_file.assert_called()
    captured = capsys.readouterr()
    assert INVALID_CONFIGURATION_FILE_WARNING.format(filepath=config_file) in captured.out


def test_destroy_configuration_cli_action(config, test_emitter, capsys, mocker, mock_stdin):
    config_class = config.__class__
    mock_config_destroy = mocker.patch.object(config_class, 'destroy')
    mock_stdin.line(YES)
    destroy_configuration(emitter=test_emitter, character_config=config)
    mock_config_destroy.assert_called_once()
    captured = capsys.readouterr()
    assert SUCCESSFUL_DESTRUCTION in captured.out
    assert mock_stdin.empty()


def test_handle_missing_configuration_file_cli_action(config):
    config_class = config.__class__
    config_file = Path(config.filepath)
    init_command = f"{config_class.NAME} init"
    name = config_class.NAME.capitalize()
    message = MISSING_CONFIGURATION_FILE.format(name=name, init_command=init_command)
    assert not config_file.exists()
    with pytest.raises(click.exceptions.FileError, match=message):
        handle_missing_configuration_file(config_file=config_file,
                                          character_config_class=config_class)


@pytest.mark.parametrize('bad_config_payload', BAD_CONFIG_FILE_CONTENTS)
def test_handle_invalid_configuration_file_cli_action(mocker, config, test_emitter, capsys, bad_config_payload):
    config_class = config.__class__
    config_file = Path(config.filepath)
    mocker.patch.object(config_class, '_read_configuration_file', return_value=bad_config_payload)
    with pytest.raises(config_class.ConfigurationError):
        handle_invalid_configuration_file(emitter=test_emitter,
                                          config_class=config_class,
                                          filepath=config_file)
    captured = capsys.readouterr()
    message_1 = INVALID_CONFIGURATION_FILE_WARNING.format(filepath=config_file)
    assert message_1 in captured.out


@pytest.mark.parametrize('side_effect', (TypeError,))
def test_handle_corrupted_configuration_file_cli_action(mocker, config, test_emitter, capsys, side_effect):
    config_class = config.__class__
    config_file = Path(config.filepath)
    mocker.patch('__main__.open', return_value=b'AAAAAAAAAAAAA')
    mocker.patch.object(config_class, '_read_configuration_file', side_effect=side_effect)
    with pytest.raises(side_effect):
        handle_invalid_configuration_file(emitter=test_emitter,
                                          config_class=config_class,
                                          filepath=config_file)
    captured = capsys.readouterr()
    message_1 = INVALID_CONFIGURATION_FILE_WARNING.format(filepath=config_file)
    message_2 = INVALID_JSON_IN_CONFIGURATION_WARNING.format(filepath=config_file)
    assert message_1 in captured.out
    assert message_2 in captured.out
