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

from nucypher.blockchain.eth.agents import StakingEscrowAgent, ContractAgency, PolicyManagerAgent
from nucypher.blockchain.eth.constants import (
    STAKING_ESCROW_CONTRACT_NAME,
    POLICY_MANAGER_CONTRACT_NAME,
    AVERAGE_BLOCK_TIME_IN_SECONDS
)
from nucypher.blockchain.eth.interfaces import BlockchainInterfaceFactory
from nucypher.blockchain.eth.registry import InMemoryContractRegistry, LocalContractRegistry
from nucypher.blockchain.eth.utils import datetime_at_period
from nucypher.characters.banners import NU_BANNER
from nucypher.cli.actions import get_provider_process
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
from nucypher.cli.painting import paint_contract_status, paint_stakers, paint_locked_tokens_status, \
    paint_min_reward_range


class RegistryOptions:

    __option_name__ = 'registry_options'

    def __init__(self, provider_uri, geth, poa, registry_filepath, light, network):
        self.provider_uri = provider_uri
        self.geth = geth
        self.poa = poa
        self.registry_filepath = registry_filepath
        self.light = light
        self.network = network

    def get_registry(self, emitter, debug):
        try:
            eth_node = None
            if self.geth:
                eth_node = get_provider_process()

            # Note: For test compatibility.
            if not BlockchainInterfaceFactory.is_interface_initialized(provider_uri=self.provider_uri):
                BlockchainInterfaceFactory.initialize_interface(provider_uri=self.provider_uri,
                                                                provider_process=eth_node,
                                                                poa=self.poa,
                                                                light=self.light,
                                                                sync=False,
                                                                emitter=emitter)

            blockchain = BlockchainInterfaceFactory.get_interface(provider_uri=self.provider_uri)

            emitter.echo(message="Reading Latest Chaindata...")
            blockchain.connect()
        except Exception as e:
            if debug:
                raise
            click.secho(str(e), bold=True, fg='red')
            raise click.Abort
        if self.registry_filepath:
            registry = LocalContractRegistry(filepath=self.registry_filepath)
        else:
            registry = InMemoryContractRegistry.from_latest_publication(network=self.network)

        return registry


group_registry_options = group_options(
    RegistryOptions,
    provider_uri=option_provider_uri(),
    geth=option_geth,
    poa=option_poa,
    light=option_light,
    registry_filepath=option_registry_filepath,
    network=option_network,
    )


@click.group()
def status():
    """
    Echo a snapshot of live NuCypher Network metadata.
    """
    pass


@status.command()
@group_registry_options
@group_general_config
def network(general_config, registry_options):
    """
    Overall information of the NuCypher Network.
    """
    emitter = _setup_emitter(general_config)
    registry = registry_options.get_registry(emitter, general_config.debug)
    paint_contract_status(registry, emitter=emitter)


@status.command()
@group_registry_options
@option_staking_address
@group_general_config
def stakers(general_config, registry_options, staking_address):
    """
    Show relevant information about stakers.
    """
    emitter = _setup_emitter(general_config)
    registry = registry_options.get_registry(emitter, general_config.debug)

    staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=registry)
    policy_agent = ContractAgency.get_agent(PolicyManagerAgent, registry=registry)

    stakers_list = [staking_address] if staking_address else staking_agent.get_stakers()
    paint_stakers(emitter=emitter, stakers=stakers_list, staking_agent=staking_agent, policy_agent=policy_agent)


@status.command(name='locked-tokens')
@group_registry_options
@click.option('--periods', help="Number of periods", type=click.INT, default=90)
@group_general_config
def locked_tokens(general_config, registry_options, periods):
    """
    Display a graph of the number of locked tokens over time.
    """
    emitter = _setup_emitter(general_config)
    registry = registry_options.get_registry(emitter, general_config.debug)
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
    """
    Show events associated to NuCypher contracts
    """
    emitter = _setup_emitter(general_config)
    registry = registry_options.get_registry(emitter, general_config.debug)
    blockchain = BlockchainInterfaceFactory.get_interface(provider_uri=registry_options.provider_uri)

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


@status.command(name='reward-range')
@group_registry_options
@group_general_config
def reward_range(general_config, registry_options):
    """
    Show information about the allowed range for min reward rate.
    """
    emitter = _setup_emitter(general_config)
    registry = registry_options.get_registry(emitter, general_config.debug)
    policy_agent = ContractAgency.get_agent(PolicyManagerAgent, registry=registry)
    paint_min_reward_range(emitter=emitter, policy_agent=policy_agent)


def _setup_emitter(general_config):
    emitter = general_config.emitter
    emitter.banner(NU_BANNER)
    return emitter

