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
import maya
import os

from nucypher.blockchain.eth.agents import ContractAgency, PolicyManagerAgent, StakingEscrowAgent
from nucypher.blockchain.eth.constants import (
    AVERAGE_BLOCK_TIME_IN_SECONDS,
    POLICY_MANAGER_CONTRACT_NAME,
    STAKING_ESCROW_CONTRACT_NAME
)
from nucypher.blockchain.eth.utils import datetime_at_period
from nucypher.cli.config import group_general_config
from nucypher.cli.options import (
    group_options,
    option_contract_name,
    option_event_name,
    option_geth,
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


class RegistryOptions:

    __option_name__ = 'registry_options'

    def __init__(self, provider_uri, geth, poa, registry_filepath, light, network):
        self.provider_uri = provider_uri
        self.geth = geth
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
    geth=option_geth,
    poa=option_poa,
    light=option_light,
    registry_filepath=option_registry_filepath,
    network=option_network(),
    provider_uri=option_provider_uri(default=os.environ.get(NUCYPHER_ENVVAR_PROVIDER_URI)),
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


@status.command()
@group_registry_options
@option_staking_address
@group_general_config
def stakers(general_config, registry_options, staking_address):
    """Show relevant information about stakers."""
    emitter, registry, blockchain = registry_options.setup(general_config=general_config)
    staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=registry)
    policy_agent = ContractAgency.get_agent(PolicyManagerAgent, registry=registry)
    stakers_list = [staking_address] if staking_address else staking_agent.get_stakers()
    paint_stakers(emitter=emitter, stakers=stakers_list, staking_agent=staking_agent, policy_agent=policy_agent)


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
@option_contract_name
@option_event_name
@click.option('--from-block', help="Collect events from this block number", type=click.INT)
@click.option('--to-block', help="Collect events until this block number", type=click.INT)
# TODO: Add options for number of periods in the past (default current period), or range of blocks
# TODO: Add way to input additional event filters? (e.g., staker, etc)
def events(general_config, registry_options, contract_name, from_block, to_block, event_name):
    """Show events associated to NuCypher contracts."""

    emitter, registry, blockchain = registry_options.setup(general_config=general_config)
    if not contract_name:
        if event_name:
            raise click.BadOptionUsage(option_name='--event-name', message='--event-name requires --contract-name')
        contract_names = [STAKING_ESCROW_CONTRACT_NAME, POLICY_MANAGER_CONTRACT_NAME]
    else:
        contract_names = [contract_name]

    if from_block is None:
        # Sketch of logic for getting the approximate block height of current period start,
        # so by default, this command only shows events of the current period
        last_block = blockchain.client.w3.eth.blockNumber
        staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=registry)
        current_period = staking_agent.get_current_period()
        current_period_start = datetime_at_period(period=current_period,
                                                  seconds_per_period=staking_agent.staking_parameters()[0],
                                                  start_of_period=True)
        seconds_from_midnight = int((maya.now() - current_period_start).total_seconds())
        blocks_from_midnight = seconds_from_midnight // AVERAGE_BLOCK_TIME_IN_SECONDS

        from_block = last_block - blocks_from_midnight

    if to_block is None:
        to_block = 'latest'

    # TODO: additional input validation for block numbers
    emitter.echo(f"Showing events from block {from_block} to {to_block}")
    for contract_name in contract_names:
        title = f" {contract_name} Events ".center(40, "-")
        emitter.echo(f"\n{title}\n", bold=True, color='green')
        agent = ContractAgency.get_agent_by_contract_name(contract_name, registry)
        names = agent.events.names if not event_name else [event_name]
        for name in names:
            emitter.echo(f"{name}:", bold=True, color='yellow')
            event_method = agent.events[name]
            for event_record in event_method(from_block=from_block, to_block=to_block):
                emitter.echo(f"  - {event_record}")


@status.command(name='fee-range')
@group_registry_options
@group_general_config
def fee_range(general_config, registry_options):
    """Provide information on the global fee range – the range into which the minimum fee rate must fall."""
    emitter, registry, blockchain = registry_options.setup(general_config=general_config)
    policy_agent = ContractAgency.get_agent(PolicyManagerAgent, registry=registry)
    paint_fee_rate_range(emitter=emitter, policy_agent=policy_agent)
