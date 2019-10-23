import functools
import os

import click
from constant_sorrow.constants import NO_BLOCKCHAIN_CONNECTION

from nucypher.characters.banners import FELIX_BANNER
from nucypher.cli import actions, painting
from nucypher.cli.actions import get_nucypher_password, unlock_nucypher_keyring
from nucypher.cli.common_options import (
    group_options,
    option_checksum_address,
    option_config_file,
    option_config_root,
    option_db_filepath,
    option_dev,
    option_discovery_port,
    option_dry_run,
    option_force,
    option_geth,
    option_min_stake,
    option_network,
    option_poa,
    option_provider_uri,
    option_registry_filepath,
    option_teacher_uri,
    )
from nucypher.cli.config import group_general_config
from nucypher.cli.types import NETWORK_PORT, EXISTING_READABLE_FILE, EIP55_CHECKSUM_ADDRESS
from nucypher.config.characters import FelixConfiguration
from nucypher.config.constants import DEFAULT_CONFIG_ROOT


option_port = click.option('--port', help="The host port to run Felix HTTP services on", type=NETWORK_PORT,
                  default=FelixConfiguration.DEFAULT_REST_PORT)


# Args (checksum_address, geth, dev, network, registry_filepath,  provider_uri, host, db_filepath, poa)
group_admin = group_options(
    'admin',
    checksum_address=option_checksum_address,
    geth=option_geth,
    dev=option_dev,
    network=option_network,
    registry_filepath=option_registry_filepath,
    provider_uri=option_provider_uri(),
    host=click.option('--host', help="The host to run Felix HTTP services on", type=click.STRING, default='127.0.0.1'),
    db_filepath=option_db_filepath,
    poa=option_poa,
    )


# Args (config_file, port, teacher_uri)
group_api = group_options(
    'api',
    admin=group_admin,
    config_file=option_config_file,
    port=option_port,
    teacher_uri=option_teacher_uri,
    min_stake=option_min_stake,
    )


@click.group()
def felix():
    """
    "Felix the Faucet" management commands.
    """
    pass


@felix.command()
@group_admin
@option_config_root
@option_discovery_port(default=FelixConfiguration.DEFAULT_LEARNER_PORT)
@group_general_config
def init(general_config,

         # Admin Options
         admin,

         # Other
         config_root, discovery_port):
    """
    Create a brand-new Felix.
    """
    emitter = _setup_emitter(general_config, admin.checksum_address)

    ETH_NODE = NO_BLOCKCHAIN_CONNECTION
    provider_uri = admin.provider_uri
    if admin.geth:
        ETH_NODE = actions.get_provider_process(admin.dev)
        provider_uri = ETH_NODE.provider_uri

    if not config_root:  # Flag
        config_root = DEFAULT_CONFIG_ROOT  # Envvar or init-only default

    try:
        new_felix_config = FelixConfiguration.generate(password=get_nucypher_password(confirm=True),
                                                       config_root=config_root,
                                                       rest_host=admin.host,
                                                       rest_port=discovery_port,
                                                       db_filepath=admin.db_filepath,
                                                       domains={admin.network} if admin.network else None,
                                                       checksum_address=admin.checksum_address,
                                                       registry_filepath=admin.registry_filepath,
                                                       provider_uri=provider_uri,
                                                       provider_process=ETH_NODE,
                                                       poa=admin.poa)
    except Exception as e:
        if general_config.debug:
            raise
        else:
            emitter.echo(str(e), color='red', bold=True)
            raise click.Abort

    # Paint Help
    painting.paint_new_installation_help(emitter, new_configuration=new_felix_config)


@felix.command()
@group_admin
@option_config_file
@option_port
@option_force
@group_general_config
def destroy(general_config,

            # Admin Options
            admin,

            # Other
            config_file, port, force):
    """
    Destroy Felix Configuration.
    """
    emitter = _setup_emitter(general_config, admin.checksum_address)

    ETH_NODE = NO_BLOCKCHAIN_CONNECTION
    provider_uri = admin.provider_uri
    if admin.geth:
        ETH_NODE = actions.get_provider_process(admin.dev)
        provider_uri = ETH_NODE.provider_uri

    felix_config = _get_config(
        emitter, admin.network, config_file, admin.registry_filepath, ETH_NODE, provider_uri,
        admin.host, port, admin.db_filepath, admin.poa)
    actions.destroy_configuration(emitter, character_config=felix_config, force=force)


@felix.command()
@group_api
@option_force
@group_general_config
def createdb(general_config,

             # API Options
             api,

             # Other
             force):
    """
    Create Felix DB.
    """
    emitter = _setup_emitter(general_config, api.admin.checksum_address)

    admin = api.admin

    ETH_NODE = NO_BLOCKCHAIN_CONNECTION
    provider_uri = admin.provider_uri
    if api.admin.geth:
        ETH_NODE = actions.get_provider_process(admin.dev)
        provider_uri = ETH_NODE.provider_uri

    felix_config = _get_config(
        emitter, admin.network, api.config_file, admin.registry_filepath, ETH_NODE, provider_uri,
        admin.host, api.port, admin.db_filepath, admin.poa)
    FELIX = _create_felix(emitter, general_config, felix_config, api.teacher_uri, api.min_stake, admin.network)

    if os.path.isfile(FELIX.db_filepath):
        if not force:
            click.confirm("Overwrite existing database?", abort=True)
        os.remove(FELIX.db_filepath)
        emitter.echo(f"Destroyed existing database {FELIX.db_filepath}")

    FELIX.create_tables()
    emitter.echo(f"\nCreated new database at {FELIX.db_filepath}", color='green')


@felix.command()
@group_api
@group_general_config
def view(general_config,

         # API Options
         api
         ):
    """
    View Felix token balance.
    """
    emitter = _setup_emitter(general_config, api.admin.checksum_address)

    admin = api.admin

    ETH_NODE = NO_BLOCKCHAIN_CONNECTION
    provider_uri = admin.provider_uri
    if api.admin.geth:
        ETH_NODE = actions.get_provider_process(dev)
        provider_uri = ETH_NODE.provider_uri

    felix_config = _get_config(
        emitter, admin.network, api.config_file, admin.registry_filepath, ETH_NODE, provider_uri,
        admin.host, api.port, admin.db_filepath, admin.poa)
    FELIX = _create_felix(emitter, general_config, felix_config, api.teacher_uri, api.min_stake, admin.network)

    token_balance = FELIX.token_balance
    eth_balance = FELIX.eth_balance
    emitter.echo(f"""
        Address .... {FELIX.checksum_address}
        NU ......... {str(token_balance)}
        ETH ........ {str(eth_balance)}
    """)


@felix.command()
@group_api
@group_general_config
def accounts(general_config,

             # API Options
             api
             ):
    """
    View Felix known accounts.
    """
    emitter = _setup_emitter(general_config, api.admin.checksum_address)

    admin = api.admin

    ETH_NODE = NO_BLOCKCHAIN_CONNECTION
    provider_uri = admin.provider_uri
    if api.admin.geth:
        ETH_NODE = actions.get_provider_process(dev)
        provider_uri = ETH_NODE.provider_uri

    felix_config = _get_config(
        emitter, admin.network, api.config_file, admin.registry_filepath, ETH_NODE, provider_uri,
        admin.host, api.port, admin.db_filepath, admin.poa)
    FELIX = _create_felix(emitter, general_config, felix_config, api.teacher_uri, api.min_stake, admin.network)

    accounts = FELIX.blockchain.client.accounts
    for account in accounts:
        emitter.echo(account)


@felix.command()
@group_api
@option_dry_run
@group_general_config
def run(general_config,

        # API Options
        api,

        # Other
        dry_run):
    """
    Run Felix service.
    """
    emitter = _setup_emitter(general_config, api.admin.checksum_address)

    admin = api.admin

    ETH_NODE = NO_BLOCKCHAIN_CONNECTION
    provider_uri = admin.provider_uri
    if api.admin.geth:
        ETH_NODE = actions.get_provider_process(dev)
        provider_uri = ETH_NODE.provider_uri

    felix_config = _get_config(
        emitter, admin.network, api.config_file, admin.registry_filepath, ETH_NODE, provider_uri,
        admin.host, api.port, admin.db_filepath, admin.poa)
    FELIX = _create_felix(emitter, general_config, felix_config, api.teacher_uri, api.min_stake, admin.network)

    emitter.echo("Waiting for blockchain sync...", color='yellow')
    emitter.message(f"Running Felix on {admin.host}:{api.port}")
    FELIX.start(host=admin.host,
                port=api.port,
                web_services=not dry_run,
                distribution=True,
                crash_on_error=general_config.debug)


def _create_felix(emitter, general_config, felix_config, teacher_uri, min_stake, network):
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
                                               network_middleware=general_config.middleware)

        # Produce Felix
        FELIX = felix_config.produce(domains=network, known_nodes=teacher_nodes)
        FELIX.make_web_app()  # attach web application, but dont start service

        return FELIX
    except Exception as e:
        if general_config.debug:
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


def _setup_emitter(general_config, checksum_address):
    emitter = general_config.emitter

    # Intro
    emitter.clear()
    emitter.banner(FELIX_BANNER.format(checksum_address or ''))

    return emitter
