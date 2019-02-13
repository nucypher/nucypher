import click
import os

from nacl.exceptions import CryptoError

from nucypher.cli.config import nucypher_click_config
from nucypher.cli.types import NETWORK_PORT, EXISTING_READABLE_FILE
from nucypher.characters.lawful import Ursula
from nucypher.config.characters import AliceConfiguration
from nucypher import network
from nucypher.config.constants import GLOBAL_DOMAIN
from nucypher.network import character_control


@click.command()
@click.argument('action')
@click.option('--teacher-uri', help="An Ursula URI to start learning from (seednode)", type=click.STRING)
@click.option('--quiet', '-Q', help="Disable logging", is_flag=True)
@click.option('--min-stake', help="The minimum stake the teacher must have to be a teacher", type=click.INT, default=0)
@click.option('--rest-port', help="The host port to run Alice's character control service on", type=NETWORK_PORT)
@click.option('--federated-only', '-F', help="Connect only to federated nodes", is_flag=True)
@click.option('--network', help="Network Domain Name", type=click.STRING)
@click.option('--config-root', help="Custom configuration directory", type=click.Path())
@click.option('--config-file', help="Path to configuration file", type=EXISTING_READABLE_FILE)
@click.option('--provider-uri', help="Blockchain provider's URI", type=click.STRING)
@click.option('--registry-filepath', help="Custom contract registry filepath", type=EXISTING_READABLE_FILE)
@click.option('--dev', '-d', help="Enable development mode", is_flag=True)
@click.option('--dry-run', '-x', help="Execute normally without actually starting the node", is_flag=True)
@nucypher_click_config
def alice(click_config,
          action,
          quiet,
          teacher_uri,
          min_stake,
          rest_port,
          federated_only,
          network,
          config_root,
          config_file,
          provider_uri,
          registry_filepath,
          dev,
          dry_run):

    if action == 'init':
        """Create a brand-new persistent Alice"""

        if dev and not quiet:
            click.secho("WARNING: Using temporary storage area", fg='yellow')

        if not config_root:                         # Flag
            config_root = click_config.config_file  # Envvar

        alice_config = AliceConfiguration.generate(password=click_config.get_password(confirm=True),
                                                     config_root=config_root,
                                                     rest_host="localhost",
                                                     domains={network} if network else None,
                                                     federated_only=True,
                                                     no_registry=True,  # Yes we have no registry
                                                     provider_uri=provider_uri,
                                                     )

        if not quiet:
            click.secho("Generated keyring {}".format(alice_config.keyring_dir), fg='green')
            click.secho("Saved configuration file {}".format(alice_config.config_file_location), fg='green')

            # Give the use a suggestion as to what to do next...
            how_to_run_message = "\nTo run an Alice node from the default configuration filepath run: \n\n'{}'\n"
            suggested_command = 'nucypher alice run'
            if config_root is not None:
                config_file_location = os.path.join(config_root, config_file or AliceConfiguration.CONFIG_FILENAME)
                suggested_command += ' --config-file {}'.format(config_file_location)
            click.secho(how_to_run_message.format(suggested_command), fg='green')
            return  # FIN

        else:
            click.secho("OK")

    if action == "run":
        if dev:
            alice_config = AliceConfiguration(dev_mode=True,
                                              domains={network},
                                              provider_uri=provider_uri,
                                              federated_only=True,
                                              )
        else:
            alice_config = AliceConfiguration.from_configuration_file(
                                            filepath=config_file,
                                            domains={network or GLOBAL_DOMAIN},
                                            rest_port=rest_port,
                                            provider_uri=provider_uri)

                                           # TODO: Handle boolean overrides
                                           # federated_only=federated_only

        try:
            click.secho("Decrypting keyring...", fg='blue')
            alice_config.keyring.unlock(password=click_config.get_password())
        except CryptoError:
            raise alice_config.keyring.AuthenticationFailed
        finally:
            click_config.alice_config = alice_config

        teacher_nodes = list()
        if teacher_uri:
            teacher_node = Ursula.from_teacher_uri(teacher_uri=teacher_uri,
                                                   min_stake=min_stake,
                                                   federated_only=alice_config.federated_only)
            teacher_nodes.append(teacher_node)

        drone_alice = alice_config(known_nodes=teacher_nodes)
        alice_control = Alice.make_wsgi_app(alice, teacher_node)

        if dry_run:
            return

        alice.get_deployer().run()

        pass
    else:
        raise click.BadArgumentUsage(f"No such argument {action}")
