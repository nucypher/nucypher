import os

import click
from constant_sorrow.constants import NO_BLOCKCHAIN_CONNECTION

from nucypher.characters.banners import FELIX_BANNER
from nucypher.cli import actions, painting
from nucypher.cli.actions import get_nucypher_password, unlock_nucypher_keyring, get_client_password
from nucypher.cli.config import group_general_config
from nucypher.cli.options import (
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
    option_middleware,
    option_min_stake,
    option_network,
    option_poa,
    option_provider_uri,
    option_registry_filepath,
    option_teacher_uri,
)
from nucypher.cli.types import NETWORK_PORT
from nucypher.config.characters import FelixConfiguration
from nucypher.config.constants import DEFAULT_CONFIG_ROOT, NUCYPHER_ENVVAR_WORKER_ETH_PASSWORD

option_port = click.option('--port', help="The host port to run Felix HTTP services on", type=NETWORK_PORT, default=FelixConfiguration.DEFAULT_REST_PORT)


class FelixConfigOptions:

    __option_name__ = 'config_options'

    def __init__(
            self, geth, dev, network, provider_uri, host,
            db_filepath, checksum_address, registry_filepath, poa, port):

        eth_node = NO_BLOCKCHAIN_CONNECTION
        if geth:
            eth_node = actions.get_provider_process(dev)
            provider_uri = eth_node.provider_uri

        self.eth_node = eth_node
        self.provider_uri = provider_uri
        self.domains = {network} if network else None
        self.dev = dev
        self.host = host
        self.db_filepath = db_filepath
        self.checksum_address = checksum_address
        self.registry_filepath = registry_filepath
        self.poa = poa
        self.port = port

    def create_config(self, emitter, config_file):
        # Load Felix from Configuration File with overrides
        try:
            return FelixConfiguration.from_configuration_file(
                emitter=emitter,
                filepath=config_file,
                domains=self.domains,
                registry_filepath=self.registry_filepath,
                provider_process=self.eth_node,
                provider_uri=self.provider_uri,
                rest_host=self.host,
                rest_port=self.port,
                db_filepath=self.db_filepath,
                poa=self.poa)
        except FileNotFoundError:
            return actions.handle_missing_configuration_file(
                character_config_class=FelixConfiguration,
                config_file=config_file)

    def generate_config(self, config_root, discovery_port):
        return FelixConfiguration.generate(
            password=get_nucypher_password(confirm=True),
            config_root=config_root,
            rest_host=self.host,
            rest_port=discovery_port,
            db_filepath=self.db_filepath,
            domains=self.domains,
            checksum_address=self.checksum_address,
            registry_filepath=self.registry_filepath,
            provider_uri=self.provider_uri,
            provider_process=self.eth_node,
            poa=self.poa)


group_config_options = group_options(
    FelixConfigOptions,
    geth=option_geth,
    dev=option_dev,
    network=option_network,
    provider_uri=option_provider_uri(),
    host=click.option('--host', help="The host to run Felix HTTP services on", type=click.STRING, default='127.0.0.1'),
    db_filepath=option_db_filepath,
    checksum_address=option_checksum_address,
    registry_filepath=option_registry_filepath,
    poa=option_poa,
    port=option_port,
    )


class FelixCharacterOptions:

    __option_name__ = 'character_options'

    def __init__(self, config_options, teacher_uri, min_stake, middleware):
        self.config_options = config_options
        self.teacher_uris = [teacher_uri] if teacher_uri else None
        self.min_stake = min_stake
        self.middleware = middleware

    def create_character(self, emitter, config_file, debug):

        felix_config = self.config_options.create_config(emitter, config_file)

        try:
            # Authenticate
            unlock_nucypher_keyring(emitter,
                                    character_configuration=felix_config,
                                    password=get_nucypher_password(confirm=False))

            client_password = get_client_password(checksum_address=felix_config.checksum_address,
                                                  envvar=NUCYPHER_ENVVAR_WORKER_ETH_PASSWORD)

            # Produce Felix
            FELIX = felix_config.produce(domains=self.config_options.domains, client_password=client_password)
            FELIX.make_web_app()  # attach web application, but dont start service

            return FELIX
        except Exception as e:
            if debug:
                raise
            else:
                emitter.echo(str(e), color='red', bold=True)
                raise click.Abort


group_character_options = group_options(
    FelixCharacterOptions,
    config_options=group_config_options,
    teacher_uri=option_teacher_uri,
    min_stake=option_min_stake,
    middleware=option_middleware,
    )


@click.group()
def felix():
    """
    "Felix the Faucet" management commands.
    """
    pass


@felix.command()
@group_general_config
@option_config_root
@option_discovery_port(default=FelixConfiguration.DEFAULT_LEARNER_PORT)
@group_config_options
def init(general_config, config_options, config_root, discovery_port):
    """
    Create a brand-new Felix.
    """
    emitter = _setup_emitter(general_config, config_options.checksum_address)

    if not config_root:  # Flag
        config_root = DEFAULT_CONFIG_ROOT  # Envvar or init-only default

    try:
        new_felix_config = config_options.generate_config(config_root, discovery_port)
    except Exception as e:
        if general_config.debug:
            raise
        else:
            emitter.echo(str(e), color='red', bold=True)
            raise click.Abort

    # Paint Help
    painting.paint_new_installation_help(emitter, new_configuration=new_felix_config)


@felix.command()
@group_config_options
@option_config_file
@option_force
@group_general_config
def destroy(general_config, config_options, config_file, force):
    """
    Destroy Felix Configuration.
    """
    emitter = _setup_emitter(general_config, config_options.checksum_address)
    felix_config = config_options.create_config(emitter, config_file)
    actions.destroy_configuration(emitter, character_config=felix_config, force=force)


@felix.command()
@group_character_options
@option_config_file
@option_force
@group_general_config
def createdb(general_config, character_options, config_file, force):
    """
    Create Felix DB.
    """
    emitter = _setup_emitter(general_config, character_options.config_options.checksum_address)

    FELIX = character_options.create_character(emitter, config_file, general_config.debug)

    if os.path.isfile(FELIX.db_filepath):
        if not force:
            click.confirm("Overwrite existing database?", abort=True)
        os.remove(FELIX.db_filepath)
        emitter.echo(f"Destroyed existing database {FELIX.db_filepath}")

    FELIX.create_tables()
    emitter.echo(f"\nCreated new database at {FELIX.db_filepath}", color='green')


@felix.command()
@group_character_options
@option_config_file
@group_general_config
def view(general_config, character_options, config_file):
    """
    View Felix token balance.
    """
    emitter = _setup_emitter(general_config, character_options.config_options.checksum_address)

    FELIX = character_options.create_character(emitter, config_file, general_config.debug)

    token_balance = FELIX.token_balance
    eth_balance = FELIX.eth_balance
    emitter.echo(f"""
        Address .... {FELIX.checksum_address}
        NU ......... {str(token_balance)}
        ETH ........ {str(eth_balance)}
    """)


@felix.command()
@group_character_options
@option_config_file
@group_general_config
def accounts(general_config, character_options, config_file):
    """
    View Felix known accounts.
    """
    emitter = _setup_emitter(general_config, character_options.config_options.checksum_address)

    FELIX = character_options.create_character(emitter, config_file, general_config.debug)

    accounts = FELIX.blockchain.client.accounts
    for account in accounts:
        emitter.echo(account)


@felix.command()
@group_character_options
@option_config_file
@option_dry_run
@group_general_config
def run(general_config, character_options, config_file, dry_run):
    """
    Run Felix service.
    """
    emitter = _setup_emitter(general_config, character_options.config_options.checksum_address)

    FELIX = character_options.create_character(emitter, config_file, general_config.debug)

    host = character_options.config_options.host
    port = character_options.config_options.port
    emitter.echo("Waiting for blockchain sync...", color='yellow')
    emitter.message(f"Running Felix on {host}:{port}")
    FELIX.start(host=host,
                port=port,
                web_services=not dry_run,
                distribution=True,
                crash_on_error=general_config.debug)


def _setup_emitter(general_config, checksum_address):
    emitter = general_config.emitter

    # Intro
    emitter.clear()
    emitter.banner(FELIX_BANNER.format(checksum_address or ''))

    return emitter
