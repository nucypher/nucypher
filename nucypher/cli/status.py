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

from nucypher.blockchain.eth.interfaces import BlockchainInterface
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
    #
    # Initialize
    #
    ursula_config = UrsulaConfiguration.from_configuration_file(filepath=config_file)
    if not ursula_config.federated_only:
        ursula_config.initialize_blockchain_interface()
        ursula_config.acquire_agency()

        # Contracts
        paint_contract_status(click_config.emitter, ursula_config=ursula_config, click_config=click_config)

    # Known Nodes
    paint_known_nodes(emitter=click_config.emitter, ursula=ursula_config)
