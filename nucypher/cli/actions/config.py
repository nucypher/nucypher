"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.

"""


import json

import click
from json.decoder import JSONDecodeError
from typing import Type

from nucypher.characters.control.emitters import StdoutEmitter
from nucypher.cli.literature import (
    CHARACTER_DESTRUCTION,
    CONFIRM_FORGET_NODES,
    INVALID_CONFIGURATION_FILE_WARNING,
    INVALID_JSON_IN_CONFIGURATION_WARNING,
    MISSING_CONFIGURATION_FILE,
    SUCCESSFUL_DESTRUCTION,
    SUCCESSFUL_FORGET_NODES,
    SUCCESSFUL_UPDATE_CONFIGURATION_VALUES
)
from nucypher.config.node import CharacterConfiguration


def forget(emitter: StdoutEmitter, configuration: CharacterConfiguration) -> None:
    """Forget all known nodes via storage"""
    click.confirm(CONFIRM_FORGET_NODES, abort=True)
    configuration.forget_nodes()
    emitter.message(SUCCESSFUL_FORGET_NODES, color='red')


def update_configuration(emitter: StdoutEmitter,
                         config_class: Type[CharacterConfiguration],
                         filepath: str,
                         config_options) -> None:
    """
    Writes updates to an existing configuration file then display the result.
    If the config file is invalid, trey very hard to display the problem.
    """
    try:
        config = config_class.from_configuration_file(filepath=filepath)
    except config_class.ConfigurationError:
        return handle_invalid_configuration_file(emitter=emitter, config_class=config_class, filepath=filepath)
    updates = config_options.get_updates()
    if updates:
        emitter.message(SUCCESSFUL_UPDATE_CONFIGURATION_VALUES.format(fields=', '.join(updates)), color='yellow')
        config.update(**updates)
    emitter.echo(config.serialize())


def destroy_configuration(emitter: StdoutEmitter,
                          character_config: CharacterConfiguration,
                          force: bool = False) -> None:
    """Destroy a character configuration and report rhe result with an emitter."""
    if not force:

        ################################
        # TODO: This is a workaround for ursula - needs follow up
        try:
            database = character_config.db_filepath
        except AttributeError:
            database = "No database found"  # FIXME: This cannot be right.....
        ################################

        click.confirm(CHARACTER_DESTRUCTION.format(name=character_config.NAME,
                                                   root=character_config.config_root,
                                                   keystore=character_config.keyring_root,
                                                   nodestore=character_config.node_storage.root_dir,
                                                   config=character_config.filepath,
                                                   database=database), abort=True)
    character_config.destroy()
    emitter.message(SUCCESSFUL_DESTRUCTION, color='green')
    character_config.log.debug(SUCCESSFUL_DESTRUCTION)


def handle_missing_configuration_file(character_config_class: Type[CharacterConfiguration],
                                      init_command_hint: str = None,
                                      config_file: str = None) -> None:
    """Display a message explaining there is no configuration file to use and abort the current operation."""
    config_file_location = config_file or character_config_class.default_filepath()
    init_command = init_command_hint or f"{character_config_class.NAME} init"
    name = character_config_class.NAME.capitalize()
    message = MISSING_CONFIGURATION_FILE.format(name=name, init_command=init_command)
    raise click.FileError(filename=config_file_location, hint=message)


def handle_invalid_configuration_file(emitter: StdoutEmitter,
                                      config_class: Type[CharacterConfiguration],
                                      filepath: str) -> None:
    """
    Attempt to deserialize a config file that is not a valid nucypher character configuration
    as a means of user-friendly debugging. :-)  I hope this helps!
    """
    # Issue warning for invalid configuration...
    emitter.message(INVALID_CONFIGURATION_FILE_WARNING.format(filepath=filepath))
    try:
        # ... but try to display it anyways
        response = config_class._read_configuration_file(filepath=filepath)
        return emitter.echo(json.dumps(response, indent=4))
    except JSONDecodeError:
        emitter.message(INVALID_JSON_IN_CONFIGURATION_WARNING.format(filepath=filepath))
        try:
            # something is very wrong
            with open(filepath, 'r') as file:
                content = file.read()
                return emitter.echo(content)
        except Exception:
            # ... sorry.. we tried as hard as we could
            raise  # crash :-(