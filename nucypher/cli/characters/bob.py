from base64 import b64encode

import click

from nucypher.cli import actions, painting
from nucypher.cli.config import nucypher_click_config
from nucypher.cli.painting import paint_configuration
from nucypher.cli.types import NETWORK_PORT, EXISTING_READABLE_FILE
from nucypher.config.characters import BobConfiguration
from nucypher.config.constants import GLOBAL_DOMAIN
from nucypher.crypto.powers import DecryptingPower


@click.command()
@click.argument('action')
@click.option('--teacher-uri', help="An Ursula URI to start learning from (seednode)", type=click.STRING)
@click.option('--quiet', '-Q', help="Disable logging", is_flag=True)
@click.option('--min-stake', help="The minimum stake the teacher must have to be a teacher", type=click.INT, default=0)
@click.option('--discovery-port', help="The host port to run node discovery services on", type=NETWORK_PORT, default=6151)  # TODO
@click.option('--http-port', help="The host port to run Moe HTTP services on", type=NETWORK_PORT, default=11151)  # TODO
@click.option('--federated-only', '-F', help="Connect only to federated nodes", is_flag=True)
@click.option('--network', help="Network Domain Name", type=click.STRING)
@click.option('--config-root', help="Custom configuration directory", type=click.Path())
@click.option('--config-file', help="Path to configuration file", type=EXISTING_READABLE_FILE)
@click.option('--provider-uri', help="Blockchain provider's URI", type=click.STRING)
@click.option('--registry-filepath', help="Custom contract registry filepath", type=EXISTING_READABLE_FILE)
@click.option('--label', help="The label for a policy", type=click.STRING)
@click.option('--dev', '-d', help="Enable development mode", is_flag=True)
@click.option('--force', help="Don't ask for confirmation", is_flag=True)
@click.option('--dry-run', '-x', help="Execute normally without actually starting the node", is_flag=True)
@click.option('--policy-encrypting-key', help="Encrypting Public Key for Policy as hexidecimal string", type=click.STRING)
@click.option('--alice-encrypting-key', help="Alice's encrypting key as a hexideicmal string", type=click.STRING)
@nucypher_click_config
def bob(click_config,
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
        label,
        policy_encrypting_key,
        alice_encrypting_key):
    """
    Start and manage a "Bob" character.
    """

    if action == 'init':
        """Create a brand-new persistent Bob"""

        if dev and not quiet:
            click.secho("WARNING: Using temporary storage area", fg='yellow')

        if not config_root:                         # Flag
            config_root = click_config.config_file  # Envvar

        new_bob_config = BobConfiguration.generate(password=click_config.get_password(confirm=True),
                                                   config_root=config_root,
                                                   rest_host="localhost",
                                                   domains={network} if network else None,
                                                   federated_only=federated_only,
                                                   no_registry=True,  # Yes we have no registry,
                                                   registry_filepath=registry_filepath,
                                                   provider_uri=provider_uri,
                                                   )

        if not quiet:
            painting.paint_new_installation_help(new_configuration=new_bob_config)
            return  # FIN

        else:
            click.secho("OK")

    elif action == "destroy":
        """Delete all configuration files from the disk"""

        if dev:
            message = "'nucypher ursula destroy' cannot be used in --dev mode"
            raise click.BadOptionUsage(option_name='--dev', message=message)

        actions.destroy_system_configuration(config_class=BobConfiguration,
                                             config_file=config_file,
                                             network=network,
                                             config_root=config_root,
                                             force=force)
        if not quiet:
            click.secho("Destroyed {}".format(config_root))
        return

    #
    # Get Bob Configuration
    #

    if dev:
        bob_config = BobConfiguration(dev_mode=True,
                                      domains={network},
                                      provider_uri=provider_uri,
                                      federated_only=True,
                                      )
    else:
        bob_config = BobConfiguration.from_configuration_file(
            filepath=config_file,
            domains={network or GLOBAL_DOMAIN},
            rest_port=discovery_port,
            provider_uri=provider_uri)

    # Teacher Ursula
    teacher_uris = [teacher_uri] if teacher_uri else list()
    teacher_nodes = actions.load_seednodes(teacher_uris=teacher_uris,
                                           min_stake=min_stake,
                                           federated_only=federated_only)

    # Produce
    BOB = bob_config(known_nodes=teacher_nodes)

    if action == "run":

        if not dev:
            actions.unlock_keyring(configuration=bob_config, password=click_config.get_password())

        click.secho(f"Bob Verifying Key {bytes(BOB.stamp).hex()}", fg="green", bold=True)
        click.secho(f"Bob Encrypting Key {bytes(BOB.public_keys(DecryptingPower)).hex()}", fg="blue", bold=True)
        BOB.control.start_wsgi_control(dry_run=dry_run, http_port=http_port)

    elif action == "view":
        """Paint an existing configuration to the console"""
        json_config = BobConfiguration._read_configuration_file(filepath=config_file or bob_config.config_file_location)
        paint_configuration(json_config=json_config)
        return json_config

    elif action == "retrieve":

        bob_request_data = {
            'label': b64encode(label).decode(),
            'policy_encrypting_pubkey': policy_encrypting_key,
            'alice_signing_pubkey': alice_encrypting_key,
            # 'message_kit': b64encode(bob_message_kit.to_bytes()).decode(),  # TODO
        }

        response = BOB.control.retrieve(request=bob_request_data)
        click.secho(response)
        return response

    else:
        raise click.BadArgumentUsage(f"No such argument {action}")
