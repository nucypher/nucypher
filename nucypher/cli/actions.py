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


import click
import os
import requests
import shutil

from twisted.logger import Logger
from typing import List

from nucypher.characters.lawful import Ursula
from nucypher.cli.config import NucypherClickConfig
from nucypher.config.constants import DEFAULT_CONFIG_ROOT, USER_LOG_DIR
from nucypher.network.middleware import RestMiddleware
from nucypher.network.teachers import TEACHER_NODES
from nucypher.utilities.sandbox.constants import TEMPORARY_DOMAIN

DESTRUCTION = '''
*Permanently and irreversibly delete all* nucypher files including:
    - Private and Public Keys
    - Known Nodes
    - TLS certificates
    - Node Configurations

Delete {}?'''

CHARACTER_DESTRUCTION = '''
Delete all {name} character files including:
    - Private and Public Keys
    - Known Nodes
    - Node Configuration File

Delete {root}?'''


LOG = Logger('cli.actions')

console_emitter = NucypherClickConfig.emit


def load_seednodes(min_stake: int,
                   federated_only: bool,
                   network_domain: str,
                   network_middleware: RestMiddleware = None,
                   teacher_uris: list = None
                   ) -> List[Ursula]:

    if network_domain is None:
        from nucypher.config.node import NodeConfiguration
        network_domain = NodeConfiguration.DEFAULT_DOMAIN

    teacher_nodes = list()
    if teacher_uris is None:
        teacher_uris = list()

        # Skip Test Domain
        if network_domain != TEMPORARY_DOMAIN:
            try:
                teacher_uris = TEACHER_NODES[network_domain]
            except KeyError:
                raise KeyError(f"No default teacher nodes exist for the specified network: {network_domain}")

    for uri in teacher_uris:
        teacher_node = Ursula.from_teacher_uri(teacher_uri=uri,
                                               min_stake=min_stake,
                                               federated_only=federated_only,
                                               network_middleware=network_middleware)
        teacher_nodes.append(teacher_node)
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


def get_external_ip():
    ip_request = requests.get('https://ifconfig.me/')
    if ip_request.status_code == 200:
        return ip_request.text
    return None


def destroy_configuration(character_config, force: bool = False) -> None:

        if not force:
            click.confirm(CHARACTER_DESTRUCTION.format(name=character_config._NAME,
                                                       root=character_config.config_root), abort=True)

        try:
            character_config.destroy()

        except FileNotFoundError:
            message = 'Failed: No nucypher files found at {}'.format(character_config.config_root)
            console_emitter(message=message, color='red')
            character_config.log.debug(message)
            raise click.Abort()
        else:
            message = "Deleted configuration files at {}".format(character_config.config_root)
            console_emitter(message=message, color='green')
            character_config.log.debug(message)


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
  ETH address {ursula.checksum_public_address} for the duration 
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
