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
import glob
import json
import os
import re
import shutil
from json import JSONDecodeError
from typing import List, Tuple, Dict, Set, Optional

import click
import requests
from constant_sorrow.constants import (
    NO_BLOCKCHAIN_CONNECTION,
    NO_PASSWORD,
    NO_CONTROL_PROTOCOL,
    UNKNOWN_DEVELOPMENT_CHAIN_ID
)
from eth_utils import is_checksum_address
from nacl.exceptions import CryptoError
from tabulate import tabulate
from twisted.logger import Logger
from web3 import Web3

from nucypher.blockchain.eth.actors import Staker
from nucypher.blockchain.eth.agents import NucypherTokenAgent
from nucypher.blockchain.eth.clients import NuCypherGethGoerliProcess
from nucypher.blockchain.eth.decorators import validate_checksum_address
from nucypher.blockchain.eth.interfaces import BlockchainInterfaceFactory
from nucypher.blockchain.eth.networks import NetworksInventory
from nucypher.blockchain.eth.registry import (
    BaseContractRegistry,
    InMemoryContractRegistry,
    LocalContractRegistry,
    IndividualAllocationRegistry
)
from nucypher.blockchain.eth.token import NU
from nucypher.blockchain.eth.token import Stake
from nucypher.cli import painting
from nucypher.cli.types import IPV4_ADDRESS
from nucypher.config.characters import UrsulaConfiguration
from nucypher.config.constants import DEFAULT_CONFIG_ROOT, NUCYPHER_ENVVAR_KEYRING_PASSWORD, \
    NUCYPHER_ENVVAR_WORKER_ADDRESS
from nucypher.config.node import CharacterConfiguration
from nucypher.network.exceptions import NodeSeemsToBeDown
from nucypher.network.middleware import RestMiddleware
from nucypher.network.nodes import Teacher
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


def get_nucypher_password(confirm: bool = False, envvar=NUCYPHER_ENVVAR_KEYRING_PASSWORD) -> str:
    prompt = f"Enter NuCypher keyring password"
    if confirm:
        from nucypher.config.keyring import NucypherKeyring
        prompt += f" ({NucypherKeyring.MINIMUM_PASSWORD_LENGTH} character minimum)"
    keyring_password = get_password_from_prompt(prompt=prompt, confirm=confirm, envvar=envvar)
    return keyring_password


def unlock_nucypher_keyring(emitter, password: str, character_configuration: CharacterConfiguration):
    emitter.message(f'Decrypting {character_configuration._NAME} keyring...', color='yellow')
    if character_configuration.dev_mode:
        return True  # Dev accounts are always unlocked

    # NuCypher
    try:
        character_configuration.attach_keyring()
        character_configuration.keyring.unlock(password=password)  # Takes ~3 seconds, ~1GB Ram
    except CryptoError:
        raise character_configuration.keyring.AuthenticationFailed


def load_static_nodes(domains: Set[str], filepath: Optional[str] = None) -> Dict[str, 'Ursula']:
    """
    Non-invasively read teacher-uris from a JSON configuration file keyed by domain name.
    and return a filtered subset of domains and teacher URIs as a dict.
    """

    if not filepath:
        filepath = os.path.join(DEFAULT_CONFIG_ROOT, 'static-nodes.json')
    try:
        with open(filepath, 'r') as file:
            static_nodes = json.load(file)
    except FileNotFoundError:
        return dict()   # No static nodes file, No static nodes.
    except JSONDecodeError:
        raise RuntimeError(f"Static nodes file '{filepath}' contains invalid JSON.")
    filtered_static_nodes = {domain: uris for domain, uris in static_nodes.items() if domain in domains}
    return filtered_static_nodes


def aggregate_seednode_uris(domains: set, highest_priority: Optional[List[str]] = None) -> List[str]:

    # Read from the disk
    static_nodes = load_static_nodes(domains=domains)

    # Priority 1 - URI passed via --teacher
    uris = highest_priority or list()
    for domain in domains:

        # 2 - Static nodes from JSON file
        domain_static_nodes = static_nodes.get(domain)
        if domain_static_nodes:
            uris.extend(domain_static_nodes)

        # 3 - Hardcoded teachers from module
        hardcoded_uris = TEACHER_NODES.get(domain)
        if hardcoded_uris:
            uris.extend(hardcoded_uris)

    return uris


def load_seednodes(emitter,
                   min_stake: int,
                   federated_only: bool,
                   network_domains: set,
                   network_middleware: RestMiddleware = None,
                   teacher_uris: list = None,
                   registry: BaseContractRegistry = None,
                   ) -> List:

    """
    Aggregates seednodes URI sources into a list or teacher URIs ordered
    by connection priority in the following order:

    1. --teacher CLI flag
    2. static-nodes.json
    3. Hardcoded teachers
    """

    # Heads up
    emitter.message("Connecting to preferred teacher nodes...", color='yellow')
    from nucypher.characters.lawful import Ursula

    # Aggregate URIs (Ordered by Priority)
    teacher_nodes = list()  # type: List[Ursula]
    teacher_uris = aggregate_seednode_uris(domains=network_domains, highest_priority=teacher_uris)
    if not teacher_uris:
        emitter.message(f"No teacher nodes available for domains: {','.join(network_domains)}")
        return teacher_nodes

    # Construct Ursulas
    for uri in teacher_uris:
        try:
            teacher_node = Ursula.from_teacher_uri(teacher_uri=uri,
                                                   min_stake=min_stake,
                                                   federated_only=federated_only,
                                                   network_middleware=network_middleware,
                                                   registry=registry)
        except NodeSeemsToBeDown:
            LOG.info(f"Failed to connect to teacher: {uri}")
            continue
        except Teacher.NotStaking:
            LOG.info(f"Teacher: {uri} is not actively staking, skipping")
            continue
        teacher_nodes.append(teacher_node)

    if not teacher_nodes:
        emitter.message(f"WARNING - No Peers Available for domains: {','.join(network_domains)}")
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
    message = "Removed all stored known nodes metadata and certificates"
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


def handle_missing_configuration_file(character_config_class, init_command_hint: str = None, config_file: str = None):
    config_file_location = config_file or character_config_class.default_filepath()
    init_command = init_command_hint or f"{character_config_class._NAME} init"
    message = f'No {character_config_class._NAME.capitalize()} configuration file found.\n' \
              f'To create a new persistent {character_config_class._NAME.capitalize()} run: ' \
              f'\'nucypher {init_command}\''

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
                       emitter,
                       unlock_keyring: bool = True,
                       teacher_uri: str = None,
                       min_stake: int = 0,
                       load_preferred_teachers: bool = True,
                       **config_args):

    #
    # Pre-Init
    #

    # Handle Keyring

    if unlock_keyring:
        unlock_nucypher_keyring(emitter,
                                character_configuration=character_config,
                                password=get_nucypher_password(confirm=False))

    # Handle Teachers
    teacher_nodes = list()
    if load_preferred_teachers:
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
    except (CryptoError, ValueError):
        raise character_config.keyring.AuthenticationFailed(f"Failed to unlock nucypher keyring. "
                                                            "Are you sure you provided the correct password?")

    #
    # Post-Init
    #

    if CHARACTER.controller is not NO_CONTROL_PROTOCOL:
        CHARACTER.controller.emitter = emitter  # TODO: set it on object creation? Or not set at all?

    # Federated
    if character_config.federated_only:
        emitter.message("WARNING: Running in Federated mode", color='yellow')

    return CHARACTER


def select_stake(stakeholder, emitter, divisible: bool = False, staker_address: str = None) -> Stake:
    if staker_address:
        staker = stakeholder.get_staker(checksum_address=staker_address)
        stakes = staker.stakes
    else:
        stakes = stakeholder.all_stakes
    if not stakes:
        emitter.echo(f"No stakes found.", color='red')
        raise click.Abort

    stakes = sorted((stake for stake in stakes if stake.is_active), key=lambda s: s.address_index_ordering_key)
    if divisible:
        emitter.echo("NOTE: Showing divisible stakes only", color='yellow')
        stakes = list(filter(lambda s: bool(s.value >= stakeholder.economics.minimum_allowed_locked*2), stakes))  # TODO: Move to method on Stake
        if not stakes:
            emitter.echo(f"No divisible stakes found.", color='red')
            raise click.Abort
    enumerated_stakes = dict(enumerate(stakes))
    painting.paint_stakes(stakeholder=stakeholder, emitter=emitter, staker_address=staker_address)
    choice = click.prompt("Select Stake", type=click.IntRange(min=0, max=len(enumerated_stakes)-1))
    chosen_stake = enumerated_stakes[choice]
    return chosen_stake


def select_client_account(emitter,
                          provider_uri: str = None,
                          wallet = None,
                          prompt: str = None,
                          default: int = 0,
                          registry=None,
                          show_balances: bool = True,
                          show_staking: bool = False,
                          network: str = None,
                          poa: bool = False
                          ) -> str:
    """
    Note: Setting show_balances to True, causes an eager contract and blockchain connection.
    """
    # TODO: Break show_balances into show_eth_balance and show_token_balance

    if not (provider_uri or wallet):
        raise ValueError("Provider URI or wallet must be provided to select an account.")

    if not provider_uri:
        provider_uri = wallet.blockchain.provider_uri

    # Lazy connect the blockchain interface
    if not BlockchainInterfaceFactory.is_interface_initialized(provider_uri=provider_uri):
        BlockchainInterfaceFactory.initialize_interface(provider_uri=provider_uri, poa=poa, emitter=emitter)
    blockchain = BlockchainInterfaceFactory.get_interface(provider_uri=provider_uri)

    # Lazy connect to contracts
    token_agent = None
    if show_balances or show_staking:
        if not registry:
            registry = InMemoryContractRegistry.from_latest_publication(network=network)
        token_agent = NucypherTokenAgent(registry=registry)

    if wallet:
        wallet_accounts = wallet.accounts
    else:
        wallet_accounts = blockchain.client.accounts
    enumerated_accounts = dict(enumerate(wallet_accounts))
    if len(enumerated_accounts) < 1:
        emitter.echo("No ETH accounts were found.", color='red', bold=True)
        raise click.Abort()

    # Display account info
    headers = ['Account']
    if show_staking:
        headers.append('Staking')
    if show_balances:
        headers.extend(('', ''))

    rows = list()
    for index, account in enumerated_accounts.items():
        row = [account]
        if show_staking:
            staker = Staker(is_me=True, checksum_address=account, registry=registry)
            staker.stakes.refresh()
            is_staking = 'Yes' if bool(staker.stakes) else 'No'
            row.append(is_staking)
        if show_balances:
            token_balance = NU.from_nunits(token_agent.get_balance(address=account))
            ether_balance = Web3.fromWei(blockchain.client.get_balance(account=account), 'ether')
            row.extend((token_balance, f'{ether_balance} ETH'))
        rows.append(row)
    emitter.echo(tabulate(rows, headers=headers, showindex='always'))

    # Prompt the user for selection, and return
    prompt = prompt or "Select index of account"
    account_range = click.IntRange(min=0, max=len(enumerated_accounts)-1)
    choice = click.prompt(prompt, type=account_range, default=default)
    chosen_account = enumerated_accounts[choice]

    emitter.echo(f"Selected {choice}: {chosen_account}", color='blue')
    return chosen_account


def handle_client_account_for_staking(emitter,
                                      stakeholder,
                                      staking_address: str,
                                      individual_allocation: IndividualAllocationRegistry,
                                      force: bool,
                                      ) -> Tuple[str, str]:
    """
    Manages client account selection for stake-related operations.
    It always returns a tuple of addresses: the first is the local client account and the second is the staking address.

    When this is not a preallocation staker (which is the normal use case), both addresses are the same.
    Otherwise, when the staker is a contract managed by a beneficiary account,
    then the local client account is the beneficiary, and the staking address is the address of the staking contract.
    """

    if individual_allocation:
        client_account = individual_allocation.beneficiary_address
        staking_address = individual_allocation.contract_address

        message = f"Beneficiary {client_account} will use preallocation contract {staking_address} to stake."
        emitter.echo(message, color='yellow', verbosity=1)
        if not force:
            click.confirm("Is this correct?", abort=True)
    else:
        if staking_address:
            client_account = staking_address
        else:
            client_account = select_client_account(prompt="Select index of staking account",
                                                   emitter=emitter,
                                                   registry=stakeholder.registry,
                                                   network=stakeholder.network,
                                                   wallet=stakeholder.wallet)
            staking_address = client_account

    return client_account, staking_address


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
re-stake all rewards until a future period.  You will not be able to disable re-staking until {release_period}.
    """
    emitter.message(restaking_lock_agreement)
    click.confirm(f"Confirm enable re-staking lock for staker {staking_address} until {release_period}?", abort=True)
    return True


def confirm_enable_restaking(emitter, staking_address: str) -> bool:
    restaking_agreement = f"By enabling the re-staking for {staking_address}, " \
                          f"all staking rewards will be automatically added to your existing stake."
    emitter.message(restaking_agreement)
    click.confirm(f"Confirm enable automatic re-staking for staker {staking_address}?", abort=True)
    return True


def confirm_enable_winding_down(emitter, staking_address: str) -> bool:
    winding_down_agreement = f"""
Over time, as the locked stake duration decreases
i.e. `winds down`, you will receive decreasing inflationary rewards.

Instead, by disabling `wind down` (default) the locked stake duration
can remain constant until you specify that `wind down` should begin. By
keeping the locked stake duration constant, it ensures that you will
receive maximum inflation compensation.

If `wind down` was previously disabled, you can enable it at any point
and the locked duration will decrease after each period.

For more information see https://docs.nucypher.com/en/latest/architecture/sub_stakes.html#winding-down.
"""
    emitter.message(winding_down_agreement)
    click.confirm(f"Confirm enable automatic winding down for staker {staking_address}?", abort=True)
    return True


def establish_deployer_registry(emitter,
                                registry_infile: str = None,
                                registry_outfile: str = None,
                                use_existing_registry: bool = False,
                                download_registry: bool = False,
                                dev: bool = False
                                ) -> BaseContractRegistry:

    if download_registry:
        registry = InMemoryContractRegistry.from_latest_publication()
        emitter.message(f"Using latest published registry from {registry.source}")
        return registry

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


def get_or_update_configuration(emitter, config_class, filepath: str, config_options):

    try:
        config = config_class.from_configuration_file(filepath=filepath)
    except config_class.ConfigurationError:
        # Issue warning for invalid configuration...
        emitter.message(f"Invalid Configuration at {filepath}.")
        try:
            # ... but try to display it anyways
            response = config_class._read_configuration_file(filepath=filepath)
            return emitter.echo(json.dumps(response, indent=4))
        except JSONDecodeError:
            # ... sorry
            return emitter.message(f"Invalid JSON in Configuration File at {filepath}.")
    else:
        updates = config_options.get_updates()
        if updates:
            emitter.message(f"Updated configuration values: {', '.join(updates)}", color='yellow')
            config.update(**updates)
        return emitter.echo(config.serialize())


def extract_checksum_address_from_filepath(filepath, config_class=UrsulaConfiguration):

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


def select_config_file(emitter,
                       config_class,
                       config_root: str = None,
                       checksum_address: str = None,
                       ) -> str:

    #
    # Scrape Disk Configurations
    #

    config_root = config_root or DEFAULT_CONFIG_ROOT
    default_config_file = glob.glob(config_class.default_filepath(config_root=config_root))
    glob_pattern = f'{config_root}/{config_class._NAME}-0x*.{config_class._CONFIG_FILE_EXTENSION}'
    secondary_config_files = glob.glob(glob_pattern)
    config_files = [*default_config_file, *secondary_config_files]
    if not config_files:
        emitter.message(f"No {config_class._NAME.capitalize()} configurations found.  "
                        f"run 'nucypher {config_class._NAME} init' then try again.", color='red')
        raise click.Abort()

    checksum_address = checksum_address or os.environ.get(NUCYPHER_ENVVAR_WORKER_ADDRESS, None)  # TODO: Deprecate worker_address in favor of checksum_address
    if checksum_address:

        #
        # Manual
        #

        parsed_addresses = {extract_checksum_address_from_filepath(fp): fp for fp in config_files}
        try:
            config_file = parsed_addresses[checksum_address]
        except KeyError:
            raise ValueError(f"'{checksum_address}' is not a known {config_class._NAME} configuration account.")

    elif len(config_files) > 1:

        #
        # Interactive
        #

        parsed_addresses = tuple([extract_checksum_address_from_filepath(fp)] for fp in config_files)

        # Display account info
        headers = ['Account']
        emitter.echo(tabulate(parsed_addresses, headers=headers, showindex='always'))

        # Prompt the user for selection, and return
        prompt = f"Select {config_class._NAME} configuration"
        account_range = click.IntRange(min=0, max=len(config_files) - 1)
        choice = click.prompt(prompt, type=account_range, default=0)
        config_file = config_files[choice]
        emitter.echo(f"Selected {choice}: {config_file}", color='blue')

    else:
        # Default: Only one config file, use it.
        config_file = config_files[0]

    return config_file


def issue_stake_suggestions(value: NU = None, lock_periods: int = None):
    if value and (value > NU.from_tokens(150000)):
        click.confirm(f"Wow, {value} - That's a lot of NU - Are you sure this is correct?", abort=True)
    if lock_periods and (lock_periods > 365):
        click.confirm(f"Woah, {lock_periods} is a long time - Are you sure this is correct?", abort=True)


def select_network(emitter) -> str:
    headers = ["Network"]
    rows = [[n] for n in NetworksInventory.NETWORKS]
    emitter.echo(tabulate(rows, headers=headers, showindex='always'))
    choice = click.prompt("Select Network", default=0, type=click.IntRange(0, len(NetworksInventory.NETWORKS)-1))
    network = NetworksInventory.NETWORKS[choice]
    return network
