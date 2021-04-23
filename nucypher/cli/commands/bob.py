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
from base64 import b64decode

import click

from nucypher.characters.control.emitters import StdoutEmitter
from nucypher.characters.control.interfaces import BobInterface
from nucypher.characters.lawful import Alice
from nucypher.cli.actions.auth import get_nucypher_password
from nucypher.cli.actions.configure import (
    destroy_configuration,
    get_or_update_configuration,
    handle_missing_configuration_file
)
from nucypher.cli.actions.select import select_client_account, select_config_file
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
    option_signer_uri,
    option_teacher_uri,
    option_lonely,
    option_max_gas_price
)
from nucypher.cli.painting.help import paint_new_installation_help
from nucypher.cli.painting.policies import paint_single_card
from nucypher.cli.utils import make_cli_character, setup_emitter
from nucypher.config.characters import BobConfiguration
from nucypher.config.constants import TEMPORARY_DOMAIN
from nucypher.crypto.powers import DecryptingPower
from nucypher.network.middleware import RestMiddleware
from nucypher.policy.identity import Card


class BobConfigOptions:

    __option_name__ = 'config_options'

    def __init__(self, 
                 provider_uri: str,
                 network: str,
                 registry_filepath: str,
                 checksum_address: str,
                 discovery_port: int,
                 dev: bool,
                 middleware: RestMiddleware,
                 federated_only: bool,
                 gas_strategy: str,
                 max_gas_price: int,
                 signer_uri: str,
                 lonely: bool
                 ):

        self.provider_uri = provider_uri
        self.signer_uri = signer_uri
        self.gas_strategy = gas_strategy
        self.max_gas_price = max_gas_price
        self.domain = network
        self.registry_filepath = registry_filepath
        self.checksum_address = checksum_address
        self.discovery_port = discovery_port
        self.dev = dev
        self.middleware = middleware
        self.federated_only = federated_only
        self.lonely = lonely

    def create_config(self, emitter: StdoutEmitter, config_file: str) -> BobConfiguration:
        if self.dev:
            return BobConfiguration(
                emitter=emitter,
                dev_mode=True,
                domain=TEMPORARY_DOMAIN,
                provider_uri=self.provider_uri,
                gas_strategy=self.gas_strategy,
                max_gas_price=self.max_gas_price,
                signer_uri=self.signer_uri,
                federated_only=True,
                checksum_address=self.checksum_address,
                network_middleware=self.middleware,
                lonely=self.lonely
            )
        else:
            if not config_file:
                config_file = select_config_file(emitter=emitter,
                                                 checksum_address=self.checksum_address,
                                                 config_class=BobConfiguration)
            try:
                return BobConfiguration.from_configuration_file(
                    emitter=emitter,
                    filepath=config_file,
                    domain=self.domain,
                    checksum_address=self.checksum_address,
                    rest_port=self.discovery_port,
                    provider_uri=self.provider_uri,
                    signer_uri=self.signer_uri,
                    gas_strategy=self.gas_strategy,
                    max_gas_price=self.max_gas_price,
                    registry_filepath=self.registry_filepath,
                    network_middleware=self.middleware,
                    lonely=self.lonely
                )
            except FileNotFoundError:
                handle_missing_configuration_file(character_config_class=BobConfiguration,
                                                  config_file=config_file)

    def generate_config(self, emitter: StdoutEmitter, config_root: str) -> BobConfiguration:

        checksum_address = self.checksum_address
        if not checksum_address and not self.federated_only:
            checksum_address = select_client_account(emitter=emitter,
                                                     signer_uri=self.signer_uri,
                                                     provider_uri=self.provider_uri)  # TODO: See #1888

        return BobConfiguration.generate(
            password=get_nucypher_password(emitter=emitter, confirm=True),
            config_root=config_root,
            checksum_address=checksum_address,
            domain=self.domain,
            federated_only=self.federated_only,
            registry_filepath=self.registry_filepath,
            provider_uri=self.provider_uri,
            signer_uri=self.signer_uri,
            gas_strategy=self.gas_strategy,
            max_gas_price=self.max_gas_price,
            lonely=self.lonely
        )

    def get_updates(self) -> dict:
        payload = dict(checksum_address=self.checksum_address,
                       domain=self.domain,
                       federated_only=self.federated_only,
                       registry_filepath=self.registry_filepath,
                       provider_uri=self.provider_uri,
                       signer_uri=self.signer_uri,
                       gas_strategy=self.gas_strategy,
                       max_gas_price=self.max_gas_price,
                       lonely=self.lonely
                       )
        # Depends on defaults being set on Configuration classes, filtrates None values
        updates = {k: v for k, v in payload.items() if v is not None}
        return updates


group_config_options = group_options(
    BobConfigOptions,
    provider_uri=option_provider_uri(),
    gas_strategy=option_gas_strategy,
    max_gas_price=option_max_gas_price,
    signer_uri=option_signer_uri,
    network=option_network(),
    registry_filepath=option_registry_filepath,
    checksum_address=option_checksum_address,
    discovery_port=option_discovery_port(),
    dev=option_dev,
    middleware=option_middleware,
    federated_only=option_federated_only,
    lonely=option_lonely,
)


class BobCharacterOptions:

    __option_name__ = 'character_options'

    def __init__(self, config_options: BobConfigOptions, teacher_uri: str, min_stake: int):
        self.config_options = config_options
        self.teacher_uri = teacher_uri
        self.min_stake = min_stake

    def create_character(self, emitter, config_file, json_ipc):
        config = self.config_options.create_config(emitter, config_file)
        BOB = make_cli_character(character_config=config,
                                 emitter=emitter,
                                 unlock_keyring=not self.config_options.dev,
                                 unlock_signer=not config.federated_only and config.signer_uri,
                                 teacher_uri=self.teacher_uri,
                                 min_stake=self.min_stake,
                                 json_ipc=json_ipc)
        return BOB


group_character_options = group_options(
    BobCharacterOptions,
    config_options=group_config_options,
    teacher_uri=option_teacher_uri,
    min_stake=option_min_stake
)


@click.group()
def bob():
    """"Bob management commands."""


@bob.command()
@group_config_options
@option_federated_only
@option_config_root
@group_general_config
def init(general_config, config_options, config_root):
    """Create a brand new persistent Bob."""
    emitter = setup_emitter(general_config)
    if not config_root:
        config_root = general_config.config_root
    new_bob_config = config_options.generate_config(emitter, config_root)
    filepath = new_bob_config.to_configuration_file()
    paint_new_installation_help(emitter, new_configuration=new_bob_config, filepath=filepath)


@bob.command()
@group_character_options
@option_config_file
@option_controller_port(default=BobConfiguration.DEFAULT_CONTROLLER_PORT)
@option_dry_run
@group_general_config
def run(general_config, character_options, config_file, controller_port, dry_run):
    """Start Bob's controller."""

    # Setup
    emitter = setup_emitter(general_config)
    BOB = character_options.create_character(emitter=emitter,
                                             config_file=config_file,
                                             json_ipc=general_config.json_ipc)

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
    """View and optionally update existing Bob's configuration."""
    emitter = setup_emitter(general_config)
    if not config_file:
        config_file = select_config_file(emitter=emitter,
                                         checksum_address=config_options.checksum_address,
                                         config_class=BobConfiguration)
    updates = config_options.get_updates()
    get_or_update_configuration(emitter=emitter,
                                config_class=BobConfiguration,
                                filepath=config_file,
                                updates=updates)


@bob.command()
@group_config_options
@option_config_file
@option_force
@group_general_config
def destroy(general_config, config_options, config_file, force):
    """Delete existing Bob's configuration."""
    emitter = setup_emitter(general_config)
    if config_options.dev:
        message = "'nucypher bob destroy' cannot be used in --dev mode"
        raise click.BadOptionUsage(option_name='--dev', message=message)
    bob_config = config_options.create_config(emitter, config_file)
    destroy_configuration(emitter, character_config=bob_config, force=force)


@bob.command(name='public-keys')
@group_character_options
@option_config_file
@BobInterface.connect_cli('public_keys')
@group_general_config
def public_keys(general_config, character_options, config_file):
    """Obtain Bob's public verification and encryption keys."""
    emitter = setup_emitter(general_config)
    BOB = character_options.create_character(emitter, config_file, json_ipc=general_config.json_ipc)
    response = BOB.controller.public_keys()
    return response


@bob.command()
@group_character_options
@option_config_file
@group_general_config
@click.option('--nickname', help="Human-readable nickname / alias for a card", type=click.STRING, required=False)
def make_card(general_config, character_options, config_file, nickname):
    emitter = setup_emitter(general_config)
    BOB = character_options.create_character(emitter, config_file, json_ipc=False)
    card = Card.from_character(BOB)
    if nickname:
        card.nickname = nickname
    card.save(overwrite=True)
    emitter.message(f"Saved new character card to {card.filepath}", color='green')
    paint_single_card(card=card, emitter=emitter)


@bob.command()
@group_character_options
@option_config_file
@group_general_config
@option_force
@BobInterface.connect_cli('retrieve')
@click.option('--alice', type=click.STRING, help="The card id or nickname of a stored Alice card.")
@click.option('--ipfs', help="Download an encrypted message from IPFS at the specified gateway URI")
@click.option('--decode', help="Decode base64 plaintext messages", is_flag=True)
def retrieve(general_config,
             character_options,
             config_file,
             label,
             policy_encrypting_key,
             alice_verifying_key,
             message_kit,
             ipfs,
             alice,
             decode,
             force):
    """Obtain plaintext from encrypted data, if access was granted."""

    # Setup
    emitter = setup_emitter(general_config)
    BOB = character_options.create_character(emitter, config_file, json_ipc=general_config.json_ipc)

    if not message_kit:
        if ipfs:
            prompt = "Enter IPFS CID for encrypted data"
        else:
            prompt = "Enter encrypted data (base64)"
        message_kit = click.prompt(prompt, type=click.STRING)

    if ipfs:
        import ipfshttpclient
        # TODO: #2108
        emitter.message(f"Connecting to IPFS Gateway {ipfs}")
        ipfs_client = ipfshttpclient.connect(ipfs)
        cid = message_kit  # Understand the message kit value as an IPFS hash.
        raw_message_kit = ipfs_client.cat(cid)  # cat the contents at the hash reference
        emitter.message(f"Downloaded message kit from IPFS (CID {cid})", color='green')
        message_kit = raw_message_kit.decode()  # cast to utf-8

    if not alice_verifying_key:
        if alice:  # from storage
            card = Card.load(identifier=alice)
            if card.character is not Alice:
                emitter.error('Grantee card is not an Alice.')
                raise click.Abort
            alice_verifying_key = card.verifying_key.hex()
            emitter.message(f'{card.nickname or ("Alice #"+card.id.hex())}\n'
                            f'Verifying Key  | {card.verifying_key.hex()}',
                            color='green')
            if not force:
                click.confirm('Is this the correct Granter (Alice)?', abort=True)
        else:  # interactive
            alice_verifying_key = click.prompt("Enter Alice's verifying key", click.STRING)

    if not force:
        if not policy_encrypting_key:
            policy_encrypting_key = click.prompt("Enter policy public key", type=click.STRING)

        if not label:
            label = click.prompt("Enter label to retrieve", type=click.STRING)

    # Request
    bob_request_data = {
        'label': label,
        'policy_encrypting_key': policy_encrypting_key,
        'alice_verifying_key': alice_verifying_key,
        'message_kit': message_kit,
    }

    response = BOB.controller.retrieve(request=bob_request_data)
    if decode:
        messages = list([b64decode(r).decode() for r in response['cleartexts']])
        emitter.echo('----------Messages----------')
        for message in messages:
            emitter.echo(message)
    return response
