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

from nucypher.blockchain.eth.agents import StakingEscrowAgent, ContractAgency
from nucypher.blockchain.eth.interfaces import BlockchainInterfaceFactory
from nucypher.blockchain.eth.registry import InMemoryContractRegistry
from nucypher.characters.banners import NU_BANNER
from nucypher.cli.actions import get_provider_process
from nucypher.cli.config import nucypher_click_config
from nucypher.cli.painting import paint_contract_status, paint_stakers, paint_locked_tokens_status, paint_known_nodes
from nucypher.config.characters import UrsulaConfiguration


@click.command()
@click.argument('action')
@click.option('--poa', help="Inject POA middleware", is_flag=True, default=False)
@click.option('--sync/--no-sync', default=False)
@click.option('--geth', '-G', help="Run using the built-in geth node", is_flag=True)
@click.option('--provider', 'provider_uri', help="Blockchain provider's URI", type=click.STRING, default="auto://")
@click.option('--periods', help="Number of periods", type=click.INT, default=90)
@nucypher_click_config
def status(click_config, action, provider_uri, sync, geth, poa, periods):
    """
    Echo a snapshot of live network metadata.
    """

    emitter = click_config.emitter
    click.clear()
    emitter.banner(NU_BANNER)

    try:
        ETH_NODE = None
        if geth:
            ETH_NODE = get_provider_process()

        BlockchainInterfaceFactory.initialize_interface(provider_uri=provider_uri,
                                                        provider_process=ETH_NODE,
                                                        poa=poa)
        blockchain = BlockchainInterfaceFactory.get_interface()
        emitter.echo(message="Reading Latest Chaindata...")
        blockchain.connect()
    except Exception as e:
        if click_config.debug:
            raise
        click.secho(str(e), bold=True, fg='red')
        return  # Exit

    # TODO: Allow --registry
    registry = InMemoryContractRegistry.from_latest_publication()
    staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=registry)

    if action == 'view':
        ursula_config = UrsulaConfiguration.from_configuration_file(filepath=click_config.config_file)
        if not ursula_config.federated_only:
            paint_contract_status(registry, emitter=emitter)

        paint_known_nodes(emitter=click_config.emitter, ursula=ursula_config)
        return  # Exit

    if action == 'stakers':
        paint_stakers(emitter=emitter, stakers=staking_agent.get_stakers(), agent=staking_agent)
        return  # Exit

    elif action == 'locked-tokens':
        paint_locked_tokens_status(emitter=emitter, agent=staking_agent, periods=periods)
        return  # Exit

    else:
        ctx = click.get_current_context()
        click.UsageError(message=f"Unknown action '{action}'.", ctx=ctx).show()
