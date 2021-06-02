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
from nucypher.characters.lawful import Ursula
from nucypher.cli.config import group_general_config
from nucypher.cli.options import option_network, option_provider_uri, option_federated_only, option_teacher_uri
from nucypher.cli.types import NETWORK_PORT
from nucypher.cli.utils import setup_emitter
from nucypher.utilities.porter.control.interfaces import PorterInterface
from nucypher.utilities.porter.porter import Porter

from nucypher.config.constants import TEMPORARY_DOMAIN

@click.group()
def porter():
    """
    Porter management commands. Porter is the conduit between web apps and the nucypher network, that performs actions
    on behalf of Alice and Bob.
    """


@porter.command()
@group_general_config
@PorterInterface.connect_cli('get_ursulas')
def get_ursulas(general_config, porter_uri, quantity, duration_periods, exclude_ursulas, include_ursulas):
    """Sample Ursulas on behalf of Alice."""
    pass


@porter.command()
@group_general_config
@PorterInterface.connect_cli('publish_treasure_map')
def publish_treasure_map(general_config, porter_uri, treasure_map, bob_encrypting_key):
    """Publish a treasure map on behalf of Alice."""
    pass


@porter.command()
@group_general_config
@PorterInterface.connect_cli('revoke')
def revoke(general_config, porter_uri):
    """Off-chain revoke of a policy on behalf of Alice."""
    pass


@porter.command()
@group_general_config
@PorterInterface.connect_cli('get_treasure_map')
def get_treasure_map(general_config, porter_uri, treasure_map_id, bob_encrypting_key):
    """Retrieve a treasure map on behalf of Bob."""
    pass


@porter.command()
@group_general_config
@PorterInterface.connect_cli('exec_work_order')
def exec_work_order(general_config, porter_uri, ursula, work_order):
    """Execute a PRE work order on behalf of Bob."""
    pass


@porter.command()
@group_general_config
@option_network(default=NetworksInventory.DEFAULT, validate=True, required=False)
@option_provider_uri(required=False)
@option_federated_only
@option_teacher_uri
@click.option('--http-port', help="Porter HTTP port for JSON endpoint", type=NETWORK_PORT, default=Porter.DEFAULT_PORTER_HTTP_PORT)
@click.option('--dry-run', '-x', help="Execute normally without actually starting Porter", is_flag=True)
@click.option('--eager', help="Start learning and scraping the network before starting up other services", is_flag=True, default=True)
def run(general_config, network, provider_uri, federated_only, teacher_uri, http_port, dry_run, eager):
    """Start Porter's Web controller."""
    emitter = setup_emitter(general_config, banner=Porter.BANNER)

    if federated_only:
        if not teacher_uri:
            raise click.BadOptionUsage(option_name='--teacher',
                                       message="--teacher is required for federated porter.")

        ursula = Ursula.from_seed_and_stake_info(seed_uri="localhost:11500",
                                                 federated_only=True,
                                                 minimum_stake=0)
        PORTER = Porter(domain=TEMPORARY_DOMAIN,
                        start_learning_now=eager,
                        known_nodes={ursula},
                        verify_node_bonding=False,
                        federated_only=True)
    else:
        if not provider_uri:
            raise click.BadOptionUsage(option_name='--provider',
                                       message="--provider is required for decentralized porter.")
        if not network:
            raise click.BadOptionUsage(option_name='--network',
                                       message="--network is required for decentralized porter.")

        BlockchainInterfaceFactory.initialize_interface(provider_uri=provider_uri)
        PORTER = Porter(domain=network,
                        start_learning_now=eager)

    # RPC
    if general_config.json_ipc:
        rpc_controller = PORTER.make_rpc_controller()
        _transport = rpc_controller.make_control_transport()
        rpc_controller.start()
        return

    # HTTP
    emitter.message(f"Network: {PORTER.domain.capitalize()}", color='green')
    if not federated_only:
        emitter.message(f"Provider: {provider_uri}", color='green')

    controller = PORTER.make_web_controller(crash_on_error=False)
    message = f"Running Porter Web Controller at http://localhost:{http_port}"
    emitter.message(message, color='green', bold=True)
    return controller.start(http_port=http_port, dry_run=dry_run)
