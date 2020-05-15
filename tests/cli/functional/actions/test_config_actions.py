from pathlib import Path

import click
import pytest

from nucypher.cli.actions.config import destroy_configuration, forget, handle_invalid_configuration_file, \
    handle_missing_configuration_file, update_configuration
from nucypher.cli.literature import MISSING_CONFIGURATION_FILE
from nucypher.config.node import CharacterConfiguration
from tests.constants import YES


def test_forget(alice_blockchain_test_config,
                test_emitter,
                stdout_trap,
                mock_click_confirm):
    mock_click_confirm.return_value = YES
    forget(emitter=test_emitter, configuration=alice_blockchain_test_config)


def test_update_configuration(alice_blockchain_test_config,
                              test_emitter,
                              stdout_trap):
    config_class = alice_blockchain_test_config.__class__
    config_file = alice_blockchain_test_config.filepath
    update_configuration(emitter=test_emitter,
                         config_class=config_class,
                         filepath=config_file,
                         config_options=dict())


def test_destroy_configuration(alice_blockchain_test_config,
                               test_emitter,
                               stdout_trap):
    destroy_configuration(emitter=test_emitter, character_config=alice_blockchain_test_config)


def test_handle_missing_configuration_file(alice_blockchain_test_config):
    config_class = alice_blockchain_test_config.__class__
    config_file = Path(alice_blockchain_test_config.filepath)

    # The config file does not exist
    assert not config_file.exists()

    init_command = f"{config_class.NAME} init"
    name = config_class.NAME.capitalize()
    message = MISSING_CONFIGURATION_FILE.format(name=name, init_command=init_command)
    with pytest.raises(click.exceptions.FileError, match=message):
        handle_missing_configuration_file(config_file=str(config_file),
                                          character_config_class=config_class)


def test_handle_invalid_configuration_file(mocker,
                                           alice_blockchain_test_config,
                                           test_emitter,
                                           stdout_trap):

    config_class = alice_blockchain_test_config.__class__
    config_file = alice_blockchain_test_config.filepath

    mocker.patch.object(CharacterConfiguration,
                        '_read_configuration_file',
                        return_value={'some': 'garbage'})

    handle_invalid_configuration_file(emitter=test_emitter,
                                      config_class=config_class,
                                      filepath=config_file)
