import click

from nucypher.blockchain.eth.interfaces import BlockchainInterfaceFactory
from nucypher.blockchain.eth.registry import InMemoryContractRegistry, LocalContractRegistry
from nucypher.characters.banners import MOE_BANNER
from nucypher.characters.chaotic import Moe
from nucypher.cli import actions
from nucypher.cli.config import nucypher_click_config
from nucypher.cli.types import NETWORK_PORT, EXISTING_READABLE_FILE
from nucypher.network.middleware import RestMiddleware

from twisted.internet import reactor

from nucypher.network.status_app.crawler import NetworkCrawler


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
@click.option('--network', help="Network Domain Name", type=click.STRING)
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

    BlockchainInterfaceFactory.initialize_interface(provider_uri=provider_uri)
    if registry_filepath:
        registry = LocalContractRegistry.from_latest_publication()
    else:
        registry = InMemoryContractRegistry.from_latest_publication()

    # Teacher Ursula
    teacher_uris = [teacher_uri] if teacher_uri else None
    teacher_nodes = actions.load_seednodes(emitter,
                                           teacher_uris=teacher_uris,
                                           min_stake=min_stake,
                                           federated_only=False,
                                           network_domains={network} if network else None,
                                           network_middleware=click_config.middleware)

    # Make Moe
    MOE = Moe(domains={network} if network else None,
              network_middleware=RestMiddleware(),
              known_nodes=teacher_nodes,
              registry=registry,
              federated_only=False,
              host=host,
              tls_certificate_filepath=certificate_filepath,
              tls_private_key_filepath=tls_key_filepath,
              start_learning_now=True,
              learn_on_same_thread=learn_on_launch)

    # Learn about nodes
    MOE.start_learning_loop(now=learn_on_launch)

    # Start Network Crawler that learns about the network
    crawler = NetworkCrawler(moe=MOE)
    crawler.start()

    reactor.run()


@moe.command()
def dashboard():
    """
    Run UI dashboard of NuCypher network.
    """
    # #
    # # WSGI Service
    # #
    # self.rest_app = Flask("fleet-monitor")
    # rest_app = self.rest_app
    # MoeStatusApp(moe=self,
    #              title='Moe Monitoring Application',
    #              flask_server=self.rest_app,
    #              route_url='/')
    #
    # #
    # # Server
    # #
    # deployer = self._crypto_power.power_ups(TLSHostingPower).get_deployer(rest_app=rest_app, port=self.http_port)
    # if not dry_run:
    #     deployer.run()
    #
    # pass
    pass
