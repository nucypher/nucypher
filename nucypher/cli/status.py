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

import functools

import click

from nucypher.blockchain.eth.agents import StakingEscrowAgent, ContractAgency, PolicyManagerAgent
from nucypher.blockchain.eth.interfaces import BlockchainInterfaceFactory
from nucypher.blockchain.eth.registry import InMemoryContractRegistry, LocalContractRegistry
from nucypher.characters.banners import NU_BANNER
from nucypher.cli.actions import get_provider_process
from nucypher.cli.common_options import (
    group_options,
    option_geth,
    option_light,
    option_poa,
    option_provider_uri,
    option_registry_filepath,
    option_staking_address,
    )
from nucypher.cli.config import group_general_config
from nucypher.cli.painting import paint_contract_status, paint_stakers, paint_locked_tokens_status
from nucypher.cli.types import EIP55_CHECKSUM_ADDRESS, EXISTING_READABLE_FILE


group_common = group_options(
    'common',
    provider_uri=option_provider_uri(default="auto://"),
    geth=option_geth,
    poa=option_poa,
    light=option_light,
    registry_filepath=option_registry_filepath,
    )


@click.group()
def status():
    """
    Echo a snapshot of live NuCypher Network metadata.
    """
    pass


@status.command()
@group_common
@group_general_config
def network(general_config,

            # Common Options
            common
            ):
    """
    Overall information of the NuCypher Network.
    """
    # Init
    emitter = _setup_emitter(general_config)
    registry = _get_registry(
        general_config, emitter, common.geth, common.poa,
        common.light, common.provider_uri, common.registry_filepath)
    paint_contract_status(registry, emitter=emitter)


@status.command()
@group_common
@option_staking_address
@group_general_config
def stakers(general_config,

            # Common Options
            common,

            # Other
            staking_address):
    """
    Show relevant information about stakers.
    """
    # Init
    emitter = _setup_emitter(general_config)
    registry = _get_registry(
        general_config, emitter, common.geth, common.poa,
        common.light, common.provider_uri, common.registry_filepath)

    staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=registry)
    policy_agent = ContractAgency.get_agent(PolicyManagerAgent, registry=registry)

    stakers = [staking_address] if staking_address else staking_agent.get_stakers()
    paint_stakers(emitter=emitter, stakers=stakers, staking_agent=staking_agent, policy_agent=policy_agent)


@status.command(name='locked-tokens')
@group_common
@click.option('--periods', help="Number of periods", type=click.INT, default=90)
@group_general_config
def locked_tokens(general_config,

                  # Common Options
                  common,

                  # Other
                  periods):
    """
    Display a graph of the number of locked tokens over time.
    """
    # Init
    emitter = _setup_emitter(general_config)
    registry = _get_registry(
        general_config, emitter, common.geth, common.poa,
        common.light, common.provider_uri, common.registry_filepath)
    staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=registry)
    paint_locked_tokens_status(emitter=emitter, agent=staking_agent, periods=periods)


def _setup_emitter(general_config):
    emitter = general_config.emitter
    emitter.clear()
    emitter.banner(NU_BANNER)

    return emitter


def _get_registry(general_config, emitter, geth, poa, light, provider_uri, registry_filepath):
    try:
        ETH_NODE = None
        if geth:
            ETH_NODE = get_provider_process()

        # Note: For test compatibility.
        if not BlockchainInterfaceFactory.is_interface_initialized(provider_uri=provider_uri):
            BlockchainInterfaceFactory.initialize_interface(provider_uri=provider_uri,
                                                            provider_process=ETH_NODE,
                                                            poa=poa,
                                                            light=light,
                                                            sync=False,
                                                            show_sync_progress=False)

        blockchain = BlockchainInterfaceFactory.get_interface()

        emitter.echo(message="Reading Latest Chaindata...")
        blockchain.connect()
    except Exception as e:
        if general_config.debug:
            raise
        click.secho(str(e), bold=True, fg='red')
        raise click.Abort
    if registry_filepath:
        registry = LocalContractRegistry(filepath=registry_filepath)
    else:
        registry = InMemoryContractRegistry.from_latest_publication()

    return registry
