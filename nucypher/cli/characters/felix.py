import os

import click
from constant_sorrow.constants import NO_BLOCKCHAIN_CONNECTION

from nucypher.blockchain.eth.clients import NuCypherGethDevnetProcess
from nucypher.characters.banners import FELIX_BANNER
from nucypher.cli import actions, painting
from nucypher.cli.config import nucypher_click_config
from nucypher.cli.types import NETWORK_PORT, EXISTING_READABLE_FILE, EIP55_CHECKSUM_ADDRESS
from nucypher.config.characters import FelixConfiguration
from nucypher.config.constants import DEFAULT_CONFIG_ROOT


@click.command()
@click.argument('action')
@click.option('--teacher-uri', help="An Ursula URI to start learning from (seednode)", type=click.STRING)
@click.option('--enode', help="An ethereum bootnode enode address to start learning from", type=click.STRING)
@click.option('--min-stake', help="The minimum stake the teacher must have to be a teacher", type=click.INT, default=0)
@click.option('--network', help="Network Domain Name", type=click.STRING)
@click.option('--host', help="The host to run Felix HTTP services on", type=click.STRING, default='127.0.0.1')
@click.option('--port', help="The host port to run Felix HTTP services on", type=NETWORK_PORT, default=FelixConfiguration.DEFAULT_REST_PORT)
@click.option('--discovery-port', help="The host port to run Felix Node Discovery services on", type=NETWORK_PORT, default=FelixConfiguration.DEFAULT_LEARNER_PORT)
@click.option('--dry-run', '-x', help="Execute normally without actually starting the node", is_flag=True, default=False)
@click.option('--provider-uri', help="Blockchain provider's URI", type=click.STRING)
@click.option('--geth', '-G', help="Run using the built-in geth node", is_flag=True)
@click.option('--config-root', help="Custom configuration directory", type=click.Path())
@click.option('--checksum-address', help="Run with a specified account", type=EIP55_CHECKSUM_ADDRESS)
@click.option('--poa', help="Inject POA middleware", is_flag=True, default=None)
@click.option('--config-file', help="Path to configuration file", type=EXISTING_READABLE_FILE)
@click.option('--db-filepath', help="The database filepath to connect to", type=click.STRING)
@click.option('--no-registry', help="Skip importing the default contract registry", is_flag=True)
@click.option('--registry-filepath', help="Custom contract registry filepath", type=EXISTING_READABLE_FILE)
@click.option('--force', help="Don't ask for confirmation", is_flag=True)
@click.option('--dev', '-d', help="Enable development mode", is_flag=True)
@nucypher_click_config
def felix(click_config,
          action,
          teacher_uri,
          enode,
          min_stake,
          network,
          host,
          dry_run,
          port,
          discovery_port,
          provider_uri,
          geth,
          config_root,
          checksum_address,
          poa,
          config_file,
          db_filepath,
          no_registry,
          registry_filepath,
          dev,
          force):

    # Intro
    click.clear()
    if not click_config.quiet:
        click.secho(FELIX_BANNER.format(checksum_address or ''))

    ETH_NODE = NO_BLOCKCHAIN_CONNECTION
    if geth:
        ETH_NODE = actions.get_provider_process(dev=dev)
        provider_uri = ETH_NODE.provider_uri

    if action == "init":
        """Create a brand-new Felix"""

        if not config_root:                         # Flag
            config_root = DEFAULT_CONFIG_ROOT       # Envvar or init-only default

        # Acquire Keyring Password
        new_password = click_config.get_password(confirm=True)

        try:
            new_felix_config = FelixConfiguration.generate(password=new_password,
                                                           config_root=config_root,
                                                           rest_host=host,
                                                           rest_port=discovery_port,
                                                           db_filepath=db_filepath,
                                                           domains={network} if network else None,
                                                           checksum_address=checksum_address,
                                                           download_registry=not no_registry,
                                                           registry_filepath=registry_filepath,
                                                           provider_uri=provider_uri,
                                                           provider_process=ETH_NODE,
                                                           poa=poa)
        except Exception as e:
            if click_config.debug:
                raise
            else:
                click.secho(str(e), fg='red', bold=True)
                raise click.Abort

        # Paint Help
        painting.paint_new_installation_help(new_configuration=new_felix_config)

        return  # <-- do not remove (conditional flow control)

    # Domains -> bytes | or default
    domains = [network] if network else None

    # Load Felix from Configuration File with overrides
    try:
        felix_config = FelixConfiguration.from_configuration_file(filepath=config_file,
                                                                  domains=domains,
                                                                  registry_filepath=registry_filepath,
                                                                  provider_process=ETH_NODE,
                                                                  provider_uri=provider_uri,
                                                                  rest_host=host,
                                                                  rest_port=port,
                                                                  db_filepath=db_filepath,
                                                                  poa=poa)

    except FileNotFoundError:
        click.secho(f"No Felix configuration file found at {config_file}. "
                    f"Check the filepath or run 'nucypher felix init' to create a new system configuration.")
        raise click.Abort

    try:

        # Connect to Blockchain
        felix_config.connect_to_blockchain()

        # Authenticate
        password = click_config.get_password(confirm=False)
        click_config.unlock_keyring(character_configuration=felix_config,
                                    password=password)



        # Produce Teacher Ursulas
        teacher_nodes = actions.load_seednodes(teacher_uris=[teacher_uri] if teacher_uri else None,
                                               min_stake=min_stake,
                                               federated_only=felix_config.federated_only,
                                               network_domains=felix_config.domains,
                                               network_middleware=click_config.middleware)
        
        # Add ETH Bootnode or Peer
        if enode:
            if geth:
                felix_config.blockchain.interface.w3.geth.admin.addPeer(enode)
                click.secho(f"Added ethereum peer {enode}")
            else:
                raise NotImplemented  # TODO: other backends

        # Produce Felix
        FELIX = felix_config.produce(domains=network, known_nodes=teacher_nodes)
        FELIX.make_web_app()  # attach web application, but dont start service

    except Exception as e:
        if click_config.debug:
            raise
        else:
            click.secho(str(e), fg='red', bold=True)
            raise click.Abort

    if action == "createdb":  # Initialize Database
        if os.path.isfile(FELIX.db_filepath):
            if not force:
                click.confirm("Overwrite existing database?", abort=True)
            os.remove(FELIX.db_filepath)
            click.secho(f"Destroyed existing database {FELIX.db_filepath}")

        FELIX.create_tables()
        click.secho(f"\nCreated new database at {FELIX.db_filepath}", fg='green')

    elif action == 'view':
        token_balance = FELIX.token_balance
        eth_balance = FELIX.eth_balance
        click.secho(f"""
Address .... {FELIX.checksum_address}
NU ......... {str(token_balance)}
ETH ........ {str(eth_balance)}
        """)

    elif action == "accounts":
        accounts = FELIX.blockchain.interface.w3.eth.accounts
        for account in accounts:
            click.secho(account)

    elif action == "destroy":
        """Delete all configuration files from the disk"""
        actions.destroy_configuration(character_config=felix_config, force=force)

    elif action == 'run':     # Start web services

        try:
            click.secho("Waiting for blockchain sync...", fg='yellow')
            FELIX.blockchain.sync()
            FELIX.start(host=host,
                        port=port,
                        web_services=not dry_run,
                        distribution=True,
                        crash_on_error=click_config.debug)
        finally:
            FELIX.blockchain.disconnect()

    else:
        raise click.BadArgumentUsage("No such argument {}".format(action))
