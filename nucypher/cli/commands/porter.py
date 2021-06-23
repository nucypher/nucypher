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
from nucypher.cli.literature import BOTH_TLS_KEY_AND_CERTIFICATION_MUST_BE_PROVIDED, PORTER_RUN_MESSAGE, \
    BASIC_AUTH_REQUIRES_HTTPS
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
    Porter management commands. Porter is a web-service that is the conduit between applications and the
    nucypher network, that performs actions on behalf of Alice and Bob.
    """


@porter.command()
@group_general_config
@option_network(default=NetworksInventory.DEFAULT, validate=True, required=False)
@option_provider_uri(required=False)
@option_federated_only
@option_teacher_uri
@option_registry_filepath
@option_min_stake
@click.option('--http-port', help="Porter HTTP/HTTPS port for JSON endpoint", type=NETWORK_PORT, default=Porter.DEFAULT_PORT)
@click.option('--tls-certificate-filepath', help="Pre-signed TLS certificate filepath", type=click.Path(dir_okay=False, exists=True, path_type=Path))
@click.option('--tls-key-filepath', help="TLS private key filepath", type=click.Path(dir_okay=False, exists=True, path_type=Path))
@click.option('--basic-auth-filepath', help="htpasswd filepath for basic authentication", type=click.Path(dir_okay=False, exists=True, resolve_path=True, path_type=Path))
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
        tls_certificate_filepath,
        tls_key_filepath,
        basic_auth_filepath,
        dry_run,
        eager):
    """Start Porter's Web controller."""
    emitter = setup_emitter(general_config, banner=Porter.BANNER)

    # HTTP/HTTPS
    if bool(tls_key_filepath) ^ bool(tls_certificate_filepath):
        raise click.BadOptionUsage(option_name='--tls-key-filepath, --tls-certificate-filepath',
                                   message=BOTH_TLS_KEY_AND_CERTIFICATION_MUST_BE_PROVIDED)

    is_https = (tls_key_filepath and tls_certificate_filepath)

    # check authentication
    if basic_auth_filepath and not is_https:
        raise click.BadOptionUsage(option_name='--basic-auth-filepath',
                                   message=BASIC_AUTH_REQUIRES_HTTPS)

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
            # should never happen - network defaults to 'mainnet' if not specified
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

    emitter.message(f"Network: {PORTER.domain.capitalize()}", color='green')
    if not federated_only:
        emitter.message(f"Provider: {provider_uri}", color='green')

    if basic_auth_filepath:
        emitter.message("Basic Authentication enabled", color='green')

    controller = PORTER.make_web_controller(htpasswd_filepath=basic_auth_filepath, crash_on_error=False)
    http_scheme = "https" if is_https else "http"
    message = PORTER_RUN_MESSAGE.format(http_scheme=http_scheme, http_port=http_port)
    emitter.message(message, color='green', bold=True)
    return controller.start(port=http_port,
                            tls_key_filepath=tls_key_filepath,
                            tls_certificate_filepath=tls_certificate_filepath,
                            dry_run=dry_run)
