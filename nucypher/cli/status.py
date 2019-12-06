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

from nucypher.blockchain.eth.agents import StakingEscrowAgent, ContractAgency
from nucypher.blockchain.eth.interfaces import BlockchainInterfaceFactory
from nucypher.blockchain.eth.registry import InMemoryContractRegistry, LocalContractRegistry
from nucypher.characters.banners import NU_BANNER
from nucypher.cli.actions import get_provider_process
from nucypher.cli.config import nucypher_click_config
from nucypher.cli.painting import paint_contract_status, paint_stakers, paint_locked_tokens_status
from nucypher.cli.types import EIP55_CHECKSUM_ADDRESS, EXISTING_READABLE_FILE


# Args (provider_uri, geth, poa, registry_filepath)
def _common_options(func):
    @click.option('--provider', 'provider_uri', help="Blockchain provider's URI", type=click.STRING, default="auto://")
    @click.option('--geth', '-G', help="Run using the built-in geth node", is_flag=True)
    @click.option('--poa', help="Inject POA middleware", is_flag=True, default=False)
    @click.option('--light', help="Indicate that node is light", is_flag=True, default=False)
    @click.option('--registry-filepath', help="Custom contract registry filepath", type=EXISTING_READABLE_FILE)
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)
    return wrapper


@click.group()
def status():
    """
    Echo a snapshot of live NuCypher Network metadata.
    """
    pass


@status.command()
@_common_options
@nucypher_click_config
def network(click_config,

            # Common Options
            provider_uri, geth, poa, light, registry_filepath):
    """
    Overall information of the NuCypher Network.
    """
    # Init
    emitter = _setup_emitter(click_config)
    staking_agent = _get_staking_agent(click_config, emitter, geth, poa, light, provider_uri, registry_filepath)

    paint_contract_status(staking_agent.registry, emitter=emitter)


@status.command()
@_common_options
@click.option('--staking-address', help="Address of a NuCypher staker", type=EIP55_CHECKSUM_ADDRESS)
@nucypher_click_config
def stakers(click_config,

            # Common Options
            provider_uri, geth, poa, light, registry_filepath,

            # Other
            staking_address):
    """
    Show relevant information about stakers.
    """
    # Init
    emitter = _setup_emitter(click_config)
    staking_agent = _get_staking_agent(click_config, emitter, geth, poa, light, provider_uri, registry_filepath)

    stakers = [staking_address] if staking_address else staking_agent.get_stakers()
    paint_stakers(emitter=emitter, stakers=stakers, agent=staking_agent)


@status.command(name='locked-tokens')
@_common_options
@click.option('--periods', help="Number of periods", type=click.INT, default=90)
@nucypher_click_config
def locked_tokens(click_config,

                  # Common Options
                  provider_uri, geth, poa, light, registry_filepath,

                  # Other
                  periods):
    """
    Display a graph of the number of locked tokens over time.
    """
    # Init
    emitter = _setup_emitter(click_config)
    staking_agent = _get_staking_agent(click_config, emitter, geth, poa, light, provider_uri, registry_filepath)

    paint_locked_tokens_status(emitter=emitter, agent=staking_agent, periods=periods)


def _setup_emitter(click_config):
    emitter = click_config.emitter
    emitter.clear()
    emitter.banner(NU_BANNER)

    return emitter


def _get_staking_agent(click_config, emitter, geth, poa, light, provider_uri, registry_filepath):
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
        if click_config.debug:
            raise
        click.secho(str(e), bold=True, fg='red')
        raise click.Abort
    if registry_filepath:
        registry = LocalContractRegistry(filepath=registry_filepath)
    else:
        registry = InMemoryContractRegistry.from_latest_publication()

    staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=registry)
    return staking_agent
