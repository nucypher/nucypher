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
from constant_sorrow.constants import (
    NO_BLOCKCHAIN_CONNECTION,
    NO_PASSWORD,
    NO_CONTROL_PROTOCOL,
    UNKNOWN_DEVELOPMENT_CHAIN_ID
)
from nacl.exceptions import CryptoError
from twisted.logger import Logger

from nucypher.blockchain.eth.agents import NucypherTokenAgent
from nucypher.blockchain.eth.clients import NuCypherGethGoerliProcess
from nucypher.blockchain.eth.decorators import validate_checksum_address
from nucypher.blockchain.eth.interfaces import BlockchainInterfaceFactory
from nucypher.blockchain.eth.registry import BaseContractRegistry, InMemoryContractRegistry, LocalContractRegistry
from nucypher.blockchain.eth.token import NU
from nucypher.blockchain.eth.token import Stake
from nucypher.cli import painting
from nucypher.cli.types import IPV4_ADDRESS
from nucypher.config.constants import DEFAULT_CONFIG_ROOT
from nucypher.config.node import CharacterConfiguration
from nucypher.network.middleware import RestMiddleware
from nucypher.network.teachers import TEACHER_NODES

NO_BLOCKCHAIN_CONNECTION.bool_value(False)


CHARACTER_DESTRUCTION = '''
Delete all {name} character files including:
    - Private and Public Keys ({keystore})
    - Known Nodes             ({nodestore})
    - Node Configuration File ({config})
    - Database                ({database})
    
Are you sure?'''

SUCCESSFUL_DESTRUCTION = "Successfully destroyed NuCypher configuration"


LOG = Logger('cli.actions')


class UnknownIPAddress(RuntimeError):
    pass


def get_password_from_prompt(prompt: str = "Enter password", envvar: str = '', confirm: bool = False) -> str:
    password = os.environ.get(envvar, NO_PASSWORD)
    if password is NO_PASSWORD:  # Collect password, prefer env var
        password = click.prompt(prompt, confirmation_prompt=confirm, hide_input=True)
    return password


@validate_checksum_address
def get_client_password(checksum_address: str, envvar: str = '') -> str:
    prompt = f"Enter password to unlock account {checksum_address}"
    client_password = get_password_from_prompt(prompt=prompt, envvar=envvar, confirm=False)
    return client_password


def get_nucypher_password(confirm: bool = False, envvar="NUCYPHER_KEYRING_PASSWORD") -> str:
    prompt = "Enter NuCypher keyring password"
    keyring_password = get_password_from_prompt(prompt=prompt, confirm=confirm, envvar=envvar)
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
                   teacher_uris: list = None,
                   registry: BaseContractRegistry = None,
                   ) -> List:
    from nucypher.characters.lawful import Ursula

    # Set domains
    if network_domains is None:
        from nucypher.config.node import CharacterConfiguration
        network_domains = {CharacterConfiguration.DEFAULT_DOMAIN, }

    teacher_nodes = list()  # Ursula
    if teacher_uris is None:
        teacher_uris = list()

    for domain in network_domains:
        try:
            # Known NuCypher Domain
            seednode_uris = TEACHER_NODES[domain]
        except KeyError:
            # Unknown NuCypher Domain
            if not teacher_uris:
                emitter.message(f"No default teacher nodes exist for the specified network: {domain}")
        else:
            # Prefer the injected teacher URI, then use the hardcoded seednodes.
            teacher_uris.extend(seednode_uris)

        for uri in teacher_uris:
            teacher_node = Ursula.from_teacher_uri(teacher_uri=uri,
                                                   min_stake=min_stake,
                                                   federated_only=federated_only,
                                                   network_middleware=network_middleware,
                                                   registry=registry)
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
        try:
            database = character_config.db_filepath
        except AttributeError:
            database = "No database found"

        click.confirm(CHARACTER_DESTRUCTION.format(name=character_config._NAME,
                                                   root=character_config.config_root,
                                                   keystore=character_config.keyring_root,
                                                   nodestore=character_config.node_storage.root_dir,
                                                   config=character_config.filepath,
                                                   database=database), abort=True)
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


def confirm_staged_stake(staker_address, value, lock_periods) -> None:
    click.confirm(f"""
* Ursula Node Operator Notice *
-------------------------------

By agreeing to stake {str(value)} ({str(value.to_nunits())} NuNits):

- Staked tokens will be locked for the stake duration.

- You are obligated to maintain a networked and available Ursula-Worker node 
  bonded to the staker address {staker_address} for the duration 
  of the stake(s) ({lock_periods} periods).

- Agree to allow NuCypher network users to carry out uninterrupted re-encryption
  work orders at-will without interference.

Failure to keep your node online, or violation of re-encryption work orders
will result in the loss of staked tokens as described in the NuCypher slashing protocol.

Keeping your Ursula node online during the staking period and successfully
producing correct re-encryption work orders will result in rewards
paid out in ethers retro-actively and on-demand.

Accept ursula node operator obligation?""", abort=True)


def handle_missing_configuration_file(character_config_class, config_file: str = None):
    config_file_location = config_file or character_config_class.default_filepath()
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

    # Handle Keyring

    if not dev:
        character_config.attach_keyring()
        unlock_nucypher_keyring(emitter,
                                character_configuration=character_config,
                                password=get_nucypher_password(confirm=False))

    # Handle Teachers
    teacher_nodes = load_seednodes(emitter,
                                   teacher_uris=[teacher_uri] if teacher_uri else None,
                                   min_stake=min_stake,
                                   federated_only=character_config.federated_only,
                                   network_domains=character_config.domains,
                                   network_middleware=character_config.network_middleware,
                                   registry=character_config.registry)

    #
    # Character Init
    #

    # Produce Character
    try:
        CHARACTER = character_config(known_nodes=teacher_nodes,
                                     network_middleware=character_config.network_middleware,
                                     **config_args)
    except CryptoError as e:
        raise character_config.keyring.AuthenticationFailed(str(e))
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
    stakes = stakeholder.all_stakes
    enumerated_stakes = dict(enumerate(stakes))
    painting.paint_stakes(stakes=stakes, emitter=emitter)
    choice = click.prompt("Select Stake", type=click.IntRange(min=0, max=len(enumerated_stakes)-1))
    chosen_stake = enumerated_stakes[choice]
    return chosen_stake


def select_client_account(emitter,
                          provider_uri: str,
                          prompt: str = None,
                          default: int = 0,
                          registry=None,
                          show_balances: bool = True
                          ) -> str:
    """
    Note: Setting show_balances to True, causes an eager contract and blockchain connection.
    """

    if not provider_uri:
        raise ValueError("Provider URI must be provided to select a wallet account.")

    # Lazy connect the blockchain interface
    if not BlockchainInterfaceFactory.is_interface_initialized(provider_uri=provider_uri):
        BlockchainInterfaceFactory.initialize_interface(provider_uri=provider_uri)
    blockchain = BlockchainInterfaceFactory.get_interface(provider_uri=provider_uri)

    # Lazy connect to contracts
    token_agent = None
    if show_balances:
        if not registry:
            registry = InMemoryContractRegistry.from_latest_publication()
        token_agent = NucypherTokenAgent(registry=registry)

    # Real wallet accounts
    enumerated_accounts = dict(enumerate(blockchain.client.accounts))
    if len(enumerated_accounts) < 1:
        emitter.echo("No ETH accounts were found.", color='red', bold=True)
        raise click.Abort()

    # Display account info
    for index, account in enumerated_accounts.items():
        message = f"{index} | {account} "
        if show_balances:
            message += f" | {NU.from_nunits(token_agent.get_balance(address=account))}"
        emitter.echo(message)

    # Prompt the user for selection, and return
    prompt = prompt or "Select Account"
    account_range = click.IntRange(min=0, max=len(enumerated_accounts)-1)
    choice = click.prompt(prompt, type=account_range, default=default)
    chosen_account = enumerated_accounts[choice]
    return chosen_account


def confirm_deployment(emitter, deployer_interface) -> bool:
    if deployer_interface.client.chain_name == UNKNOWN_DEVELOPMENT_CHAIN_ID or deployer_interface.client.is_local:
        expected_chain_name = 'DEPLOY'
    else:
        expected_chain_name = deployer_interface.client.chain_name

    if click.prompt(f"Type '{expected_chain_name}' to continue") != expected_chain_name:
        emitter.echo("Aborting Deployment", color='red', bold=True)
        raise click.Abort()

    return True


def confirm_enable_restaking_lock(emitter, staking_address: str, release_period: int) -> bool:
    restaking_lock_agreement = f"""
By enabling the re-staking lock for {staking_address}, you are committing to automatically 
re-stake all rewards until period a future period.  You will not be able to disable re-staking until {release_period}.
    """
    emitter.message(restaking_lock_agreement)
    click.confirm(f"Confirm enable re-staking lock for staker {staking_address} until {release_period}?", abort=True)
    return True


def confirm_enable_restaking(emitter, staking_address: str) -> bool:
    restaking_lock_agreement = f"By enabling the re-staking for {staking_address}, " \
                               f"All staking rewards will be automatically added to your existing stake."
    emitter.message(restaking_lock_agreement)
    click.confirm(f"Confirm enable automatic re-staking for staker {staking_address}?", abort=True)
    return True


def establish_deployer_registry(emitter,
                                registry_infile: str = None,
                                registry_outfile:str = None,
                                use_existing_registry: bool = False,
                                dev: bool = False
                                ) -> LocalContractRegistry:

    # Establish a contract registry from disk if specified
    filepath = registry_infile
    default_registry_filepath = os.path.join(DEFAULT_CONFIG_ROOT, BaseContractRegistry.REGISTRY_NAME)
    if registry_outfile:
        registry_infile = registry_infile or default_registry_filepath
        if use_existing_registry:
            try:
                _result = shutil.copyfile(registry_infile, registry_outfile)
            except shutil.SameFileError:
                raise click.BadArgumentUsage(f"--registry-infile and --registry-outfile must not be the same path '{registry_infile}'.")
        filepath = registry_outfile
    if dev:
        # TODO: Need a way to detect a geth --dev registry filepath here. (then deprecate the --dev flag)
        filepath = os.path.join(DEFAULT_CONFIG_ROOT, BaseContractRegistry.DEVELOPMENT_REGISTRY_NAME)
    registry_filepath = filepath or default_registry_filepath

    # All Done.
    registry = LocalContractRegistry(filepath=registry_filepath)
    emitter.message(f"Configured to registry filepath {registry_filepath}")

    return registry
