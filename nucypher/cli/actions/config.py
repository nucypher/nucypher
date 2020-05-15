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
import os
import re
from eth_utils.address import is_checksum_address
from json.decoder import JSONDecodeError

from nucypher.blockchain.eth.clients import NuCypherGethGoerliProcess
from nucypher.characters.control.emitters import StdoutEmitter
from nucypher.cli.literature import (
    CHARACTER_DESTRUCTION,
    CONFIRM_FORGET_NODES,
    INVALID_CONFIGURATION_FILE_WARNING,
    INVALID_JSON_IN_CONFIGURATION_WARNING,
    SUCCESSFUL_DESTRUCTION,
    SUCCESSFUL_FORGET_NODES,
    SUCCESSFUL_UPDATE_CONFIGURATION_VALUES
)
from nucypher.config.characters import UrsulaConfiguration
from nucypher.config.node import CharacterConfiguration


def get_or_update_configuration(emitter: StdoutEmitter,
                                config_class,
                                filepath: str,
                                config_options) -> None:

    try:
        config = config_class.from_configuration_file(filepath=filepath)
    except config_class.ConfigurationError:
        # Issue warning for invalid configuration...
        emitter.message(INVALID_CONFIGURATION_FILE_WARNING.format(filepath=filepath))
        try:
            # ... but try to display it anyways
            response = config_class._read_configuration_file(filepath=filepath)
            return emitter.echo(json.dumps(response, indent=4))
        except JSONDecodeError:
            # ... sorry
            return emitter.message(INVALID_JSON_IN_CONFIGURATION_WARNING.format(filepath=filepath))
    else:
        updates = config_options.get_updates()
        if updates:
            emitter.message(SUCCESSFUL_UPDATE_CONFIGURATION_VALUES.format(fields=', '.join(updates)), color='yellow')
            config.update(**updates)
        return emitter.echo(config.serialize())


def destroy_configuration(emitter, character_config, force: bool = False) -> None:
    if not force:
        try:
            database = character_config.db_filepath
        except AttributeError:
            database = "No database found"  # FIXME: This cannot be right.....

        click.confirm(CHARACTER_DESTRUCTION.format(name=character_config.NAME,
                                                   root=character_config.config_root,
                                                   keystore=character_config.keyring_root,
                                                   nodestore=character_config.node_storage.root_dir,
                                                   config=character_config.filepath,
                                                   database=database), abort=True)
    character_config.destroy()
    emitter.message(SUCCESSFUL_DESTRUCTION, color='green')
    character_config.log.debug(SUCCESSFUL_DESTRUCTION)


def forget(emitter, configuration):
    """Forget all known nodes via storage"""
    click.confirm(CONFIRM_FORGET_NODES, abort=True)
    configuration.forget_nodes()
    emitter.message(SUCCESSFUL_FORGET_NODES, color='red')


def handle_missing_configuration_file(character_config_class,
                                      init_command_hint: str = None,
                                      config_file: str = None
                                      ) -> None:

    config_file_location = config_file or character_config_class.default_filepath()
    init_command = init_command_hint or f"{character_config_class.NAME} init"
    message = f'No {character_config_class.NAME.capitalize()} configuration file found.\n' \
              f'To create a new persistent {character_config_class.NAME.capitalize()} run: ' \
              f'\'nucypher {init_command}\''

    raise click.FileError(filename=config_file_location, hint=message)


def get_provider_process(start_now: bool = False) -> NuCypherGethGoerliProcess:
    """Stage integrated ethereum node process"""
    # TODO: Support domains and non-geth clients
    process = NuCypherGethGoerliProcess()
    if start_now:
        process.start()
    return process


def extract_checksum_address_from_filepath(filepath: str, config_class: CharacterConfiguration) -> str:

    pattern = re.compile(r'''
                         (^\w+)-
                         (0x{1}         # Then, 0x the start of the string, exactly once
                         [0-9a-fA-F]{40}) # Followed by exactly 40 hex chars
                         ''',
                         re.VERBOSE)

    filename = os.path.basename(filepath)
    match = pattern.match(filename)

    if match:
        character_name, checksum_address = match.groups()

    else:
        # Extract from default by "peeking" inside the configuration file.
        default_name = config_class.generate_filename()
        if filename == default_name:
            checksum_address = config_class.peek(filepath=filepath, field='checksum_address')

            ###########
            # TODO: Cleanup and deprecate worker_address in config files, leaving only checksum_address
            if config_class == UrsulaConfiguration:
                federated = bool(config_class.peek(filepath=filepath, field='federated_only'))
                if not federated:
                    checksum_address = config_class.peek(filepath=filepath, field='worker_address')
            ###########

        else:
            raise ValueError(f"Cannot extract checksum from filepath '{filepath}'")

    if not is_checksum_address(checksum_address):
        raise RuntimeError(f"Invalid checksum address detected in configuration file at '{filepath}'.")
    return checksum_address
