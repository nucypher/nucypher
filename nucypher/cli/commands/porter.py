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
from pathlib import Path

import click

from nucypher.blockchain.eth.networks import NetworksInventory
from nucypher.characters.lawful import Ursula
from nucypher.cli.config import group_general_config
from nucypher.cli.options import (
    option_network,
    option_provider_uri,
    option_federated_only,
    option_teacher_uri,
    option_registry_filepath,
    option_min_stake
)
from nucypher.cli.types import NETWORK_PORT
from nucypher.cli.utils import setup_emitter, get_registry
from nucypher.config.constants import TEMPORARY_DOMAIN
from nucypher.utilities.porter.control.interfaces import PorterInterface
from nucypher.utilities.porter.porter import Porter


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
@option_registry_filepath
@option_min_stake
@click.option('--http-port', help="Porter HTTP/HTTPS port for JSON endpoint", type=NETWORK_PORT, default=Porter.DEFAULT_PORT)
@click.option('--certificate-filepath', help="Pre-signed TLS certificate filepath", type=click.Path(dir_okay=False, exists=True, path_type=Path))
@click.option('--tls-key-filepath', help="TLS private key filepath", type=click.Path(dir_okay=False, exists=True, path_type=Path))
@click.option('--dry-run', '-x', help="Execute normally without actually starting Porter", is_flag=True)
@click.option('--eager', help="Start learning and scraping the network before starting up other services", is_flag=True, default=True)
def run(general_config,
        network,
        provider_uri,
        federated_only,
        teacher_uri,
        registry_filepath,
        min_stake,
        http_port,
        certificate_filepath,
        tls_key_filepath,
        dry_run,
        eager):
    """Start Porter's Web controller."""
    emitter = setup_emitter(general_config, banner=Porter.BANNER)

    if federated_only:
        if not teacher_uri:
            raise click.BadOptionUsage(option_name='--teacher',
                                       message="--teacher is required for federated porter.")

        teacher = Ursula.from_teacher_uri(teacher_uri=teacher_uri,
                                          federated_only=True,
                                          min_stake=min_stake)  # min stake is irrelevant for federated
        PORTER = Porter(domain=TEMPORARY_DOMAIN,
                        start_learning_now=eager,
                        known_nodes={teacher},
                        verify_node_bonding=False,
                        federated_only=True)
    else:
        # decentralized/blockchain
        if not provider_uri:
            raise click.BadOptionUsage(option_name='--provider',
                                       message="--provider is required for decentralized porter.")
        if not network:
            raise click.BadOptionUsage(option_name='--network',
                                       message="--network is required for decentralized porter.")

        registry = get_registry(network=network, registry_filepath=registry_filepath)
        teacher = None
        if teacher_uri:
            teacher = Ursula.from_teacher_uri(teacher_uri=teacher_uri,
                                              federated_only=False,  # always False
                                              min_stake=min_stake,
                                              registry=registry)

        PORTER = Porter(domain=network,
                        known_nodes={teacher} if teacher else None,
                        registry=registry,
                        start_learning_now=eager,
                        provider_uri=provider_uri)

    # RPC
    if general_config.json_ipc:
        rpc_controller = PORTER.make_rpc_controller()
        _transport = rpc_controller.make_control_transport()
        rpc_controller.start()
        return

    # HTTP/HTTPS
    if bool(tls_key_filepath) ^ bool(certificate_filepath):
        raise click.BadOptionUsage(option_name='--tls-key-filepath, --certificate-filepath',
                                   message='both --tls-key-filepath and --certificate-filepath must be specified to '
                                           'launch porter with TLS; only one specified')

    emitter.message(f"Network: {PORTER.domain.capitalize()}", color='green')
    if not federated_only:
        emitter.message(f"Provider: {provider_uri}", color='green')

    controller = PORTER.make_web_controller(crash_on_error=False)
    http_scheme = "https" if tls_key_filepath and certificate_filepath else "http"
    message = f"Running Porter Web Controller at {http_scheme}://127.0.0.1:{http_port}"
    emitter.message(message, color='green', bold=True)
    return controller.start(port=http_port,
                            tls_key_filepath=tls_key_filepath,
                            certificate_filepath=certificate_filepath,
                            dry_run=dry_run)
