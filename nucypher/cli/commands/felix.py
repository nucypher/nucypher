import functools
import os

import click
from constant_sorrow.constants import NO_BLOCKCHAIN_CONNECTION

from nucypher.characters.banners import FELIX_BANNER
from nucypher.cli import actions, painting
from nucypher.cli.actions import get_nucypher_password, unlock_nucypher_keyring
from nucypher.cli.config import nucypher_click_config
from nucypher.cli.types import NETWORK_PORT, EXISTING_READABLE_FILE, EIP55_CHECKSUM_ADDRESS
from nucypher.config.characters import FelixConfiguration
from nucypher.config.constants import DEFAULT_CONFIG_ROOT


# Args (checksum_address, geth, dev, network, registry_filepath,  provider_uri, host, db_filepath, poa)
def _admin_options(func):
    @click.option('--checksum-address', help="Run with a specified account", type=EIP55_CHECKSUM_ADDRESS)
    @click.option('--geth', '-G', help="Run using the built-in geth node", is_flag=True)
    @click.option('--dev', '-d', help="Enable development mode", is_flag=True)
    @click.option('--network', help="Network Domain Name", type=click.STRING)
    @click.option('--registry-filepath', help="Custom contract registry filepath", type=EXISTING_READABLE_FILE)
    @click.option('--provider', 'provider_uri', help="Blockchain provider's URI", type=click.STRING)
    @click.option('--host', help="The host to run Felix HTTP services on", type=click.STRING, default='127.0.0.1')
    @click.option('--db-filepath', help="The database filepath to connect to", type=click.STRING)
    @click.option('--poa', help="Inject POA middleware", is_flag=True, default=None)
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)
    return wrapper


# Args (config_file, port, teacher_uri)
def _api_options(func):
    @_admin_options
    @click.option('--config-file', help="Path to configuration file", type=EXISTING_READABLE_FILE)
    @click.option('--port', help="The host port to run Felix HTTP services on", type=NETWORK_PORT,
                  default=FelixConfiguration.DEFAULT_REST_PORT)
    @click.option('--teacher', 'teacher_uri', help="An Ursula URI to start learning from (seednode)", type=click.STRING)
    @click.option('--min-stake', help="The minimum stake the teacher must have to be a teacher", type=click.INT,
                  default=0)
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)
    return wrapper


@click.group()
def felix():
    """
    "Felix the Faucet" management commands.
    """
    pass


@felix.command()
@_admin_options
@click.option('--config-root', help="Custom configuration directory", type=click.Path())
@click.option('--discovery-port', help="The host port to run Felix Node Discovery services on", type=NETWORK_PORT, default=FelixConfiguration.DEFAULT_LEARNER_PORT)
@nucypher_click_config
def init(click_config,

         # Admin Options
         checksum_address, geth, dev, network, registry_filepath, provider_uri, host, db_filepath, poa,

         # Other
         config_root, discovery_port):
    """
    Create a brand-new Felix.
    """
    emitter = _setup_emitter(click_config, checksum_address)

    ETH_NODE = NO_BLOCKCHAIN_CONNECTION
    if geth:
        ETH_NODE = actions.get_provider_process(dev)
        provider_uri = ETH_NODE.provider_uri

    if not config_root:  # Flag
        config_root = DEFAULT_CONFIG_ROOT  # Envvar or init-only default

    try:
        new_felix_config = FelixConfiguration.generate(password=get_nucypher_password(confirm=True),
                                                       config_root=config_root,
                                                       rest_host=host,
                                                       rest_port=discovery_port,
                                                       db_filepath=db_filepath,
                                                       domains={network} if network else None,
                                                       checksum_address=checksum_address,
                                                       registry_filepath=registry_filepath,
                                                       provider_uri=provider_uri,
                                                       provider_process=ETH_NODE,
                                                       poa=poa)
    except Exception as e:
        if click_config.debug:
            raise
        else:
            emitter.echo(str(e), color='red', bold=True)
            raise click.Abort

    # Paint Help
    painting.paint_new_installation_help(emitter, new_configuration=new_felix_config)


@felix.command()
@_admin_options
@click.option('--config-file', help="Path to configuration file", type=EXISTING_READABLE_FILE)
@click.option('--port', help="The host port to run Felix HTTP services on", type=NETWORK_PORT, default=FelixConfiguration.DEFAULT_REST_PORT)
@click.option('--force', help="Don't ask for confirmation", is_flag=True)
@nucypher_click_config
def destroy(click_config,

            # Admin Options
            checksum_address, geth, dev, network, registry_filepath, provider_uri, host, db_filepath, poa,

            # Other
            config_file, port, force):
    """
    Destroy Felix Configuration.
    """
    emitter = _setup_emitter(click_config, checksum_address)

    ETH_NODE = NO_BLOCKCHAIN_CONNECTION
    if geth:
        ETH_NODE = actions.get_provider_process(dev)
        provider_uri = ETH_NODE.provider_uri

    felix_config = _get_config(emitter, network, config_file, registry_filepath, ETH_NODE, provider_uri, host, port, db_filepath, poa)
    actions.destroy_configuration(emitter, character_config=felix_config, force=force)


@felix.command()
@_api_options
@click.option('--force', help="Don't ask for confirmation", is_flag=True)
@nucypher_click_config
def createdb(click_config,

             # API Options
             checksum_address, geth, dev, network, registry_filepath, provider_uri, host, db_filepath, poa,
             config_file, port, teacher_uri, min_stake,

             # Other
             force):
    """
    Create Felix DB.
    """
    emitter = _setup_emitter(click_config, checksum_address)

    ETH_NODE = NO_BLOCKCHAIN_CONNECTION
    if geth:
        ETH_NODE = actions.get_provider_process(dev)
        provider_uri = ETH_NODE.provider_uri

    felix_config = _get_config(emitter, network, config_file, registry_filepath, ETH_NODE, provider_uri, host, port,
                               db_filepath, poa)
    FELIX = _create_felix(emitter, click_config, felix_config, teacher_uri, min_stake, network)

    if os.path.isfile(FELIX.db_filepath):
        if not force:
            click.confirm("Overwrite existing database?", abort=True)
        os.remove(FELIX.db_filepath)
        emitter.echo(f"Destroyed existing database {FELIX.db_filepath}")

    FELIX.create_tables()
    emitter.echo(f"\nCreated new database at {FELIX.db_filepath}", color='green')


@felix.command()
@_api_options
@nucypher_click_config
def view(click_config,

         # API Options
         checksum_address, geth, dev, network, registry_filepath, provider_uri, host, db_filepath, poa,
         config_file, port, teacher_uri, min_stake):
    """
    View Felix token balance.
    """
    emitter = _setup_emitter(click_config, checksum_address)

    ETH_NODE = NO_BLOCKCHAIN_CONNECTION
    if geth:
        ETH_NODE = actions.get_provider_process(dev)
        provider_uri = ETH_NODE.provider_uri

    felix_config = _get_config(emitter, network, config_file, registry_filepath, ETH_NODE, provider_uri, host, port,
                               db_filepath, poa)
    FELIX = _create_felix(emitter, click_config, felix_config, teacher_uri, min_stake, network)

    token_balance = FELIX.token_balance
    eth_balance = FELIX.eth_balance
    emitter.echo(f"""
        Address .... {FELIX.checksum_address}
        NU ......... {str(token_balance)}
        ETH ........ {str(eth_balance)}
    """)


@felix.command()
@_api_options
@nucypher_click_config
def accounts(click_config,

             # API Options
             checksum_address, geth, dev, network, registry_filepath, provider_uri, host, db_filepath, poa,
             config_file, port, teacher_uri, min_stake):
    """
    View Felix known accounts.
    """
    emitter = _setup_emitter(click_config, checksum_address)

    ETH_NODE = NO_BLOCKCHAIN_CONNECTION
    if geth:
        ETH_NODE = actions.get_provider_process(dev)
        provider_uri = ETH_NODE.provider_uri

    felix_config = _get_config(emitter, network, config_file, registry_filepath, ETH_NODE, provider_uri, host, port,
                               db_filepath, poa)
    FELIX = _create_felix(emitter, click_config, felix_config, teacher_uri, min_stake, network)

    accounts = FELIX.blockchain.client.accounts
    for account in accounts:
        emitter.echo(account)


@felix.command()
@_api_options
@click.option('--dry-run', '-x', help="Execute normally without actually starting the node", is_flag=True, default=False)
@nucypher_click_config
def run(click_config,

        # API Options
        checksum_address, geth, dev, network, registry_filepath, provider_uri, host, db_filepath, poa,
        config_file, port, teacher_uri, min_stake,

        # Other
        dry_run):
    """
    Run Felix service.
    """
    emitter = _setup_emitter(click_config, checksum_address)

    ETH_NODE = NO_BLOCKCHAIN_CONNECTION
    if geth:
        ETH_NODE = actions.get_provider_process(dev)
        provider_uri = ETH_NODE.provider_uri

    felix_config = _get_config(emitter, network, config_file, registry_filepath, ETH_NODE, provider_uri, host, port,
                               db_filepath, poa)
    FELIX = _create_felix(emitter, click_config, felix_config, teacher_uri, min_stake, network)

    emitter.echo("Waiting for blockchain sync...", color='yellow')
    emitter.message(f"Running Felix on {host}:{port}")
    FELIX.start(host=host,
                port=port,
                web_services=not dry_run,
                distribution=True,
                crash_on_error=click_config.debug)


def _create_felix(emitter, click_config, felix_config, teacher_uri, min_stake, network):
    try:
        # Authenticate
        unlock_nucypher_keyring(emitter,
                                character_configuration=felix_config,
                                password=get_nucypher_password(confirm=False))

        # Produce Teacher Ursulas
        teacher_nodes = actions.load_seednodes(emitter,
                                               teacher_uris=[teacher_uri] if teacher_uri else None,
                                               min_stake=min_stake,
                                               federated_only=felix_config.federated_only,
                                               network_domains=felix_config.domains,
                                               network_middleware=click_config.middleware)

        # Produce Felix
        FELIX = felix_config.produce(domains=network, known_nodes=teacher_nodes)
        FELIX.make_web_app()  # attach web application, but dont start service

        return FELIX
    except Exception as e:
        if click_config.debug:
            raise
        else:
            emitter.echo(str(e), color='red', bold=True)
            raise click.Abort


def _get_config(emitter, network, config_file, registry_filepath, eth_node, provider_uri, host, port, db_filepath, poa):
    # Domains -> bytes | or default
    domains = [network] if network else None

    # Load Felix from Configuration File with overrides
    try:
        felix_config = FelixConfiguration.from_configuration_file(filepath=config_file,
                                                                  domains=domains,
                                                                  registry_filepath=registry_filepath,
                                                                  provider_process=eth_node,
                                                                  provider_uri=provider_uri,
                                                                  rest_host=host,
                                                                  rest_port=port,
                                                                  db_filepath=db_filepath,
                                                                  poa=poa)

        return felix_config
    except FileNotFoundError:
        emitter.echo(f"No Felix configuration file found at {config_file}. "
                     f"Check the filepath or run 'nucypher felix init' to create a new system configuration.")
        raise click.Abort


def _setup_emitter(click_config, checksum_address):
    emitter = click_config.emitter

    # Intro
    emitter.clear()
    emitter.banner(FELIX_BANNER.format(checksum_address or ''))

    return emitter
