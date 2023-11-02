import os
from distutils.util import strtobool
from pathlib import Path
from typing import Dict, Optional, Tuple

import click
from web3.types import BlockIdentifier

from nucypher.blockchain.eth.agents import EthereumContractAgent
from nucypher.blockchain.eth.domains import TACoDomain
from nucypher.blockchain.eth.events import EventRecord
from nucypher.blockchain.eth.registry import (
    ContractRegistry,
    LocalRegistrySource,
)
from nucypher.characters.base import Character
from nucypher.cli.actions.auth import (
    get_nucypher_password,
    unlock_nucypher_keystore,
    unlock_signer_account,
)
from nucypher.cli.literature import (
    CONFIRM_OVERWRITE_EVENTS_CSV_FILE,
)
from nucypher.utilities.emitters import StdoutEmitter
from nucypher.utilities.events import write_events_to_csv_file


def setup_emitter(general_config, banner: str = None) -> StdoutEmitter:
    emitter = general_config.emitter
    if banner:
        emitter.banner(banner)
    return emitter


def make_cli_character(
    character_config,
    emitter,
    eth_endpoint: str,
    unlock_keystore: bool = True,
    unlock_signer: bool = True,
    teacher_uri: str = None,
    min_stake: int = 0,
    json_ipc: bool = False,
    **config_args,
) -> Character:
    #
    # Pre-Init
    #

    # Handle KEYSTORE
    if unlock_keystore:
        unlock_nucypher_keystore(emitter,
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
            network_middleware=character_config.network_middleware,
            registry=character_config.registry,
            eth_endpoint=eth_endpoint,
        )
        sage_nodes.append(maybe_sage_node)

    CHARACTER = character_config(
        known_nodes=sage_nodes,
        network_middleware=character_config.network_middleware,
        eth_endpoint=eth_endpoint,
        **config_args,
    )

    #
    # Post-Init
    #

    emitter.message(f"Loaded {CHARACTER.__class__.__name__} ({CHARACTER.domain})", color='green')
    return CHARACTER


def get_registry(
    domain: TACoDomain, registry_filepath: Optional[Path] = None
) -> ContractRegistry:
    if registry_filepath:
        source = LocalRegistrySource(filepath=registry_filepath)
        registry = ContractRegistry(source=source)
    else:
        registry = ContractRegistry.from_latest_publication(domain=domain)
    return registry


def get_env_bool(var_name: str, default: bool) -> bool:
    if var_name in os.environ:
        # TODO: which is better: to fail on an incorrect envvar, or to use the default?
        # Currently doing the former.
        return strtobool(os.environ[var_name])
    else:
        return default


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
                    csv_output_file: Optional[Path] = None) -> None:
    if csv_output_file:
        if csv_output_file.exists():
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
        emitter.echo(f"{event_name}:", bold=True, color="yellow")
        entries = event.get_logs(
            fromBlock=from_block, toBlock=to_block, argument_filters=argument_filters
        )
        for event_record in entries:
            emitter.echo(f"  - {EventRecord(event_record)}")
