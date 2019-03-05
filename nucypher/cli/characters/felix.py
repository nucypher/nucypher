import click

from nucypher.cli import actions, painting
from nucypher.cli.config import nucypher_click_config
from nucypher.cli.types import NETWORK_PORT, EXISTING_READABLE_FILE, EIP55_CHECKSUM_ADDRESS
from nucypher.config.characters import FelixConfiguration


@click.command()
@click.argument('action')
@click.option('--teacher-uri', help="An Ursula URI to start learning from (seednode)", type=click.STRING)
@click.option('--min-stake', help="The minimum stake the teacher must have to be a teacher", type=click.INT, default=0)
@click.option('--network', help="Network Domain Name", type=click.STRING)
@click.option('--host', help="The host to run Felix HTTP services on", type=click.STRING, default='127.0.0.1')
@click.option('--port', help="The host port to run Felix HTTP services on", type=NETWORK_PORT, default=FelixConfiguration.DEFAULT_REST_PORT)
@click.option('--discovery-port', help="The host port to run Felix Node Discovery services on", type=NETWORK_PORT, default=FelixConfiguration.DEFAULT_LEARNER_PORT)
@click.option('--dry-run', '-x', help="Execute normally without actually starting the node", is_flag=True)
@click.option('--provider-uri', help="Blockchain provider's URI", type=click.STRING)
@click.option('--config-root', help="Custom configuration directory", type=click.Path())
@click.option('--checksum-address', help="Run with a specified account", type=EIP55_CHECKSUM_ADDRESS)
@click.option('--poa', help="Inject POA middleware", is_flag=True, default=False)
@click.option('--config-file', help="Path to configuration file", type=EXISTING_READABLE_FILE)
@click.option('--db-filepath', help="The database filepath to connect to", type=click.STRING)
@click.option('--no-registry', help="Skip importing the default contract registry", is_flag=True)
@click.option('--registry-filepath', help="Custom contract registry filepath", type=EXISTING_READABLE_FILE)
@nucypher_click_config
def felix(click_config,
          action,
          teacher_uri,
          min_stake,
          network,
          host,
          dry_run,
          port,
          discovery_port,
          provider_uri,
          config_root,
          checksum_address,
          poa,
          config_file,
          db_filepath,
          no_registry,
          registry_filepath):

    if action == "init":
        """Create a brand-new persistent Ursula"""

        if not network:
            raise click.BadArgumentUsage('--network is required to initialize a new configuration.')

        if not config_root:                         # Flag
            config_root = click_config.config_file  # Envvar

        ursula_config = FelixConfiguration.generate(password=click_config._get_password(confirm=True),
                                                    config_root=config_root,
                                                    rest_host=host,
                                                    rest_port=discovery_port,
                                                    db_filepath=db_filepath,
                                                    domains={network} if network else None,
                                                    checksum_public_address=checksum_address,
                                                    no_registry=no_registry,
                                                    registry_filepath=registry_filepath,
                                                    provider_uri=provider_uri,
                                                    poa=poa)

        painting.paint_new_installation_help(new_configuration=ursula_config,
                                             config_root=config_root,
                                             config_file=config_file)
        return

    elif action == 'run':

        # Domains -> bytes | or default
        domains = [bytes(network, encoding='utf-8')] if network else None

        # Load Ursula from Configuration File
        try:
            felix_config = FelixConfiguration.from_configuration_file(filepath=config_file,
                                                                      domains=domains,
                                                                      registry_filepath=registry_filepath,
                                                                      provider_uri=provider_uri,
                                                                      rest_host=host,
                                                                      rest_port=port,
                                                                      db_filepath=db_filepath,
                                                                      poa=poa)
        except FileNotFoundError:
            click.secho("No Felix Configuration File Found.")
            raise click.Abort

        # Teacher Ursula
        teacher_uris = [teacher_uri] if teacher_uri else list()
        teacher_nodes = actions.load_seednodes(teacher_uris=teacher_uris,
                                               min_stake=min_stake,
                                               federated_only=False,
                                               network_middleware=click_config.middleware)

        # Felix
        click_config.unlock_keyring(character_configuration=felix_config)
        FELIX = felix_config.produce(domains=network, known_nodes=teacher_nodes)

        # Start web services
        FELIX.make_web_app()
        FELIX.start(host=host, port=port, dry_run=dry_run)

    else:
        raise click.BadArgumentUsage("No such argument {}".format(action))
