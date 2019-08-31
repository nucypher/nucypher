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

from nucypher.blockchain.eth.interfaces import BlockchainInterface, BlockchainInterfaceFactory
from nucypher.blockchain.eth.registry import InMemoryContractRegistry
from nucypher.characters.banners import NU_BANNER
from nucypher.cli.actions import get_provider_process
from nucypher.cli.config import nucypher_click_config
from nucypher.cli.painting import paint_contract_status


@click.command()
@click.option('--poa', help="Inject POA middleware", is_flag=True, default=False)
@click.option('--sync/--no-sync', default=False)
@click.option('--geth', '-G', help="Run using the built-in geth node", is_flag=True)
@click.option('--provider', 'provider_uri', help="Blockchain provider's URI", type=click.STRING, default="auto://")
@nucypher_click_config
def status(click_config, provider_uri, sync, geth, poa):
    """
    Echo a snapshot of live network metadata.
    """

    emitter = click_config.emitter
    click.clear()
    emitter.banner(NU_BANNER)
    emitter.echo(message="Reading Latest Chaindata...")

    try:
        BlockchainInterfaceFactory.initialize_interface(provider_uri=provider_uri, sync=sync)
        registry = InMemoryContractRegistry.from_latest_publication()
        paint_contract_status(emitter=emitter, registry=registry)
        return  # Exit

    except Exception as e:
        if click_config.debug:
            raise
        click.secho(str(e), bold=True, fg='red')
        return  # Exit
