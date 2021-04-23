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
import os

from nucypher.characters.control.emitters import StdoutEmitter
from nucypher.cli.actions.auth import (
    get_client_password,
    get_nucypher_password,
    unlock_nucypher_keyring
)
from nucypher.cli.actions.configure import destroy_configuration, handle_missing_configuration_file
from nucypher.cli.actions.select import select_config_file
from nucypher.cli.config import group_general_config
from nucypher.cli.literature import (
    CONFIRM_OVERWRITE_DATABASE,
    FELIX_RUN_MESSAGE,
    SUCCESSFUL_DATABASE_CREATION,
    SUCCESSFUL_DATABASE_DESTRUCTION
)
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
    option_middleware,
    option_min_stake,
    option_network,
    option_poa,
    option_provider_uri,
    option_registry_filepath,
    option_teacher_uri,
    option_signer_uri,
)
from nucypher.cli.painting.help import paint_new_installation_help
from nucypher.cli.types import NETWORK_PORT
from nucypher.cli.utils import setup_emitter
from nucypher.config.characters import FelixConfiguration
from nucypher.config.constants import DEFAULT_CONFIG_ROOT, NUCYPHER_ENVVAR_WORKER_ETH_PASSWORD
from nucypher.utilities.networking import LOOPBACK_ADDRESS

option_port = click.option('--port', help="The host port to run Felix HTTP services on", type=NETWORK_PORT, default=FelixConfiguration.DEFAULT_REST_PORT)


class FelixConfigOptions:

    __option_name__ = 'config_options'

    def __init__(self,
                 dev,
                 network,
                 provider_uri,
                 signer_uri,
                 host,
                 db_filepath,
                 checksum_address,
                 registry_filepath,
                 poa,
                 port):

        self.provider_uri = provider_uri
        self.signer_uri = signer_uri
        self.domain = network
        self.dev = dev
        self.host = host
        self.db_filepath = db_filepath
        self.checksum_address = checksum_address
        self.registry_filepath = registry_filepath
        self.poa = poa
        self.port = port

    def create_config(self, emitter, config_file):
        # Load Felix from Configuration File with overrides
        if not config_file:
            config_file = select_config_file(emitter=emitter,
                                             checksum_address=self.checksum_address,
                                             config_class=FelixConfiguration)
        try:
            return FelixConfiguration.from_configuration_file(
                emitter=emitter,
                filepath=config_file,
                domain=self.domain,
                registry_filepath=self.registry_filepath,
                provider_uri=self.provider_uri,
                signer=self.signer_uri,
                rest_host=self.host,
                rest_port=self.port,
                db_filepath=self.db_filepath,
                poa=self.poa)
        except FileNotFoundError:
            return handle_missing_configuration_file(
                character_config_class=FelixConfiguration,
                config_file=config_file
            )

    def generate_config(self, config_root, discovery_port):
        return FelixConfiguration.generate(
            password=get_nucypher_password(emitter=StdoutEmitter(), confirm=True),
            config_root=config_root,
            rest_host=self.host,
            rest_port=discovery_port,
            db_filepath=self.db_filepath,
            domain=self.domain,
            checksum_address=self.checksum_address,
            registry_filepath=self.registry_filepath,
            provider_uri=self.provider_uri,
            signer_uri=self.signer_uri,
            poa=self.poa)


group_config_options = group_options(
    FelixConfigOptions,
    dev=option_dev,
    network=option_network(),
    provider_uri=option_provider_uri(),
    signer_uri=option_signer_uri,
    host=click.option('--host', help="The host to run Felix HTTP services on", type=click.STRING,
                      default=LOOPBACK_ADDRESS),
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
                                    password=get_nucypher_password(emitter=emitter, confirm=False))

            client_password = get_client_password(checksum_address=felix_config.checksum_address,
                                                  envvar=NUCYPHER_ENVVAR_WORKER_ETH_PASSWORD)

            # Produce Felix
            FELIX = felix_config.produce(domain=self.config_options.domain)
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
    """"Felix the Faucet" management commands."""


@felix.command()
@group_general_config
@option_config_root
@option_discovery_port(default=FelixConfiguration.DEFAULT_LEARNER_PORT)
@group_config_options
def init(general_config, config_options, config_root, discovery_port):
    """Create a brand-new Felix."""
    emitter = setup_emitter(general_config=general_config, banner=config_options.checksum_address)
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
    filepath = new_felix_config.to_configuration_file()
    paint_new_installation_help(emitter, new_configuration=new_felix_config, filepath=filepath)


@felix.command()
@group_config_options
@option_config_file
@option_force
@group_general_config
def destroy(general_config, config_options, config_file, force):
    """Destroy Felix Configuration."""
    emitter = setup_emitter(general_config, config_options.checksum_address)
    felix_config = config_options.create_config(emitter, config_file)
    destroy_configuration(emitter, character_config=felix_config, force=force)


@felix.command()
@group_character_options
@option_config_file
@option_force
@group_general_config
def createdb(general_config, character_options, config_file, force):
    """Create Felix DB."""
    emitter = setup_emitter(general_config, character_options.config_options.checksum_address)
    FELIX = character_options.create_character(emitter, config_file, general_config.debug)
    if os.path.isfile(FELIX.db_filepath):
        if not force:
            click.confirm(CONFIRM_OVERWRITE_DATABASE, abort=True)
        os.remove(FELIX.db_filepath)
        emitter.echo(SUCCESSFUL_DATABASE_DESTRUCTION.format(path=FELIX.db_filepath))
    FELIX.create_tables()
    emitter.echo(SUCCESSFUL_DATABASE_CREATION.format(path=FELIX.db_filepath), color='green')


@felix.command()
@group_character_options
@option_config_file
@group_general_config
def view(general_config, character_options, config_file):
    """View Felix token balance."""
    emitter = setup_emitter(general_config, character_options.config_options.checksum_address)
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
    """View Felix known accounts."""
    emitter = setup_emitter(general_config, character_options.config_options.checksum_address)
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
    """Run Felix services."""
    emitter = setup_emitter(general_config, character_options.config_options.checksum_address)
    FELIX = character_options.create_character(emitter, config_file, general_config.debug)
    host = character_options.config_options.host
    port = character_options.config_options.port
    emitter.message(FELIX_RUN_MESSAGE.format(host=host, port=port))
    FELIX.start(host=host,
                port=port,
                web_services=not dry_run,
                distribution=True,
                crash_on_error=general_config.debug)
