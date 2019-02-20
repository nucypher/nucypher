import datetime
import os

import click
import maya
from hendrix.deploy.base import HendrixDeploy
from nacl.exceptions import CryptoError

from nucypher.characters.lawful import Ursula, Bob
from nucypher.cli.actions import destroy_system_configuration
from nucypher.cli.config import nucypher_click_config
from nucypher.cli.painting import paint_configuration
from nucypher.cli.types import NETWORK_PORT, EXISTING_READABLE_FILE
from nucypher.config.characters import AliceConfiguration
from nucypher.config.constants import GLOBAL_DOMAIN
from nucypher.crypto.powers import SigningPower, DecryptingPower

ALICE_BANNER = r"""

    / \  | (_) ___ ___
   / _ \ | | |/ __/ _ \
  / ___ \| | | (_|  __/
 /_/   \_|_|_|\___\___|

 the Authority.

"""


@click.command()
@click.argument('action')
@click.option('--teacher-uri', help="An Ursula URI to start learning from (seednode)", type=click.STRING)
@click.option('--quiet', '-Q', help="Disable logging", is_flag=True)
@click.option('--min-stake', help="The minimum stake the teacher must have to be a teacher", type=click.INT, default=0)
@click.option('--discovery-port', help="The host port to run node discovery services on", type=NETWORK_PORT, default=9151)  # TODO
@click.option('--http-port', help="The host port to run Moe HTTP services on", type=NETWORK_PORT, default=8151)  # TODO
@click.option('--federated-only', '-F', help="Connect only to federated nodes", is_flag=True)
@click.option('--network', help="Network Domain Name", type=click.STRING)
@click.option('--config-root', help="Custom configuration directory", type=click.Path())
@click.option('--config-file', help="Path to configuration file", type=EXISTING_READABLE_FILE)
@click.option('--provider-uri', help="Blockchain provider's URI", type=click.STRING)
@click.option('--registry-filepath', help="Custom contract registry filepath", type=EXISTING_READABLE_FILE)
@click.option('--bob-encrypting-key', help="Bob's encrypting key as a hexideicmal string", type=click.STRING)
@click.option('--bob-verifying-key', help="Bob's verifying key as a hexideicmal string", type=click.STRING)
@click.option('--label', help="The label for a policy", type=click.STRING)
@click.option('--m', help="M", type=click.INT)
@click.option('--n', help="N", type=click.INT)
@click.option('--dev', '-d', help="Enable development mode", is_flag=True)
@click.option('--force', help="Don't ask for confirmation", is_flag=True)
@click.option('--dry-run', '-x', help="Execute normally without actually starting the node", is_flag=True)
@nucypher_click_config
def alice(click_config,
          action,
          quiet,
          teacher_uri,
          min_stake,
          http_port,
          discovery_port,
          federated_only,
          network,
          config_root,
          config_file,
          provider_uri,
          registry_filepath,
          dev,
          force,
          dry_run,
          bob_encrypting_key,
          bob_verifying_key,
          label,
          m,
          n):

    """
    Start and manage an "Alice" character.
    """

    if not quiet:
        click.secho(ALICE_BANNER)

    if action == 'init':
        """Create a brand-new persistent Alice"""

        if not network:
            raise click.BadArgumentUsage('--network is required to initialize a new configuration.')

        if dev and not quiet:
            click.secho("WARNING: Using temporary storage area", fg='yellow')

        if not config_root:                         # Flag
            config_root = click_config.config_file  # Envvar

        alice_config = AliceConfiguration.generate(password=click_config.get_password(confirm=True),
                                                   config_root=config_root,
                                                   rest_host="localhost",
                                                   domains={network} if network else None,
                                                   federated_only=federated_only,
                                                   no_registry=True,  # Yes we have no registry,
                                                   registry_filepath=registry_filepath,
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

    elif action == "destroy":
        """Delete all configuration files from the disk"""

        if dev:
            message = "'nucypher ursula destroy' cannot be used in --dev mode"
            raise click.BadOptionUsage(option_name='--dev', message=message)

        destroy_system_configuration(config_class=AliceConfiguration,
                                     config_file=config_file,
                                     network=network,
                                     config_root=config_root,
                                     force=force)
        if not quiet:
            click.secho("Destroyed {}".format(config_root))
        return

    #
    # Get Alice Configuration
    #

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
            rest_port=discovery_port,
            provider_uri=provider_uri)

    # Teacher
    teacher_nodes = list()
    if teacher_uri:
        teacher_node = Ursula.from_teacher_uri(teacher_uri=teacher_uri,
                                               min_stake=min_stake,
                                               federated_only=alice_config.federated_only)
        teacher_nodes.append(teacher_node)

    if not dev:
        # Keyring
        try:
            click.secho("Decrypting keyring...", fg='blue')
            alice_config.keyring.unlock(password=click_config.get_password())
        except CryptoError:
            raise alice_config.keyring.AuthenticationFailed
        finally:
            click_config.alice_config = alice_config

    # Produce
    ALICE = alice_config(known_nodes=teacher_nodes)

    if action == "run":

        # Alice Control
        alice_control = ALICE.make_wsgi_app()
        click.secho("Starting Alice Character Control...")

        click.secho(f"Alice Verifying Key {bytes(ALICE.stamp).hex()}", fg="green", bold=True)

        # Run
        if dry_run:
            return

        hx_deployer = HendrixDeploy(action="start", options={"wsgi": alice_control, "http_port": http_port})
        hx_deployer.run()  # <--- Blocking Call to Reactor

    elif action == "view":
        """Paint an existing configuration to the console"""
        paint_configuration(config_filepath=config_file or alice_config.config_file_location)
        return

    elif action == "create-policy":
        if not all((bob_verifying_key, bob_encrypting_key, label)):
            raise click.BadArgumentUsage(message="--bob-verifying-key, --bob-encrypting-key, and --label are "
                                                 "required options to create a new policy.")

        bob = Bob.from_public_keys({SigningPower: bob_verifying_key, DecryptingPower: bob_encrypting_key})
        policy = ALICE.create_policy(bob=bob, label=bytes(label, encoding='utf-8'), m=m, n=n)

        click.secho(policy.public_key.hex())
        return

    elif action == "derive-policy":
        if not label:
            raise click.BadArgumentUsage("--label is required to derive a new policy from a label.")
        policy = ALICE.get_policy_pubkey_from_label(bytes(label, encoding='utf-8'))
        click.secho(f"Created new Policy with label {label} | {bytes(policy).hex()}", fg='green')

    elif action == "grant":
        # 'expiration_time': ().iso8601(),  # TODO

        bob = Bob.from_public_keys({SigningPower: bytes.fromhex(bob_verifying_key),
                                    DecryptingPower: bytes.fromhex(bob_encrypting_key)})

        expiry = maya.now() + datetime.timedelta(days=3)  # TODO: Default expiration configuration
        policy = ALICE.grant(bob=bob, label=bytes(label, encoding='utf-8'),
                             m=m, n=n, expiration=expiry)
        click.secho(policy)
        return

    elif action == "revoke":
        raise NotImplementedError  # TODO

    else:
        raise click.BadArgumentUsage(f"No such argument {action}")
