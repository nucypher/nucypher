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
from typing import List

import click
import requests
from constant_sorrow.constants import NO_BLOCKCHAIN_CONNECTION, NO_PASSWORD, NO_CONTROL_PROTOCOL
from nacl.exceptions import CryptoError
from twisted.logger import Logger

from nucypher.blockchain.eth.clients import NuCypherGethGoerliProcess
from nucypher.blockchain.eth.decorators import validate_checksum_address
from nucypher.blockchain.eth.token import Stake
from nucypher.characters.lawful import Ursula
from nucypher.cli import painting
from nucypher.cli.types import IPV4_ADDRESS
from nucypher.config.node import CharacterConfiguration
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


class UnknownIPAddress(RuntimeError):
    pass


@validate_checksum_address
def get_client_password(checksum_address: str) -> str:
    prompt = f"Enter password to unlock account {checksum_address}"
    client_password = click.prompt(prompt, hide_input=True)
    return client_password


def get_nucypher_password(confirm: bool = False, envvar="NUCYPHER_KEYRING_PASSWORD") -> str:
    keyring_password = os.environ.get(envvar, NO_PASSWORD)
    if keyring_password is NO_PASSWORD:  # Collect password, prefer env var
        prompt = "Enter nucypher keyring password"
        keyring_password = click.prompt(prompt, confirmation_prompt=confirm, hide_input=True)
    return keyring_password


def unlock_nucypher_keyring(emitter, password: str, character_configuration: CharacterConfiguration):
    emitter.message('Decrypting NuCypher keyring...', color='yellow')
    if character_configuration.dev_mode:
        return True  # Dev accounts are always unlocked

    # NuCypher
    try:
        character_configuration.attach_keyring()
        character_configuration.keyring.unlock(password=password)  # Takes ~3 seconds, ~1GB Ram
    except CryptoError:
        raise character_configuration.keyring.AuthenticationFailed


def load_seednodes(emitter,
                   min_stake: int,
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
                emitter.message(f"No default teacher nodes exist for the specified network: {domain}")

        for uri in teacher_uris:
            teacher_node = Ursula.from_teacher_uri(teacher_uri=uri,
                                                   min_stake=min_stake,
                                                   federated_only=federated_only,
                                                   network_middleware=network_middleware)
            teacher_nodes.append(teacher_node)

    if not teacher_nodes:
        emitter.message(f'WARNING - No Bootnodes Available')

    return teacher_nodes


def get_external_ip_from_centralized_source() -> str:
    ip_request = requests.get('https://ifconfig.me/')
    if ip_request.status_code == 200:
        return ip_request.text
    raise UnknownIPAddress(f"There was an error determining the IP address automatically. "
                           f"(status code {ip_request.status_code})")


def determine_external_ip_address(emitter, force: bool = False) -> str:
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
            emitter.message(f"WARNING: --force is set, using auto-detected IP '{rest_host}'", color='yellow')

        return rest_host


def destroy_configuration(emitter, character_config, force: bool = False) -> None:
    if not force:
        click.confirm(CHARACTER_DESTRUCTION.format(name=character_config._NAME,
                                                   root=character_config.config_root,
                                                   keystore=character_config.keyring_root,
                                                   nodestore=character_config.node_storage.root_dir,
                                                   config=character_config.filepath), abort=True)
    character_config.destroy()
    SUCCESSFUL_DESTRUCTION = "Successfully destroyed NuCypher configuration"
    emitter.message(SUCCESSFUL_DESTRUCTION, color='green')
    character_config.log.debug(SUCCESSFUL_DESTRUCTION)


def forget(emitter, configuration):
    """Forget all known nodes via storage"""
    click.confirm("Permanently delete all known node data?", abort=True)
    configuration.forget_nodes()
    message = "Removed all stored node node metadata and certificates"
    emitter.message(message, color='red')


def confirm_staged_stake(staker_address, value, duration) -> None:
    click.confirm(f"""
* Ursula Node Operator Notice *
-------------------------------

By agreeing to stake {str(value)} ({str(value.to_nunits())} NuNits):

- Staked tokens will be locked for the stake duration.

- You are obligated to maintain a networked and available Ursula-Worker node 
  bonded to the staker address {staker_address} for the duration 
  of the stake(s) ({duration} periods).

- Agree to allow NuCypher network users to carry out uninterrupted re-encryption
  work orders at-will without interference.

Failure to keep your node online, or violation of re-encryption work orders
will result in the loss of staked tokens as described in the NuCypher slashing protocol.

Keeping your Ursula node online during the staking period and successfully
producing correct re-encryption work orders will result in rewards
paid out in ethers retro-actively and on-demand.

Accept ursula node operator obligation?""", abort=True)


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
                       **config_args):

    emitter = click_config.emitter

    #
    # Pre-Init
    #

    # Handle Blockchain
    if not character_config.federated_only:
        character_config.get_blockchain_interface()

    # Handle Keyring
    if not dev:
        character_config.attach_keyring()
        unlock_nucypher_keyring(emitter,
                                character_configuration=character_config,
                                password=get_nucypher_password(confirm=False))

    # Handle Teachers
    teacher_nodes = None
    if teacher_uri:
        teacher_nodes = load_seednodes(emitter,
                                       teacher_uris=[teacher_uri] if teacher_uri else None,
                                       min_stake=min_stake,
                                       federated_only=character_config.federated_only,
                                       network_domains=character_config.domains,
                                       network_middleware=character_config.network_middleware)

    #
    # Character Init
    #

    # Produce Character
    CHARACTER = character_config(known_nodes=teacher_nodes,
                                 network_middleware=character_config.network_middleware,
                                 **config_args)

    #
    # Post-Init
    #

    if CHARACTER.controller is not NO_CONTROL_PROTOCOL:
        CHARACTER.controller.emitter = emitter  # TODO: set it on object creation? Or not set at all?

    # Federated
    if character_config.federated_only:
        emitter.message("WARNING: Running in Federated mode", color='yellow')

    return CHARACTER


def select_stake(stakeholder, emitter) -> Stake:
    enumerated_stakes = dict(enumerate(stakeholder.stakes))
    painting.paint_stakes(stakes=stakeholder.stakes, emitter=emitter)
    choice = click.prompt("Select Stake", type=click.IntRange(min=0, max=len(enumerated_stakes)-1))
    chosen_stake = enumerated_stakes[choice]
    return chosen_stake


def select_client_account(emitter, blockchain, prompt: str = None, default=0) -> str:
    enumerated_accounts = dict(enumerate(blockchain.client.accounts))
    for index, account in enumerated_accounts.items():
        emitter.echo(f"{index} | {account}")
    prompt = prompt or "Select Account"
    choice = click.prompt(prompt, type=click.IntRange(min=0, max=len(enumerated_accounts)-1), default=default)
    chosen_account = enumerated_accounts[choice]
    return chosen_account


def confirm_deployment(emitter, deployer) -> bool:
    if deployer.blockchain.client.chain_id == 'UNKNOWN' or deployer.blockchain.client.is_local:
        if click.prompt("Type 'DEPLOY' to continue") != 'DEPLOY':
            emitter.echo("Aborting Deployment", fg='red', bold=True)
            raise click.Abort()
    else:
        confirmed_chain_id = int(click.prompt("Enter the Chain ID to confirm deployment", type=click.INT))
        expected_chain_id = int(deployer.blockchain.client.chain_id)
        if confirmed_chain_id != expected_chain_id:
            abort_message = f"Chain ID not a match ({confirmed_chain_id} != {expected_chain_id}) Aborting Deployment"
            emitter.echo(abort_message, fg='red', bold=True)
            raise click.Abort()
    return True
