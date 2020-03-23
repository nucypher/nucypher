import click

from nucypher.characters.banners import BOB_BANNER
from nucypher.characters.control.interfaces import BobInterface
from nucypher.cli import actions, painting
from nucypher.cli.actions import get_nucypher_password, select_client_account, get_or_update_configuration
from nucypher.cli.commands.deploy import option_gas_strategy
from nucypher.cli.config import group_general_config
from nucypher.cli.options import (
    group_options,
    option_checksum_address,
    option_config_file,
    option_config_root,
    option_controller_port,
    option_dev,
    option_discovery_port,
    option_dry_run,
    option_federated_only,
    option_force,
    option_middleware,
    option_min_stake,
    option_network,
    option_provider_uri,
    option_registry_filepath,
    option_teacher_uri,
    option_signer_uri)
from nucypher.config.characters import BobConfiguration
from nucypher.crypto.powers import DecryptingPower
from nucypher.utilities.sandbox.constants import TEMPORARY_DOMAIN


class BobConfigOptions:

    __option_name__ = 'config_options'

    def __init__(self, provider_uri, network, registry_filepath, checksum_address, discovery_port,
                 dev, middleware, federated_only, gas_strategy, signer_uri):

        self.provider_uri = provider_uri
        self.signer_uri = signer_uri
        self.gas_strategy = gas_strategy,
        self.domains = {network} if network else None
        self.registry_filepath = registry_filepath
        self.checksum_address = checksum_address
        self.discovery_port = discovery_port
        self.dev = dev
        self.middleware = middleware
        self.federated_only = federated_only

    def create_config(self, emitter, config_file):
        if self.dev:
            return BobConfiguration(
                emitter=emitter,
                dev_mode=True,
                domains={TEMPORARY_DOMAIN},
                provider_uri=self.provider_uri,
                gas_strategy=self.gas_strategy,
                signer_uri=self.signer_uri,
                federated_only=True,
                checksum_address=self.checksum_address,
                network_middleware=self.middleware)
        else:
            try:
                return BobConfiguration.from_configuration_file(
                    emitter=emitter,
                    filepath=config_file,
                    domains=self.domains,
                    checksum_address=self.checksum_address,
                    rest_port=self.discovery_port,
                    provider_uri=self.provider_uri,
                    signer_uri=self.signer_uri,
                    gas_strategy=self.gas_strategy,
                    registry_filepath=self.registry_filepath,
                    network_middleware=self.middleware)
            except FileNotFoundError:
                return actions.handle_missing_configuration_file(
                    character_config_class=BobConfiguration,
                    config_file=config_file)

    def generate_config(self, emitter, config_root):

        checksum_address = self.checksum_address
        if not checksum_address and not self.federated_only:
            checksum_address = select_client_account(emitter=emitter,
                                                     provider_uri=self.provider_uri,
                                                     show_balances=False)

        return BobConfiguration.generate(
            password=get_nucypher_password(confirm=True),
            config_root=config_root,
            checksum_address=checksum_address,
            domains=self.domains,
            federated_only=self.federated_only,
            registry_filepath=self.registry_filepath,
            provider_uri=self.provider_uri,
            signer_uri=self.signer_uri,
            gas_strategy=self.gas_strategy,
        )

    def get_updates(self) -> dict:
        payload = dict(checksum_address=self.checksum_address,
                       domains=self.domains,
                       federated_only=self.federated_only,
                       registry_filepath=self.registry_filepath,
                       provider_uri=self.provider_uri,
                       signer_uri=self.signer_uri,
                       gas_strategy=self.gas_strategy
                       )
        # Depends on defaults being set on Configuration classes, filtrates None values
        updates = {k: v for k, v in payload.items() if v is not None}
        return updates


group_config_options = group_options(
    BobConfigOptions,
    provider_uri=option_provider_uri(),
    gas_strategy=option_gas_strategy,
    signer_uri=option_signer_uri,
    network=option_network,
    registry_filepath=option_registry_filepath,
    checksum_address=option_checksum_address,
    discovery_port=option_discovery_port(),
    dev=option_dev,
    middleware=option_middleware,
    federated_only=option_federated_only
    )


class BobCharacterOptions:

    __option_name__ = 'character_options'

    def __init__(self, config_options, teacher_uri, min_stake):
        self.config_options = config_options
        self.teacher_uri = teacher_uri
        self.min_stake = min_stake

    def create_character(self, emitter, config_file):
        config = self.config_options.create_config(emitter, config_file)

        return actions.make_cli_character(character_config=config,
                                          emitter=emitter,
                                          unlock_keyring=not self.config_options.dev,
                                          teacher_uri=self.teacher_uri,
                                          min_stake=self.min_stake)


group_character_options = group_options(
    BobCharacterOptions,
    config_options=group_config_options,
    teacher_uri=option_teacher_uri,
    min_stake=option_min_stake,
    )


@click.group()
def bob():
    """
    "Bob the Data Recipient" management commands.
    """
    pass


@bob.command()
@group_config_options
@option_federated_only
@option_config_root
@group_general_config
def init(general_config, config_options, config_root):
    """
    Create a brand new persistent Bob.
    """
    emitter = _setup_emitter(general_config)
    if not config_root:
        config_root = general_config.config_root
    new_bob_config = config_options.generate_config(emitter, config_root)
    return painting.paint_new_installation_help(emitter, new_configuration=new_bob_config)


@bob.command()
@group_character_options
@option_config_file
@option_controller_port(default=BobConfiguration.DEFAULT_CONTROLLER_PORT)
@option_dry_run
@group_general_config
def run(general_config, character_options, config_file, controller_port, dry_run):
    """
    Start Bob's controller.
    """
    emitter = _setup_emitter(general_config)

    BOB = character_options.create_character(emitter, config_file)

    # RPC
    if general_config.json_ipc:
        rpc_controller = BOB.make_rpc_controller()
        _transport = rpc_controller.make_control_transport()
        rpc_controller.start()
        return

    # Echo Public Keys
    emitter.message(f"Bob Verifying Key {bytes(BOB.stamp).hex()}", color='green', bold=True)
    bob_encrypting_key = bytes(BOB.public_keys(DecryptingPower)).hex()
    emitter.message(f"Bob Encrypting Key {bob_encrypting_key}", color="blue", bold=True)
    # Start Controller
    controller = BOB.make_web_controller(crash_on_error=general_config.debug)
    BOB.log.info('Starting HTTP Character Web Controller')
    return controller.start(http_port=controller_port, dry_run=dry_run)


@bob.command()
@option_config_file
@group_config_options
@group_general_config
def config(general_config, config_options, config_file):
    """
    View and optionally update existing Bob's configuration.
    """
    emitter = _setup_emitter(general_config)
    bob_config = config_options.create_config(emitter, config_file)
    filepath = config_file or bob_config.config_file_location
    emitter.echo(f"Bob Configuration {filepath} \n {'='*55}")
    return get_or_update_configuration(emitter=emitter,
                                       config_class=BobConfiguration,
                                       filepath=filepath,
                                       config_options=config_options)


@bob.command()
@group_config_options
@option_config_file
@option_force
@group_general_config
def destroy(general_config, config_options, config_file, force):
    """
    Delete existing Bob's configuration.
    """
    emitter = _setup_emitter(general_config)

    # Validate
    if config_options.dev:
        message = "'nucypher bob destroy' cannot be used in --dev mode"
        raise click.BadOptionUsage(option_name='--dev', message=message)

    bob_config = config_options.create_config(emitter, config_file)

    # Request
    return actions.destroy_configuration(emitter, character_config=bob_config, force=force)


@bob.command(name='public-keys')
@group_character_options
@option_config_file
@BobInterface.connect_cli('public_keys')
@group_general_config
def public_keys(general_config, character_options, config_file):
    """
    Obtain Bob's public verification and encryption keys.
    """
    emitter = _setup_emitter(general_config)
    BOB = character_options.create_character(emitter, config_file)
    response = BOB.controller.public_keys()
    return response


@bob.command()
@group_character_options
@option_config_file
@BobInterface.connect_cli('retrieve')
@group_general_config
def retrieve(general_config, character_options, config_file,
             label, policy_encrypting_key, alice_verifying_key, message_kit):
    """
    Obtain plaintext from encrypted data, if access was granted.
    """
    emitter = _setup_emitter(general_config)

    BOB = character_options.create_character(emitter, config_file)

    # Validate
    if not all((label, policy_encrypting_key, alice_verifying_key, message_kit)):
        input_specification, output_specification = BOB.control.get_specifications(interface_name='retrieve')
        required_fields = ', '.join(input_specification)
        raise click.BadArgumentUsage(f'{required_fields} are required flags to retrieve')

    # Request
    bob_request_data = {
        'label': label,
        'policy_encrypting_key': policy_encrypting_key,
        'alice_verifying_key': alice_verifying_key,
        'message_kit': message_kit,
    }

    response = BOB.controller.retrieve(request=bob_request_data)
    return response


def _setup_emitter(general_config):
    # Banner
    emitter = general_config.emitter
    emitter.clear()
    emitter.banner(BOB_BANNER)

    return emitter
