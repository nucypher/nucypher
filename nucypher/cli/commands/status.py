


import os
from pathlib import Path

import click

from nucypher.blockchain.eth.agents import (
    ContractAgency,
    NucypherTokenAgent,
    TACoApplicationAgent,
)
from nucypher.blockchain.eth.constants import AVERAGE_BLOCK_TIME_IN_SECONDS
from nucypher.blockchain.eth.networks import NetworksInventory
from nucypher.cli.config import group_general_config
from nucypher.cli.options import (
    group_options,
    option_contract_name,
    option_eth_provider_uri,
    option_event_name,
    option_light,
    option_network,
    option_poa,
    option_registry_filepath,
    option_staking_provider,
)
from nucypher.cli.painting.status import paint_contract_status
from nucypher.cli.utils import (
    connect_to_blockchain,
    get_registry,
    parse_event_filters_into_argument_filters,
    retrieve_events,
    setup_emitter,
)
from nucypher.config.constants import NUCYPHER_ENVVAR_ETH_PROVIDER_URI
from nucypher.utilities.events import generate_events_csv_filepath

STAKING_ESCROW = 'StakingEscrow'
POLICY_MANAGER = 'PolicyManager'

CONTRACT_NAMES = [
    TACoApplicationAgent.contract_name,
    NucypherTokenAgent.contract_name,
    STAKING_ESCROW,
    POLICY_MANAGER
]

class RegistryOptions:

    __option_name__ = 'registry_options'

    def __init__(self, eth_provider_uri, poa, registry_filepath, light, network):
        self.eth_provider_uri = eth_provider_uri
        self.poa = poa
        self.registry_filepath = registry_filepath
        self.light = light
        self.network = network

    def setup(self, general_config) -> tuple:
        emitter = setup_emitter(general_config)
        registry = get_registry(network=self.network, registry_filepath=self.registry_filepath)
        blockchain = connect_to_blockchain(emitter=emitter, eth_provider_uri=self.eth_provider_uri)
        return emitter, registry, blockchain


group_registry_options = group_options(
    RegistryOptions,
    poa=option_poa,
    light=option_light,
    registry_filepath=option_registry_filepath,
    network=option_network(default=NetworksInventory.DEFAULT, validate=True),  # TODO: See 2214
    eth_provider_uri=option_eth_provider_uri(default=os.environ.get(NUCYPHER_ENVVAR_ETH_PROVIDER_URI)),
)

option_csv = click.option('--csv',
                          help="Write event data to a CSV file using a default filename in the current directory",
                          default=False,
                          is_flag=True)
option_csv_file = click.option('--csv-file',
                               help="Write event data to the CSV file at specified filepath",
                               type=click.Path(dir_okay=False, path_type=Path))
option_event_filters = click.option('--event-filter', '-f', 'event_filters',
                                    help="Event filter of the form <name>=<value>",
                                    multiple=True,
                                    type=click.STRING,
                                    default=[])

option_from_block = click.option(
    "--from-block",
    help="Collect events from this block number; defaults to the block number from ~24 hours ago",
    type=click.INT,
)
option_to_block = click.option(
    "--to-block",
    help="Collect events until this block number; defaults to 'latest' block number",
    type=click.INT,
)


@click.group()
def status():
    """Echo a snapshot of live NuCypher Network metadata."""


@status.command()
@group_registry_options
@group_general_config
def network(general_config, registry_options):
    """Overall information of the NuCypher Network."""
    emitter, registry, blockchain = registry_options.setup(general_config=general_config)
    paint_contract_status(registry, emitter=emitter)


@status.command("taco")
@group_registry_options
@option_staking_provider
@group_general_config
def staking_providers(general_config, registry_options, staking_provider_address):
    """Show relevant information about staking providers."""
    emitter, registry, blockchain = registry_options.setup(
        general_config=general_config
    )
    application_agent = ContractAgency.get_agent(
        TACoApplicationAgent, registry=registry
    )
    staking_providers_list = (
        [staking_provider_address]
        if staking_provider_address
        else application_agent.get_staking_providers()
    )
    emitter.echo(staking_providers_list)  # TODO: staking provider painter
    # paint_stakers(emitter=emitter, stakers=staking_providers_list, registry=registry)


@status.command()
@group_registry_options
@group_general_config
@option_contract_name(required=False, valid_options=CONTRACT_NAMES)
@option_event_name
@option_from_block
@option_to_block
@option_csv
@option_csv_file
@option_event_filters
def events(
    general_config,
    registry_options,
    contract_name,
    from_block,
    to_block,
    event_name,
    csv,
    csv_file,
    event_filters,
):
    """Show events associated with NuCypher contracts."""

    if csv or csv_file:
        if csv and csv_file:
            raise click.BadOptionUsage(option_name='--event-filter',
                                       message=click.style('Pass either --csv or --csv-file, not both.', fg="red"))

        # ensure that event name is specified - different events would have different columns in the csv file
        if csv_file and not all((event_name, contract_name)):
            # TODO consider a single csv that just gets appended to for each event
            #  - each appended event adds their column names first
            #  - single report-type functionality, see #2561
            raise click.BadOptionUsage(option_name='--csv-file, --event-name, --contract_name',
                                       message=click.style('--event-name and --contract-name must be specified when outputting to '
                                               'specific file using --csv-file; alternatively use --csv', fg="red"))
    if not contract_name:
        if event_name:
            raise click.BadOptionUsage(option_name='--event-name', message=click.style('--event-name requires --contract-name', fg="red"))
        # FIXME should we force a contract name to be specified?
        # default to TACoApplication contract
        contract_names = [TACoApplicationAgent.contract_name]
    else:
        contract_names = [contract_name]

    emitter, registry, blockchain = registry_options.setup(general_config=general_config)

    if from_block is None:
        # by default, this command only shows events of the last 24 hours
        blocks_since_yesterday_kinda = ((60*60*24)//AVERAGE_BLOCK_TIME_IN_SECONDS)
        from_block = blockchain.client.block_number - blocks_since_yesterday_kinda
    if to_block is None:
        to_block = 'latest'
    else:
        # validate block range
        if from_block > to_block:
            raise click.BadOptionUsage(option_name='--to-block, --from-block',
                                       message=click.style(f'Invalid block range provided, '
                                               f'from-block ({from_block}) > to-block ({to_block})', fg="red"))

    # event argument filters
    argument_filters = None
    if event_filters:
        try:
            argument_filters = parse_event_filters_into_argument_filters(event_filters)
        except ValueError as e:
            raise click.BadOptionUsage(option_name='--event-filter',
                                       message=click.style(f'Event filter must be specified as name-value pairs of '
                                               f'the form `<name>=<value>` - {str(e)}', fg="red"))

    emitter.echo(f"Retrieving events from block {from_block} to {to_block}")

    for contract_name in contract_names:
        agent = ContractAgency.get_agent_by_contract_name(
            contract_name=contract_name, registry=registry
        )

        if event_name and event_name not in agent.events.names:
            raise click.BadOptionUsage(option_name='--event-name, --contract_name',
                                       message=click.style(f'{contract_name} contract does not have an event named {event_name}', fg="red"))

        title = f" {agent.contract_name} Events ".center(40, "-")
        emitter.echo(f"\n{title}\n", bold=True, color='green')
        names = agent.events.names if not event_name else [event_name]
        for name in names:
            # csv output file - one per (contract_name, event_name) pair
            csv_output_file = csv_file
            if csv or csv_output_file:
                if not csv_output_file:
                    csv_output_file = generate_events_csv_filepath(contract_name=agent.contract_name, event_name=name)

            retrieve_events(emitter=emitter,
                            agent=agent,
                            event_name=name,  # None is fine - just means all events
                            from_block=from_block,
                            to_block=to_block,
                            argument_filters=argument_filters,
                            csv_output_file=csv_output_file)
