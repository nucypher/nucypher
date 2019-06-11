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


import os
import shutil
from typing import List

import click
import requests
from constant_sorrow.constants import NO_BLOCKCHAIN_CONNECTION
from twisted.logger import Logger

from nucypher.blockchain.eth.clients import NuCypherGethGoerliProcess
from nucypher.characters.control.emitters import IPCStdoutEmitter
from nucypher.characters.lawful import Ursula
from nucypher.cli.config import NucypherClickConfig
from nucypher.cli.types import IPV4_ADDRESS
from nucypher.config.constants import DEFAULT_CONFIG_ROOT, USER_LOG_DIR
from nucypher.network.middleware import RestMiddleware
from nucypher.network.teachers import TEACHER_NODES

NO_BLOCKCHAIN_CONNECTION.bool_value(False)


DESTRUCTION = '''
*Permanently and irreversibly delete all* nucypher files including:
    - Private and Public Keys
    - Known Nodes
    - TLS certificates
    - Node Configurations

Delete {}?'''

CHARACTER_DESTRUCTION = '''
Delete all {name} character files including:
    - Private and Public Keys ({keystore})
    - Known Nodes             ({nodestore})
    - Node Configuration File ({config})

Delete {root}?'''

SUCCESSFUL_DESTRUCTION = "Successfully destroyed NuCypher configuration"


LOG = Logger('cli.actions')

console_emitter = NucypherClickConfig.emit


class UnknownIPAddress(RuntimeError):
    pass


def load_seednodes(min_stake: int,
                   federated_only: bool,
                   network_domains: set,
                   network_middleware: RestMiddleware = None,
                   teacher_uris: list = None
                   ) -> List[Ursula]:

    # Set domains
    if network_domains is None:
        from nucypher.config.node import CharacterConfiguration
        network_domains = {CharacterConfiguration.DEFAULT_DOMAIN, }

    teacher_nodes = list()  # Ursula
    if teacher_uris is None:
        teacher_uris = list()

    for domain in network_domains:
        try:
            teacher_uris = TEACHER_NODES[domain]
        except KeyError:
            # TODO: If this is a unknown domain, require the caller to pass a teacher URI explicitly?
            if not teacher_uris:
                console_emitter(message=f"No default teacher nodes exist for the specified network: {domain}")

        for uri in teacher_uris:
            teacher_node = Ursula.from_teacher_uri(teacher_uri=uri,
                                                   min_stake=min_stake,
                                                   federated_only=federated_only,
                                                   network_middleware=network_middleware)
            teacher_nodes.append(teacher_node)

    if not teacher_nodes:
        console_emitter(message=f'WARNING - No Bootnodes Available')

    return teacher_nodes


def destroy_configuration_root(config_root=None, force=False, logs: bool = False) -> str:
    """CAUTION: This will destroy *all* nucypher configuration files from the configuration root"""

    config_root = config_root or DEFAULT_CONFIG_ROOT

    if not force:
        click.confirm(DESTRUCTION.format(config_root), abort=True)  # ABORT

    if os.path.isdir(config_root):
        shutil.rmtree(config_root, ignore_errors=force)  # config
    else:
        console_emitter(message=f'No NuCypher configuration root directory found at \'{config_root}\'')

    if logs:
        shutil.rmtree(USER_LOG_DIR, ignore_errors=force)  # logs

    return config_root


def get_external_ip_from_centralized_source() -> str:
    ip_request = requests.get('https://ifconfig.me/')
    if ip_request.status_code == 200:
        return ip_request.text
    raise UnknownIPAddress(f"There was an error determining the IP address automatically. "
                           f"(status code {ip_request.status_code})")


def determine_external_ip_address(force: bool = False) -> str:
    """
    Attempts to automatically get the external IP from ifconfig.me
    If the request fails, it falls back to the standard process.
    """
    try:
        rest_host = get_external_ip_from_centralized_source()
    except UnknownIPAddress:
        if force:
            raise
    else:
        # Interactive
        if not force:
            if not click.confirm(f"Is this the public-facing IPv4 address ({rest_host}) you want to use for Ursula?"):
                rest_host = click.prompt("Please enter Ursula's public-facing IPv4 address here:", type=IPV4_ADDRESS)
        else:
            console_emitter(message=f"WARNING: --force is set, using auto-detected IP '{rest_host}'", color='yellow')

        return rest_host


def destroy_configuration(character_config, force: bool = False) -> None:
    if not force:
        click.confirm(CHARACTER_DESTRUCTION.format(name=character_config._NAME,
                                                   root=character_config.config_root,
                                                   keystore=character_config.keyring_root,
                                                   nodestore=character_config.node_storage.root_dir,
                                                   config=character_config.filepath), abort=True)
    character_config.destroy()
    SUCCESSFUL_DESTRUCTION = "Successfully destroyed NuCypher configuration"
    console_emitter(message=SUCCESSFUL_DESTRUCTION, color='green')
    character_config.log.debug(SUCCESSFUL_DESTRUCTION)


def forget(configuration):
    """Forget all known nodes via storage"""
    click.confirm("Permanently delete all known node data?", abort=True)
    configuration.forget_nodes()
    message = "Removed all stored node node metadata and certificates"
    console_emitter(message=message, color='red')
    click.secho(message=message, fg='red')


def confirm_staged_stake(ursula, value, duration):
    click.confirm(f"""
* Ursula Node Operator Notice *
-------------------------------

By agreeing to stake {str(value)}: 

- Staked tokens will be locked, and unavailable for transactions for the stake duration.

- You are obligated to maintain a networked and available Ursula node with the 
  ETH address {ursula.checksum_address} for the duration 
  of the stake(s) ({duration} periods)

- Agree to allow NuCypher network users to carry out uninterrupted re-encryption
  work orders at-will without interference. 

Failure to keep your node online, or violation of re-encryption work orders
will result in the loss of staked tokens as described in the NuCypher slashing protocol.

Keeping your Ursula node online during the staking period and successfully
performing accurate re-encryption work orders will result in rewards 
paid out in ETH retro-actively, on-demand.

Accept node operator obligation?""", abort=True)


def handle_missing_configuration_file(character_config_class, config_file: str = None):
    config_file_location = config_file or character_config_class.DEFAULT_CONFIG_FILE_LOCATION
    message = f'No {character_config_class._NAME.capitalize()} configuration file found.\n' \
              f'To create a new persistent {character_config_class._NAME.capitalize()} run: ' \
              f'\'nucypher {character_config_class._NAME} init\''

    raise click.FileError(filename=config_file_location, hint=message)


def get_provider_process(start_now: bool = False):

    """
    Stage integrated ethereum node process
    # TODO: Support domains and non-geth clients
    """
    process = NuCypherGethGoerliProcess()
    if start_now:
        process.start()
    return process


def make_cli_character(character_config,
                       click_config,
                       dev: bool = False,
                       teacher_uri: str = None,
                       min_stake: int = 0,
                       sync: bool = True,
                       recompile_contracts: bool = False,
                       **config_args):

    #
    # Pre-Init
    #

    # Handle Blockchain
    if not character_config.federated_only:
        click_config.connect_to_blockchain(character_configuration=character_config,
                                           full_sync=sync,
                                           recompile_contracts=recompile_contracts)

    # Handle Keyring
    if not dev:
        character_config.attach_keyring()
        click_config.unlock_keyring(character_configuration=character_config,
                                    password=click_config.get_password(confirm=False))

    # Handle Teachers
    teacher_nodes = None
    if teacher_uri:
        teacher_nodes = load_seednodes(teacher_uris=[teacher_uri] if teacher_uri else None,
                                       min_stake=min_stake,
                                       federated_only=character_config.federated_only,
                                       network_domains=character_config.domains,
                                       network_middleware=click_config.middleware)

    #
    # Character Init
    #

    # Produce Character
    CHARACTER = character_config(known_nodes=teacher_nodes,
                                 network_middleware=click_config.middleware,
                                 **config_args)

    #
    # Post-Init
    #

    # Switch to character control emitter
    if click_config.json_ipc:
        CHARACTER.controller.emitter = IPCStdoutEmitter(quiet=click_config.quiet)

    # Federated
    if character_config.federated_only:
        click_config.emit(message="WARNING: Running in Federated mode", color='yellow')

    return CHARACTER
