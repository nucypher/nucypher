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
from distutils.util import strtobool
from pathlib import Path
from typing import Dict, Optional, Tuple

import click
from constant_sorrow.constants import NO_CONTROL_PROTOCOL
from web3.types import BlockIdentifier

from nucypher.blockchain.eth.agents import EthereumContractAgent
from nucypher.blockchain.eth.events import EventRecord
from nucypher.blockchain.eth.interfaces import (
    BlockchainDeployerInterface,
    BlockchainInterface,
    BlockchainInterfaceFactory
)
from nucypher.blockchain.eth.registry import (
    BaseContractRegistry,
    InMemoryContractRegistry,
    LocalContractRegistry
)
from nucypher.characters.base import Character
from nucypher.characters.control.emitters import StdoutEmitter
from nucypher.cli.actions.auth import (
    get_nucypher_password,
    unlock_nucypher_keyring,
    unlock_signer_account
)
from nucypher.cli.literature import (
    CONNECTING_TO_BLOCKCHAIN,
    ETHERSCAN_FLAG_DISABLED_WARNING,
    ETHERSCAN_FLAG_ENABLED_WARNING,
    FEDERATED_WARNING,
    LOCAL_REGISTRY_ADVISORY,
    NO_HARDWARE_WALLET_WARNING,
    PRODUCTION_REGISTRY_ADVISORY,
    CONFIRM_OVERWRITE_EVENTS_CSV_FILE
)
from nucypher.config.constants import DEFAULT_CONFIG_ROOT
from nucypher.utilities.events import write_events_to_csv_file


def setup_emitter(general_config, banner: str = None) -> StdoutEmitter:
    emitter = general_config.emitter
    if banner:
        emitter.banner(banner)
    return emitter


def make_cli_character(character_config,
                       emitter,
                       unlock_keyring: bool = True,
                       unlock_signer: bool = True,
                       teacher_uri: str = None,
                       min_stake: int = 0,
                       json_ipc: bool = False,
                       **config_args
                       ) -> Character:

    #
    # Pre-Init
    #

    # Handle Keyring
    if unlock_keyring:
        unlock_nucypher_keyring(emitter,
                                character_configuration=character_config,
                                password=get_nucypher_password(emitter=emitter, confirm=False))

    # Handle Signer/Wallet
    if unlock_signer:
        unlock_signer_account(config=character_config, json_ipc=json_ipc)

    # Handle Teachers
    # TODO: Is this still relevant?  Is it better to DRY this up by doing it later?
    sage_nodes = list()

    #
    # Character Init
    #

    # Produce Character
    if teacher_uri:
        maybe_sage_node = character_config.known_node_class.from_teacher_uri(
            teacher_uri=teacher_uri,
            min_stake=min_stake,
            federated_only=character_config.federated_only,
            network_middleware=character_config.network_middleware,
            registry=character_config.registry
        )
        sage_nodes.append(maybe_sage_node)

    CHARACTER = character_config(known_nodes=sage_nodes,
                                 network_middleware=character_config.network_middleware,
                                 **config_args)

    #
    # Post-Init
    #

    if CHARACTER.controller is not NO_CONTROL_PROTOCOL:
        CHARACTER.controller.emitter = emitter

    # Federated
    if character_config.federated_only:
        emitter.message(FEDERATED_WARNING, color='yellow')

    emitter.message(f"Loaded {CHARACTER.__class__.__name__} {CHARACTER.checksum_address} ({CHARACTER.domain})", color='green')
    return CHARACTER


def establish_deployer_registry(emitter,
                                network: str = None,
                                registry_infile: str = None,
                                registry_outfile: str = None,
                                use_existing_registry: bool = False,
                                download_registry: bool = False,
                                dev: bool = False
                                ) -> BaseContractRegistry:

    if download_registry:
        registry = InMemoryContractRegistry.from_latest_publication(network=network)
        emitter.message(PRODUCTION_REGISTRY_ADVISORY.format(source=registry.source))
        return registry

    # Establish a contract registry from disk if specified
    filepath = registry_infile
    default_registry_filepath = os.path.join(DEFAULT_CONFIG_ROOT, BaseContractRegistry.REGISTRY_NAME)
    if registry_outfile:
        # mutative usage of existing registry
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
    emitter.message(LOCAL_REGISTRY_ADVISORY.format(registry_filepath=registry_filepath))
    return registry


def get_registry(network: str, registry_filepath: str = None) -> BaseContractRegistry:
    if registry_filepath:
        registry = LocalContractRegistry(filepath=registry_filepath)
    else:
        registry = InMemoryContractRegistry.from_latest_publication(network=network)
    return registry


def connect_to_blockchain(emitter: StdoutEmitter, 
                          provider_uri: str,
                          debug: bool = False,
                          light: bool = False
                          ) -> BlockchainInterface:
    try:
        # Note: Conditional for test compatibility.
        if not BlockchainInterfaceFactory.is_interface_initialized(provider_uri=provider_uri):
            BlockchainInterfaceFactory.initialize_interface(provider_uri=provider_uri,
                                                            light=light,
                                                            emitter=emitter)
        emitter.echo(message=CONNECTING_TO_BLOCKCHAIN)
        blockchain = BlockchainInterfaceFactory.get_interface(provider_uri=provider_uri)
        return blockchain
    except Exception as e:
        if debug:
            raise
        emitter.echo(str(e), bold=True, color='red')
        raise click.Abort


def initialize_deployer_interface(emitter: StdoutEmitter,
                                  poa: bool,
                                  provider_uri,
                                  ignore_solidity_check: bool,
                                  gas_strategy: str = None,
                                  max_gas_price: int = None
                                  ) -> BlockchainDeployerInterface:
    
    if not BlockchainInterfaceFactory.is_interface_initialized(provider_uri=provider_uri):
        deployer_interface = BlockchainDeployerInterface(provider_uri=provider_uri,
                                                         poa=poa,
                                                         gas_strategy=gas_strategy,
                                                         max_gas_price=max_gas_price)
        BlockchainInterfaceFactory.register_interface(interface=deployer_interface, emitter=emitter)
    else:
        deployer_interface = BlockchainInterfaceFactory.get_interface(provider_uri=provider_uri)
    deployer_interface.connect(ignore_solidity_check=ignore_solidity_check)
    return deployer_interface


def get_env_bool(var_name: str, default: bool) -> bool:
    if var_name in os.environ:
        # TODO: which is better: to fail on an incorrect envvar, or to use the default?
        # Currently doing the former.
        return strtobool(os.environ[var_name])
    else:
        return default


def ensure_config_root(config_root: str) -> None:
    """Ensure config root exists, because we need a default place to put output files."""
    config_root = config_root or DEFAULT_CONFIG_ROOT
    if not os.path.exists(config_root):
        os.makedirs(config_root)


def deployer_pre_launch_warnings(emitter: StdoutEmitter, etherscan: bool, hw_wallet: bool) -> None:
    if not hw_wallet:
        emitter.echo(NO_HARDWARE_WALLET_WARNING, color='yellow')
    if etherscan:
        emitter.echo(ETHERSCAN_FLAG_ENABLED_WARNING, color='yellow')
    else:
        emitter.echo(ETHERSCAN_FLAG_DISABLED_WARNING, color='yellow')


def parse_event_filters_into_argument_filters(event_filters: Tuple[str]) -> Dict:
    """
    Converts tuple of entries of the form <filter_name>=<filter_value> into a dict
    of filter_name (key) -> filter_value (value) entries. Filter values can only be strings, but if the filter
    value can be converted to an int, then it is converted, otherwise it remains a string.
    """
    argument_filters = dict()
    for event_filter in event_filters:
        event_filter_split = event_filter.split('=')
        if len(event_filter_split) != 2:
            raise ValueError(f"Invalid filter format: {event_filter}")
        key = event_filter_split[0]
        value = event_filter_split[1]
        # events are only indexed by string or int values
        if value.isnumeric():
            value = int(value)
        argument_filters[key] = value
    return argument_filters


def retrieve_events(emitter: StdoutEmitter,
                    agent: EthereumContractAgent,
                    event_name: str,
                    from_block: BlockIdentifier,
                    to_block: BlockIdentifier,
                    argument_filters: Dict,
                    csv_output_file: Optional[str] = None) -> None:
    if csv_output_file:
        if Path(csv_output_file).exists():
            click.confirm(CONFIRM_OVERWRITE_EVENTS_CSV_FILE.format(csv_file=csv_output_file), abort=True)
        available_events = write_events_to_csv_file(csv_file=csv_output_file,
                                                    agent=agent,
                                                    event_name=event_name,
                                                    from_block=from_block,
                                                    to_block=to_block,
                                                    argument_filters=argument_filters)
        if available_events:
            emitter.echo(f"{agent.contract_name}::{event_name} events written to {csv_output_file}",
                         bold=True,
                         color='green')
        else:
            emitter.echo(f'No {agent.contract_name}::{event_name} events found', color='yellow')
    else:
        event = agent.contract.events[event_name]
        emitter.echo(f"{event_name}:", bold=True, color='yellow')
        entries = event.getLogs(fromBlock=from_block, toBlock=to_block, argument_filters=argument_filters)
        for event_record in entries:
            emitter.echo(f"  - {EventRecord(event_record)}")
