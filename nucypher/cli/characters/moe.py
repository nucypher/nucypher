import click
from cryptography.hazmat.primitives.asymmetric import ec
from flask import Flask
from twisted.internet import reactor
from umbral.keys import UmbralPrivateKey

from nucypher.blockchain.eth.interfaces import BlockchainInterfaceFactory
from nucypher.blockchain.eth.registry import InMemoryContractRegistry, LocalContractRegistry
from nucypher.characters.banners import MOE_BANNER
from nucypher.cli import actions
from nucypher.cli.config import nucypher_click_config
from nucypher.cli.types import NETWORK_PORT, EXISTING_READABLE_FILE
from nucypher.keystore.keypairs import HostingKeypair
from nucypher.network.middleware import RestMiddleware
from nucypher.network.server import TLSHostingPower
from nucypher.network.status_app.crawler import NetworkCrawler
from nucypher.network.status_app.moe import MoeDashboardApp


@click.group()
def moe():
    """
    "Moe the Monitor" management commands.
    """
    pass


@moe.command(name='crawl')
@click.option('--teacher', 'teacher_uri', help="An Ursula URI to start learning from (seednode)", type=click.STRING)
@click.option('--registry-filepath', help="Custom contract registry filepath", type=EXISTING_READABLE_FILE)
@click.option('--min-stake', help="The minimum stake the teacher must have to be a teacher", type=click.INT, default=0)
@click.option('--network', help="Network Domain Name", type=click.STRING, default='goerli')
@click.option('--host', help="The host to run Moe services on", type=click.STRING, default='127.0.0.1')
@click.option('--certificate-filepath', help="Pre-signed TLS certificate filepath")
@click.option('--tls-key-filepath', help="TLS private key filepath")
@click.option('--learn-on-launch', help="Conduct first learning loop on main thread at launch.", is_flag=True)
@click.option('--provider', 'provider_uri', help="Blockchain provider's URI", type=click.STRING)
@nucypher_click_config
def network_crawler(click_config,
                    teacher_uri,
                    registry_filepath,
                    min_stake,
                    network,
                    host,
                    certificate_filepath,
                    tls_key_filepath,
                    learn_on_launch,
                    provider_uri):
    """
    Gather NuCypher network information.
    """

    # Banner
    emitter = click_config.emitter
    emitter.clear()
    emitter.banner(MOE_BANNER)
    emitter.echo("> NETWORK CRAWLER")

    registry = __get_registry(provider_uri, registry_filepath)

    # Teacher Ursula
    teacher_uris = [teacher_uri] if teacher_uri else None
    teacher_nodes = actions.load_seednodes(emitter,
                                           teacher_uris=teacher_uris,
                                           min_stake=min_stake,
                                           federated_only=False,
                                           network_domains={network} if network else None,
                                           network_middleware=click_config.middleware)

    crawler = NetworkCrawler(domains={network} if network else None,
                             network_middleware=RestMiddleware(),
                             known_nodes=teacher_nodes,
                             registry=registry,
                             federated_only=False,
                             start_learning_now=True,
                             learn_on_same_thread=learn_on_launch)

    crawler.start()
    reactor.run()


@moe.command()
@click.option('--host', help="The host to run Moe services on", type=click.STRING, default='127.0.0.1')
@click.option('--http-port', help="The network port to run Moe services on", type=NETWORK_PORT, default=12500)
@click.option('--registry-filepath', help="Custom contract registry filepath", type=EXISTING_READABLE_FILE)
@click.option('--certificate-filepath', help="Pre-signed TLS certificate filepath")
@click.option('--tls-key-filepath', help="TLS private key filepath")
@click.option('--provider', 'provider_uri', help="Blockchain provider's URI", type=click.STRING)
@click.option('--network', help="Network Domain Name", type=click.STRING, default='goerli')
@click.option('--dry-run', '-x', help="Execute normally without actually starting the node", is_flag=True)
@nucypher_click_config
def dashboard(click_config,
              host,
              http_port,
              registry_filepath,
              certificate_filepath,
              tls_key_filepath,
              provider_uri,
              network,
              dry_run,
              ):
    """
    Run UI dashboard of NuCypher network.
    """

    # Banner
    emitter = click_config.emitter
    emitter.clear()
    emitter.banner(MOE_BANNER)
    emitter.echo("> UI DASHBOARD")

    registry = __get_registry(provider_uri, registry_filepath)

    #
    # WSGI Service
    #
    rest_app = Flask("moe-dashboard")
    MoeDashboardApp(title='Moe Dashboard Application',
                    flask_server=rest_app,
                    route_url='/',
                    registry=registry,
                    network=network)

    #
    # Server
    #
    tls_hosting_power = __get_tls_hosting_power(host=host,
                                                tls_certificate_filepath=certificate_filepath,
                                                tls_private_key_filepath=tls_key_filepath)
    emitter.message(f"Running Moe Dashboard - https://{host}:{http_port}")
    deployer = tls_hosting_power.get_deployer(rest_app=rest_app, port=http_port)
    if not dry_run:
        deployer.run()


def __get_registry(provider_uri, registry_filepath):
    BlockchainInterfaceFactory.initialize_interface(provider_uri=provider_uri)
    if registry_filepath:
        registry = LocalContractRegistry.from_latest_publication()
    else:
        registry = InMemoryContractRegistry.from_latest_publication()

    return registry


def __get_tls_hosting_power(host: str = None,
                            tls_certificate_filepath: str = None,
                            tls_private_key_filepath: str = None):
    # Pre-Signed
    if tls_certificate_filepath and tls_private_key_filepath:
        with open(tls_private_key_filepath, 'rb') as file:
            tls_private_key = UmbralPrivateKey.from_bytes(file.read())
        tls_hosting_keypair = HostingKeypair(curve=ec.SECP384R1,
                                             host=host,
                                             certificate_filepath=tls_certificate_filepath,
                                             private_key=tls_private_key)

    # Self-Sign
    else:
        tls_hosting_keypair = HostingKeypair(curve=ec.SECP384R1, host=host)

    tls_hosting_power = TLSHostingPower(keypair=tls_hosting_keypair, host=host)
    return tls_hosting_power
