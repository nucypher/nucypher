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
from pathlib import Path

import click

from nucypher.blockchain.eth.agents import ContractAgency, PolicyManagerAgent, StakingEscrowAgent
from nucypher.blockchain.eth.constants import (
    POLICY_MANAGER_CONTRACT_NAME,
    STAKING_ESCROW_CONTRACT_NAME
)
from nucypher.blockchain.eth.events import EventRecord
from nucypher.blockchain.eth.networks import NetworksInventory
from nucypher.blockchain.eth.utils import estimate_block_number_for_period
from nucypher.cli.config import group_general_config
from nucypher.cli.literature import CONFIRM_OVERWRITE_EVENTS_CSV_FILE
from nucypher.cli.options import (
    group_options,
    option_contract_name,
    option_event_name,
    option_light,
    option_network,
    option_poa,
    option_provider_uri,
    option_registry_filepath,
    option_staking_address,
)
from nucypher.cli.painting.staking import paint_fee_rate_range
from nucypher.cli.painting.status import paint_contract_status, paint_locked_tokens_status, paint_stakers
from nucypher.cli.utils import connect_to_blockchain, get_registry, setup_emitter
from nucypher.config.constants import NUCYPHER_ENVVAR_PROVIDER_URI
from nucypher.utilities.events import (
    generate_events_csv_file,
    write_events_to_csv_file,
    parse_event_filters_into_argument_filters
)


class RegistryOptions:

    __option_name__ = 'registry_options'

    def __init__(self, provider_uri, poa, registry_filepath, light, network):
        self.provider_uri = provider_uri
        self.poa = poa
        self.registry_filepath = registry_filepath
        self.light = light
        self.network = network

    def setup(self, general_config) -> tuple:
        emitter = setup_emitter(general_config)
        registry = get_registry(network=self.network, registry_filepath=self.registry_filepath)
        blockchain = connect_to_blockchain(emitter=emitter, provider_uri=self.provider_uri)
        return emitter, registry, blockchain


group_registry_options = group_options(
    RegistryOptions,
    poa=option_poa,
    light=option_light,
    registry_filepath=option_registry_filepath,
    network=option_network(default=NetworksInventory.DEFAULT, validate=True),  # TODO: See 2214
    provider_uri=option_provider_uri(default=os.environ.get(NUCYPHER_ENVVAR_PROVIDER_URI)),
)

option_csv = click.option('--csv',
                          help="Write event data to a CSV file using a default filename in the current directory",
                          default=False,
                          is_flag=True)
option_csv_file = click.option('--csv-file',
                               help="Write event data to the CSV file at specified filepath",
                               type=click.Path(dir_okay=False))
option_event_filters = click.option('--event-filter', '-f', 'event_filters',
                                    help="Event filter of the form <name>=<value>",
                                    multiple=True,
                                    type=click.STRING,
                                    default=[])

option_from_block = click.option('--from-block',
                                 help="Collect events from this block number; defaults to the block number of current period",
                                 type=click.INT)
option_to_block = click.option('--to-block',
                               help="Collect events until this block number; defaults to 'latest' block number",
                               type=click.INT)


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


@status.command()
@group_registry_options
@option_staking_address
@group_general_config
def stakers(general_config, registry_options, staking_address):
    """Show relevant information about stakers."""
    emitter, registry, blockchain = registry_options.setup(general_config=general_config)
    staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=registry)
    stakers_list = [staking_address] if staking_address else staking_agent.get_stakers()
    paint_stakers(emitter=emitter, stakers=stakers_list, registry=registry)


@status.command(name='locked-tokens')
@group_registry_options
@click.option('--periods', help="Number of periods", type=click.INT, default=90)
@group_general_config
def locked_tokens(general_config, registry_options, periods):
    """Display a graph of the number of locked tokens over time."""
    emitter, registry, blockchain = registry_options.setup(general_config=general_config)
    staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=registry)
    paint_locked_tokens_status(emitter=emitter, agent=staking_agent, periods=periods)


@status.command()
@group_registry_options
@group_general_config
@option_contract_name(required=False)
@option_event_name
@option_from_block
@option_to_block
@option_csv
@option_csv_file
@option_event_filters
# TODO: Add options for number of periods in the past (default current period), or range of blocks
def events(general_config, registry_options, contract_name, from_block, to_block, event_name, csv, csv_file, event_filters):
    """Show events associated to NuCypher contracts."""

    emitter, registry, blockchain = registry_options.setup(general_config=general_config)
    if not contract_name:
        if event_name:
            raise click.BadOptionUsage(option_name='--event-name', message='--event-name requires --contract-name')
        contract_names = [STAKING_ESCROW_CONTRACT_NAME, POLICY_MANAGER_CONTRACT_NAME]
    else:
        contract_names = [contract_name]

    if from_block is None:
        # by default, this command only shows events of the current period
        last_block = blockchain.client.block_number
        staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=registry)
        current_period = staking_agent.get_current_period()
        from_block = estimate_block_number_for_period(period=current_period,
                                                      seconds_per_period=staking_agent.staking_parameters()[0],
                                                      latest_block=last_block)
    if to_block is None:
        to_block = 'latest'

    # event argument filters
    argument_filters = None
    if event_filters:
        try:
            argument_filters = parse_event_filters_into_argument_filters(event_filters)
        except ValueError as e:
            raise click.BadOptionUsage(option_name='--event-filter',
                                       message=f'Event filter must be specified as name-value pairs of '
                                               f'the form `<name>=<value>` - {str(e)}')

    # csv output file
    csv_output_file = csv_file
    if csv or csv_output_file:
        # ensure that event name is specified - different events would have different columns in the csv file
        if not event_name:
            raise click.BadOptionUsage(option_name='--csv, --csv-file, --event-name',
                                       message='Event name must be specified to output events to csv file')
        if not csv_output_file:
            csv_output_file = generate_events_csv_file(event_name)  # output to one file - use generic name

        if Path(csv_output_file).exists():
            click.confirm(CONFIRM_OVERWRITE_EVENTS_CSV_FILE.format(csv_file=csv_output_file), abort=True)

    # TODO: additional input validation for block numbers
    emitter.echo(f"Obtaining events from block {from_block} to {to_block}")
    for contract_name in contract_names:
        agent = ContractAgency.get_agent_by_contract_name(contract_name, registry)
        names = agent.events.names if not event_name else [event_name]
        if csv_output_file:
            # csv output
            for name in names:
                write_events_to_csv_file(csv_file=csv_output_file,
                                         agent=agent,
                                         event_name=name,
                                         to_block=to_block,
                                         from_block=from_block,
                                         argument_filters=argument_filters)
                emitter.echo(f"\n{contract_name}::{name} events written to {csv_output_file}",
                             bold=True,
                             color='green')
        else:
            title = f" {contract_name} Events ".center(40, "-")
            emitter.echo(f"\n{title}\n", bold=True, color='green')
            for name in names:
                emitter.echo(f"{name}:", bold=True, color='yellow')
                event_method = agent.contract.events[name]
                entries = event_method.getLogs(fromBlock=from_block, toBlock=to_block, argument_filters=argument_filters)
                for event_record in entries:
                    emitter.echo(f"  - {EventRecord(event_record)}")


@status.command(name='fee-range')
@group_registry_options
@group_general_config
def fee_range(general_config, registry_options):
    """Provide information on the global fee range – the range into which the minimum fee rate must fall."""
    emitter, registry, blockchain = registry_options.setup(general_config=general_config)
    policy_agent = ContractAgency.get_agent(PolicyManagerAgent, registry=registry)
    paint_fee_rate_range(emitter=emitter, policy_agent=policy_agent)
