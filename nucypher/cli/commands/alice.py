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


import click

from nucypher.characters.control.emitters import StdoutEmitter
from nucypher.characters.control.interfaces import AliceInterface
from nucypher.cli.actions.auth import get_nucypher_password
from nucypher.cli.actions.collect import collect_bob_public_keys, collect_policy_parameters
from nucypher.cli.actions.configure import (
    destroy_configuration,
    handle_missing_configuration_file,
    get_or_update_configuration
)
from nucypher.cli.actions.confirm import confirm_staged_grant
from nucypher.cli.actions.select import select_client_account, select_config_file
from nucypher.cli.actions.validate import validate_grant_command
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
    option_signer_uri,
    option_teacher_uri,
    option_lonely,
    option_max_gas_price
)
from nucypher.cli.painting.help import paint_new_installation_help
from nucypher.cli.painting.policies import paint_single_card
from nucypher.cli.types import EIP55_CHECKSUM_ADDRESS
from nucypher.cli.utils import make_cli_character, setup_emitter
from nucypher.config.characters import AliceConfiguration
from nucypher.config.constants import (
    TEMPORARY_DOMAIN,
)
from nucypher.config.keyring import NucypherKeyring
from nucypher.network.middleware import RestMiddleware
from nucypher.policy.identity import Card

option_pay_with = click.option('--pay-with', help="Run with a specified account", type=EIP55_CHECKSUM_ADDRESS)
option_payment_periods = click.option('--payment-periods', help="Policy payment periods", type=click.INT)


class AliceConfigOptions:

    __option_name__ = 'config_options'

    def __init__(self,
                 dev: bool,
                 network: str,
                 provider_uri: str,
                 federated_only: bool,
                 discovery_port: int,
                 pay_with: str,
                 registry_filepath: str,
                 middleware: RestMiddleware,
                 gas_strategy: str,
                 max_gas_price: int,  # gwei
                 signer_uri: str,
                 lonely: bool,
                 ):

        self.dev = dev
        self.domain = network
        self.provider_uri = provider_uri
        self.signer_uri = signer_uri
        self.gas_strategy = gas_strategy
        self.max_gas_price = max_gas_price
        self.federated_only = federated_only
        self.pay_with = pay_with
        self.discovery_port = discovery_port
        self.registry_filepath = registry_filepath
        self.middleware = middleware
        self.lonely = lonely

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
                domain=TEMPORARY_DOMAIN,
                provider_uri=self.provider_uri,
                signer_uri=self.signer_uri,
                gas_strategy=self.gas_strategy,
                max_gas_price=self.max_gas_price,
                federated_only=True,
                lonely=self.lonely
            )

        else:
            if not config_file:
                config_file = select_config_file(emitter=emitter,
                                                 checksum_address=self.pay_with,
                                                 config_class=AliceConfiguration)
            try:
                return AliceConfiguration.from_configuration_file(
                    emitter=emitter,
                    dev_mode=False,
                    network_middleware=self.middleware,
                    domain=self.domain,
                    provider_uri=self.provider_uri,
                    signer_uri=self.signer_uri,
                    gas_strategy=self.gas_strategy,
                    max_gas_price=self.max_gas_price,
                    filepath=config_file,
                    rest_port=self.discovery_port,
                    checksum_address=self.pay_with,
                    registry_filepath=self.registry_filepath,
                    lonely=self.lonely
                )
            except FileNotFoundError:
                return handle_missing_configuration_file(
                    character_config_class=AliceConfiguration,
                    config_file=config_file
                )


group_config_options = group_options(
    AliceConfigOptions,
    dev=option_dev,
    network=option_network(),
    provider_uri=option_provider_uri(),
    signer_uri=option_signer_uri,
    gas_strategy=option_gas_strategy,
    max_gas_price=option_max_gas_price,
    federated_only=option_federated_only,
    discovery_port=option_discovery_port(),
    pay_with=option_pay_with,
    registry_filepath=option_registry_filepath,
    middleware=option_middleware,
    lonely=option_lonely,
)


class AliceFullConfigOptions:

    __option_name__ = 'full_config_options'

    def __init__(self, config_options, poa: bool, light: bool, m: int, n: int, payment_periods: int):
        self.config_options = config_options
        self.poa = poa
        self.light = light
        self.m = m
        self.n = n
        self.payment_periods = payment_periods

    def generate_config(self, emitter: StdoutEmitter, config_root: str) -> AliceConfiguration:

        opts = self.config_options

        if opts.dev:
            raise click.BadArgumentUsage("Cannot create a persistent development character")

        if not opts.provider_uri and not opts.federated_only:
            raise click.BadOptionUsage(
                option_name='--provider',
                message="--provider is required to create a new decentralized alice.")

        pay_with = opts.pay_with
        if not pay_with and not opts.federated_only:
            pay_with = select_client_account(emitter=emitter,
                                             provider_uri=opts.provider_uri,
                                             signer_uri=opts.signer_uri,
                                             show_eth_balance=True,
                                             network=opts.domain)

        return AliceConfiguration.generate(
            password=get_nucypher_password(emitter=emitter, confirm=True),
            config_root=config_root,
            checksum_address=pay_with,
            domain=opts.domain,
            federated_only=opts.federated_only,
            provider_uri=opts.provider_uri,
            signer_uri=opts.signer_uri,
            registry_filepath=opts.registry_filepath,
            poa=self.poa,
            light=self.light,
            m=self.m,
            n=self.n,
            payment_periods=self.payment_periods)

    def get_updates(self) -> dict:
        opts = self.config_options
        payload = dict(checksum_address=opts.pay_with,
                       domain=opts.domain,
                       federated_only=opts.federated_only,
                       provider_uri=opts.provider_uri,
                       signer_uri=opts.signer_uri,
                       registry_filepath=opts.registry_filepath,
                       poa=self.poa,
                       light=self.light,
                       m=self.m,
                       n=self.n,
                       payment_periods=self.payment_periods)
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
    payment_periods=option_payment_periods
)


class AliceCharacterOptions:

    __option_name__ = 'character_options'

    def __init__(self, config_options: AliceConfigOptions, hw_wallet: bool, teacher_uri: str, min_stake: int):
        self.config_options = config_options
        self.hw_wallet = hw_wallet
        self.teacher_uri = teacher_uri
        self.min_stake = min_stake

    def create_character(self, emitter, config_file, json_ipc, load_seednodes=True):
        config = self.config_options.create_config(emitter, config_file)
        try:
            ALICE = make_cli_character(character_config=config,
                                       emitter=emitter,
                                       unlock_keyring=not config.dev_mode,
                                       unlock_signer=not config.federated_only,
                                       teacher_uri=self.teacher_uri,
                                       min_stake=self.min_stake,
                                       start_learning_now=load_seednodes,
                                       lonely=self.config_options.lonely,
                                       json_ipc=json_ipc)
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
    """"Alice the Policy Authority" management commands."""


@alice.command()
@group_full_config_options
@option_config_root
@group_general_config
def init(general_config, full_config_options, config_root):
    """Create a brand new persistent Alice."""
    emitter = setup_emitter(general_config)
    if not config_root:
        config_root = general_config.config_root
    new_alice_config = full_config_options.generate_config(emitter, config_root)
    filepath = new_alice_config.to_configuration_file()
    paint_new_installation_help(emitter, new_configuration=new_alice_config, filepath=filepath)


@alice.command()
@option_config_file
@group_general_config
@group_full_config_options
def config(general_config, config_file, full_config_options):
    """View and optionally update existing Alice's configuration."""
    emitter = setup_emitter(general_config)
    if not config_file:
        config_file = select_config_file(emitter=emitter,
                                         checksum_address=full_config_options.config_options.pay_with,
                                         config_class=AliceConfiguration)
    updates = full_config_options.get_updates()
    get_or_update_configuration(emitter=emitter,
                                config_class=AliceConfiguration,
                                filepath=config_file,
                                updates=updates)


@alice.command()
@group_config_options
@option_config_file
@option_force
@group_general_config
def destroy(general_config, config_options, config_file, force):
    """Delete existing Alice's configuration."""
    emitter = setup_emitter(general_config)
    alice_config = config_options.create_config(emitter, config_file)
    destroy_configuration(emitter, character_config=alice_config, force=force)


@alice.command()
@option_config_file
@option_controller_port(default=AliceConfiguration.DEFAULT_CONTROLLER_PORT)
@option_dry_run
@group_general_config
@group_character_options
def run(general_config, character_options, config_file, controller_port, dry_run):
    """Start Alice's web controller."""

    # Setup
    emitter = setup_emitter(general_config)
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
    """Obtain Alice's public verification and encryption keys."""
    emitter = setup_emitter(general_config)
    ALICE = character_options.create_character(emitter, config_file, general_config.json_ipc, load_seednodes=False)
    response = ALICE.controller.public_keys()
    return response


@alice.command()
@group_character_options
@option_config_file
@group_general_config
@click.option('--nickname', help="Human-readable nickname / alias for a card", type=click.STRING, required=False)
def make_card(general_config, character_options, config_file, nickname):
    """Create a character card file for public key sharing"""
    emitter = setup_emitter(general_config)
    ALICE = character_options.create_character(emitter, config_file,
                                               json_ipc=general_config.json_ipc,
                                               load_seednodes=False)
    card = Card.from_character(ALICE)
    if nickname:
        card.nickname = nickname
    card.save(overwrite=True)
    emitter.message(f"Saved new character card to {card.filepath}", color='green')
    paint_single_card(card=card, emitter=emitter)


@alice.command('derive-policy-pubkey')
@AliceInterface.connect_cli('derive_policy_encrypting_key')
@group_character_options
@option_config_file
@group_general_config
def derive_policy_pubkey(general_config, label, character_options, config_file):
    """Get a policy public key from a policy label."""
    emitter = setup_emitter(general_config)
    ALICE = character_options.create_character(emitter,
                                               config_file,
                                               json_ipc=general_config.json_ipc,
                                               load_seednodes=False)
    return ALICE.controller.derive_policy_encrypting_key(label=label)


@alice.command()
@AliceInterface.connect_cli('grant')
@option_config_file
@group_general_config
@group_character_options
@option_force
@click.option('--bob', type=click.STRING, help="The card id or nickname of a stored Bob card.")
def grant(general_config,
          bob,
          bob_encrypting_key,
          bob_verifying_key,
          label,
          value,
          rate,
          expiration,
          m, n,
          character_options,
          config_file,
          force):
    """Create and enact an access policy for Bob."""

    # Setup
    emitter = setup_emitter(general_config)
    ALICE = character_options.create_character(
        emitter=emitter,
        config_file=config_file,
        json_ipc=general_config.json_ipc
    )
    validate_grant_command(
        emitter=emitter,
        alice=ALICE,
        force=force,
        bob=bob,
        label=label,
        rate=rate,
        value=value,
        expiration=expiration,
        bob_encrypting_key=bob_encrypting_key,
        bob_verifying_key=bob_verifying_key
    )

    # Collect
    bob_public_keys = collect_bob_public_keys(
        emitter=emitter,
        force=force,
        card_identifier=bob,
        bob_encrypting_key=bob_encrypting_key,
        bob_verifying_key=bob_verifying_key
    )

    policy = collect_policy_parameters(
            emitter=emitter,
            alice=ALICE,
            force=force,
            bob_identifier=bob_public_keys.verifying_key[:8],
            label=label,
            m=m,
            n=n,
            rate=rate,
            value=value,
            expiration=expiration
    )

    grant_request = {
        'bob_encrypting_key': bob_public_keys.encrypting_key,
        'bob_verifying_key': bob_public_keys.verifying_key,
        'label': policy.label,
        'm': policy.m,
        'n': policy.n,
        'expiration': policy.expiration,
    }
    if not ALICE.federated_only:
        # These values can be 0
        if policy.value is not None:
            grant_request['value'] = policy.value
        elif policy.rate is not None:
            grant_request['rate'] = policy.rate  # in wei

    # Grant
    if not force and not general_config.json_ipc:
        confirm_staged_grant(emitter=emitter,
                             grant_request=grant_request,
                             federated=ALICE.federated_only,
                             seconds_per_period=(None if ALICE.federated_only else ALICE.economics.seconds_per_period))
    emitter.echo(f'Granting Access to {bob_public_keys.verifying_key[:8]}', color='yellow')
    return ALICE.controller.grant(request=grant_request)


@alice.command()
@AliceInterface.connect_cli('revoke')
@group_character_options
@option_config_file
@group_general_config
def revoke(general_config, bob_verifying_key, label, character_options, config_file):
    """Revoke a policy."""
    emitter = setup_emitter(general_config)
    ALICE = character_options.create_character(emitter, config_file, general_config.json_ipc)
    revoke_request = {'label': label, 'bob_verifying_key': bob_verifying_key}
    return ALICE.controller.revoke(request=revoke_request)


@alice.command()
@AliceInterface.connect_cli('decrypt')
@group_character_options
@option_config_file
@group_general_config
def decrypt(general_config, label, message_kit, character_options, config_file):
    """Decrypt data encrypted under an Alice's policy public key."""
    emitter = setup_emitter(general_config)
    ALICE = character_options.create_character(emitter, config_file, general_config.json_ipc, load_seednodes=False)
    request_data = {'label': label, 'message_kit': message_kit}
    response = ALICE.controller.decrypt(request=request_data)
    return response
