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

from nucypher.blockchain.eth.interfaces import BlockchainInterfaceFactory
from nucypher.blockchain.eth.networks import NetworksInventory
from nucypher.cli.options import option_network, option_provider_uri
from nucypher.cli.types import NETWORK_PORT
from nucypher.control.emitters import StdoutEmitter
from nucypher.utilities.porter.control.interfaces import PorterInterface
from nucypher.utilities.porter.porter import Porter


@click.group()
def porter():
    """
    Porter management commands. Porter is the conduit between web apps and the nucypher network, that performs actions
    on behalf of Alice and Bob.
    """


@porter.command()
@PorterInterface.connect_cli('get_ursulas')
def get_ursulas(porter_uri, quantity, duration_periods, exclude_ursulas, include_ursulas):
    """Sample Ursulas on behalf of Alice."""
    pass


@porter.command()
@PorterInterface.connect_cli('publish_treasure_map')
def publish_treasure_map(porter_uri, treasure_map, bob_encrypting_key):
    """Publish a treasure map on behalf of Alice."""
    pass


@porter.command()
@PorterInterface.connect_cli('revoke')
def revoke(porter_uri):
    """Off-chain revoke of a policy on behalf of Alice."""
    pass


@porter.command()
@PorterInterface.connect_cli('get_treasure_map')
def get_treasure_map(porter_uri, treasure_map_id, bob_encrypting_key):
    """Retrieve a treasure map on behalf of Bob."""
    pass


@porter.command()
@PorterInterface.connect_cli('exec_work_order')
def exec_work_order(porter_uri, ursula, work_order):
    """Execute a PRE work order on behalf of Bob."""
    pass


@porter.command()
@option_network(default=NetworksInventory.DEFAULT, validate=True, required=True)
@option_provider_uri(required=True)
@click.option('--http-port', help="Porter HTTP port for JSON endpoint", type=NETWORK_PORT, default=9155)  # TODO some default value from Porter Learner Class
@click.option('--dry-run', '-x', help="Execute normally without actually starting Porter", is_flag=True)
@click.option('--eager', help="Start learning and scraping the network before starting up other services", is_flag=True, default=True)
def run(network, provider_uri, http_port, dry_run, eager):
    """Start Porter's Web controller."""
    emitter = StdoutEmitter()
    emitter.clear()
    emitter.banner(Porter.BANNER)

    # Setup
    BlockchainInterfaceFactory.initialize_interface(provider_uri=provider_uri)

    PORTER = Porter(domain=network,
                    start_learning_now=eager)

    # HTTP
    emitter.message(f"Network: {network.capitalize()}", color='green')
    emitter.message(f"Provider: {provider_uri}", color='green')
    controller = PORTER.make_web_controller(crash_on_error=False)
    message = f"Running Porter Web Controller at http://localhost:{http_port}"
    emitter.message(message, color='green', bold=True)
    return controller.start(http_port=http_port, dry_run=dry_run)
