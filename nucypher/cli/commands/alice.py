"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""

import os

import click
from constant_sorrow.constants import NO_BLOCKCHAIN_CONNECTION, NO_PASSWORD

from nucypher.characters.banners import ALICE_BANNER
from nucypher.characters.control.interfaces import AliceInterface
from nucypher.cli import actions, painting
from nucypher.cli.actions import get_nucypher_password, select_client_account, get_client_password, \
    get_or_update_configuration
from nucypher.cli.commands.deploy import option_gas_strategy
from nucypher.cli.config import group_general_config
from nucypher.cli.options import (
    group_options,
    option_config_file,
    option_config_root,
    option_controller_port,
    option_dev,
    option_discovery_port,
    option_dry_run,
    option_federated_only,
    option_force,
    option_geth,
    option_hw_wallet,
    option_light,
    option_m,
    option_middleware,
    option_min_stake,
    option_n,
    option_network,
    option_poa,
    option_provider_uri,
    option_registry_filepath,
    option_teacher_uri,
    option_rate, option_signer_uri)
from nucypher.cli.types import EIP55_CHECKSUM_ADDRESS
from nucypher.config.characters import AliceConfiguration
from nucypher.config.constants import NUCYPHER_ENVVAR_ALICE_ETH_PASSWORD
from nucypher.config.keyring import NucypherKeyring
from nucypher.utilities.sandbox.constants import TEMPORARY_DOMAIN

option_bob_verifying_key = click.option(
    '--bob-verifying-key',
    help="Bob's verifying key as a hexadecimal string",
    type=click.STRING,
    required=True
)

option_pay_with = click.option('--pay-with', help="Run with a specified account", type=EIP55_CHECKSUM_ADDRESS)
option_duration_periods = click.option('--duration-periods', help="Policy duration in periods", type=click.INT)


class AliceConfigOptions:

    __option_name__ = 'config_options'

    def __init__(self, dev, network, provider_uri, geth, federated_only, discovery_port,
                 pay_with, registry_filepath, middleware, gas_strategy, signer_uri):

        if federated_only and geth:
            raise click.BadOptionUsage(
                option_name="--geth",
                message="--federated-only cannot be used with the --geth flag")

        # Managed Ethereum Client
        eth_node = NO_BLOCKCHAIN_CONNECTION
        if geth:
            eth_node = actions.get_provider_process()
            provider_uri = eth_node.provider_uri(scheme='file')

        self.dev = dev
        self.domains = {network} if network else None
        self.provider_uri = provider_uri
        self.signer_uri = signer_uri
        self.gas_strategy = gas_strategy
        self.geth = geth
        self.federated_only = federated_only
        self.eth_node = eth_node
        self.pay_with = pay_with
        self.discovery_port = discovery_port
        self.registry_filepath = registry_filepath
        self.middleware = middleware

    def create_config(self, emitter, config_file):

        if self.dev:

            # Can be None as well, meaning it is unset - no error in this case
            if self.federated_only is False:
                raise click.BadOptionUsage(
                    option_name="--federated-only",
                    message="--federated-only cannot be explicitly set to False when --dev is set")

            return AliceConfiguration(
                emitter=emitter,
                dev_mode=True,
                network_middleware=self.middleware,
                domains={TEMPORARY_DOMAIN},
                provider_process=self.eth_node,
                provider_uri=self.provider_uri,
                signer_uri=self.signer_uri,
                gas_strategy=self.gas_strategy,
                federated_only=True)

        else:
            try:
                return AliceConfiguration.from_configuration_file(
                    emitter=emitter,
                    dev_mode=False,
                    network_middleware=self.middleware,
                    domains=self.domains,
                    provider_process=self.eth_node,
                    provider_uri=self.provider_uri,
                    signer_uri=self.signer_uri,
                    gas_strategy=self.gas_strategy,
                    filepath=config_file,
                    rest_port=self.discovery_port,
                    checksum_address=self.pay_with,
                    registry_filepath=self.registry_filepath)
            except FileNotFoundError:
                return actions.handle_missing_configuration_file(
                    character_config_class=AliceConfiguration,
                    config_file=config_file
                )


group_config_options = group_options(
    AliceConfigOptions,
    dev=option_dev,
    network=option_network,
    provider_uri=option_provider_uri(),
    signer_uri=option_signer_uri,
    gas_strategy=option_gas_strategy,
    geth=option_geth,
    federated_only=option_federated_only,
    discovery_port=option_discovery_port(),
    pay_with=option_pay_with,
    registry_filepath=option_registry_filepath,
    middleware=option_middleware,
)


class AliceFullConfigOptions:

    __option_name__ = 'full_config_options'

    def __init__(self, config_options, poa, light, m, n, duration_periods):
        self.config_options = config_options
        self.poa = poa
        self.light = light
        self.m = m
        self.n = n
        self.duration_periods = duration_periods

    def generate_config(self, emitter, config_root):

        opts = self.config_options

        if opts.dev:
            raise click.BadArgumentUsage("Cannot create a persistent development character")

        if not opts.provider_uri and not opts.federated_only:
            raise click.BadOptionUsage(
                option_name='--provider',
                message="--provider is required to create a new decentralized alice.")

        pay_with = opts.pay_with
        if not pay_with and not opts.federated_only:
            pay_with = select_client_account(emitter=emitter, provider_uri=opts.provider_uri, show_balances=False)

        return AliceConfiguration.generate(
            password=get_nucypher_password(confirm=True),
            config_root=config_root,
            checksum_address=pay_with,
            domains=opts.domains,
            federated_only=opts.federated_only,
            provider_uri=opts.provider_uri,
            signer_uri=opts.signer_uri,
            provider_process=opts.eth_node,
            registry_filepath=opts.registry_filepath,
            poa=self.poa,
            light=self.light,
            m=self.m,
            n=self.n,
            duration_periods=self.duration_periods)

    def get_updates(self) -> dict:
        opts = self.config_options
        payload = dict(checksum_address=opts.pay_with,
                       domains=opts.domains,
                       federated_only=opts.federated_only,
                       provider_uri=opts.provider_uri,
                       signer_uri=opts.signer_uri,
                       registry_filepath=opts.registry_filepath,
                       poa=self.poa,
                       light=self.light,
                       m=self.m,
                       n=self.n,
                       duration_periods=self.duration_periods)
        # Depends on defaults being set on Configuration classes, filtrates None values
        updates = {k: v for k, v in payload.items() if v is not None}
        return updates


group_full_config_options = group_options(
    AliceFullConfigOptions,
    config_options=group_config_options,
    poa=option_poa,
    light=option_light,
    m=option_m,
    n=option_n,
    duration_periods=option_duration_periods,
    )


class AliceCharacterOptions:

    __option_name__ = 'character_options'

    def __init__(self, config_options, hw_wallet, teacher_uri, min_stake):
        self.config_options = config_options
        self.hw_wallet = hw_wallet
        self.teacher_uri = teacher_uri
        self.min_stake = min_stake

    def create_character(self, emitter, config_file, json_ipc, load_seednodes=True):

        config = self.config_options.create_config(emitter, config_file)

        client_password = None
        eth_password_is_needed = not config.federated_only and not self.hw_wallet and not config.dev_mode
        if eth_password_is_needed:
            if json_ipc:
                client_password = os.environ.get(NUCYPHER_ENVVAR_ALICE_ETH_PASSWORD, NO_PASSWORD)
                if client_password is NO_PASSWORD:
                    message = f"--json-ipc implies the {NUCYPHER_ENVVAR_ALICE_ETH_PASSWORD} envvar must be set."
                    click.BadOptionUsage(option_name='--json-ipc', message=message)
            else:
                client_password = get_client_password(checksum_address=config.checksum_address,
                                                      envvar=NUCYPHER_ENVVAR_ALICE_ETH_PASSWORD)

        try:
            ALICE = actions.make_cli_character(character_config=config,
                                               emitter=emitter,
                                               unlock_keyring=not config.dev_mode,
                                               teacher_uri=self.teacher_uri,
                                               min_stake=self.min_stake,
                                               client_password=client_password,
                                               load_preferred_teachers=load_seednodes,
                                               start_learning_now=load_seednodes)

            return ALICE
        except NucypherKeyring.AuthenticationFailed as e:
            emitter.echo(str(e), color='red', bold=True)
            click.get_current_context().exit(1)


group_character_options = group_options(
    AliceCharacterOptions,
    config_options=group_config_options,
    hw_wallet=option_hw_wallet,
    teacher_uri=option_teacher_uri,
    min_stake=option_min_stake,
    )


@click.group()
def alice():
    """
    "Alice the Policy Authority" management commands.
    """
    pass


@alice.command()
@group_full_config_options
@option_config_root
@group_general_config
def init(general_config, full_config_options, config_root):
    """
    Create a brand new persistent Alice.
    """
    emitter = _setup_emitter(general_config)
    if not config_root:
        config_root = general_config.config_root
    new_alice_config = full_config_options.generate_config(emitter, config_root)
    painting.paint_new_installation_help(emitter, new_configuration=new_alice_config)


@alice.command()
@option_config_file
@group_general_config
@group_full_config_options
def config(general_config, config_file, full_config_options):
    """
    View and optionally update existing Alice's configuration.
    """
    emitter = _setup_emitter(general_config)
    configuration_file_location = config_file or AliceConfiguration.default_filepath()
    emitter.echo(f"Alice Configuration {configuration_file_location} \n {'='*55}")
    return get_or_update_configuration(emitter=emitter,
                                       config_class=AliceConfiguration,
                                       filepath=configuration_file_location,
                                       config_options=full_config_options)


@alice.command()
@group_config_options
@option_config_file
@option_force
@group_general_config
def destroy(general_config, config_options, config_file, force):
    """
    Delete existing Alice's configuration.
    """
    emitter = _setup_emitter(general_config)
    alice_config = config_options.create_config(emitter, config_file)
    return actions.destroy_configuration(emitter, character_config=alice_config, force=force)


@alice.command()
@option_config_file
@option_controller_port(default=AliceConfiguration.DEFAULT_CONTROLLER_PORT)
@option_dry_run
@group_general_config
@group_character_options
def run(general_config, character_options, config_file, controller_port, dry_run):
    """
    Start Alice's web controller.
    """
    emitter = _setup_emitter(general_config)
    ALICE = character_options.create_character(emitter, config_file, general_config.json_ipc)

    try:
        # RPC
        if general_config.json_ipc:
            rpc_controller = ALICE.make_rpc_controller()
            _transport = rpc_controller.make_control_transport()
            rpc_controller.start()
            return

        # HTTP
        else:
            emitter.message(f"Alice Verifying Key {bytes(ALICE.stamp).hex()}", color="green", bold=True)
            controller = ALICE.make_web_controller(crash_on_error=general_config.debug)
            ALICE.log.info('Starting HTTP Character Web Controller')
            emitter.message(f'Running HTTP Alice Controller at http://localhost:{controller_port}')
            return controller.start(http_port=controller_port, dry_run=dry_run)

    # Handle Crash
    except Exception as e:
        ALICE.log.critical(str(e))
        emitter.message(f"{e.__class__.__name__} {e}", color='red', bold=True)
        if general_config.debug:
            raise  # Crash :-(


@alice.command("public-keys")
@AliceInterface.connect_cli('public_keys')
@group_character_options
@option_config_file
@group_general_config
def public_keys(general_config, character_options, config_file):
    """
    Obtain Alice's public verification and encryption keys.
    """
    emitter = _setup_emitter(general_config)
    ALICE = character_options.create_character(emitter, config_file, general_config.json_ipc, load_seednodes=False)
    response = ALICE.controller.public_keys()
    return response


@alice.command('derive-policy-pubkey')
@AliceInterface.connect_cli('derive_policy_encrypting_key')
@group_character_options
@option_config_file
@group_general_config
def derive_policy_pubkey(general_config, label, character_options, config_file):
    """
    Get a policy public key from a policy label.
    """
    emitter = _setup_emitter(general_config)
    ALICE = character_options.create_character(emitter, config_file, general_config.json_ipc, load_seednodes=False)
    return ALICE.controller.derive_policy_encrypting_key(label=label)


@alice.command()
@AliceInterface.connect_cli('grant')
@option_config_file
@group_general_config
@group_character_options
def grant(general_config,
          # Other (required)
          bob_encrypting_key, bob_verifying_key, label, value, rate,

          # Other
          expiration, m, n,

          # API Options
          character_options, config_file
          ):
    """
    Create and enact an access policy for some Bob.
    """
    config_options = character_options.config_options
    emitter = _setup_emitter(general_config)

    ALICE = character_options.create_character(emitter, config_file, general_config.json_ipc)

    # Input validation
    if ALICE.federated_only:
        if any((value, rate)):
            raise click.BadOptionUsage(option_name="--value, --rate",
                                       message="Can't use --value or --rate with a federated Alice.")
    elif bool(value) and bool(rate):
        raise click.BadOptionUsage(option_name="--rate", message="Can't use --value if using --rate")
    elif not (bool(value) or bool(rate)):
        rate = ALICE.default_rate  # TODO #1709
        click.confirm(f"Confirm default rate {rate}?", abort=True)

    # Request
    grant_request = {
        'bob_encrypting_key': bob_encrypting_key,
        'bob_verifying_key': bob_verifying_key,
        'label': label,
        'm': m,
        'n': n,
        'expiration': expiration,
    }
    if not ALICE.federated_only:
        if value:
            grant_request['value'] = value
        elif rate:
            grant_request['rate'] = rate
    return ALICE.controller.grant(request=grant_request)


@alice.command()
@AliceInterface.connect_cli('revoke')
@group_character_options
@option_config_file
@group_general_config
def revoke(general_config,

           # Other (required)
           bob_verifying_key, label,

           # API Options
           character_options, config_file
           ):
    """
    Revoke a policy.
    """
    emitter = _setup_emitter(general_config)

    ALICE = character_options.create_character(emitter, config_file, general_config.json_ipc)

    # Request
    revoke_request = {'label': label, 'bob_verifying_key': bob_verifying_key}
    return ALICE.controller.revoke(request=revoke_request)


@alice.command()
@AliceInterface.connect_cli('decrypt')
@group_character_options
@option_config_file
@group_general_config
def decrypt(general_config,

            # Other (required)
            label, message_kit,

            # API Options
            character_options, config_file
            ):
    """
    Decrypt data encrypted under an Alice's policy public key.
    """
    emitter = _setup_emitter(general_config)

    ALICE = character_options.create_character(emitter, config_file, general_config.json_ipc, load_seednodes=False)

    # Request
    request_data = {'label': label, 'message_kit': message_kit}
    response = ALICE.controller.decrypt(request=request_data)
    return response


def _setup_emitter(general_config):
    # Banner
    emitter = general_config.emitter
    emitter.clear()
    emitter.banner(ALICE_BANNER)

    return emitter
