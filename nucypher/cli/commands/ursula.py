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
from constant_sorrow.constants import NO_BLOCKCHAIN_CONNECTION

from nucypher.blockchain.economics import EconomicsFactory
from nucypher.blockchain.eth.utils import datetime_at_period
from nucypher.characters.banners import URSULA_BANNER
from nucypher.cli import actions, painting
from nucypher.cli.actions import (
    get_nucypher_password,
    select_client_account,
    get_client_password,
    get_or_update_configuration,
    select_config_file,
    select_network)
from nucypher.cli.commands.deploy import option_gas_strategy
from nucypher.cli.config import group_general_config
from nucypher.cli.options import (
    group_options,
    option_config_file,
    option_config_root,
    option_db_filepath,
    option_dev,
    option_dry_run,
    option_federated_only,
    option_force,
    option_geth,
    option_light,
    option_min_stake,
    option_network,
    option_poa,
    option_provider_uri,
    option_registry_filepath,
    option_teacher_uri,
    option_signer_uri)
from nucypher.cli.types import EIP55_CHECKSUM_ADDRESS, NETWORK_PORT
from nucypher.config.characters import UrsulaConfiguration
from nucypher.config.constants import NUCYPHER_ENVVAR_WORKER_ETH_PASSWORD, NUCYPHER_ENVVAR_WORKER_IP_ADDRESS
from nucypher.config.keyring import NucypherKeyring
from nucypher.utilities.sandbox.constants import TEMPORARY_DOMAIN


class UrsulaConfigOptions:

    __option_name__ = 'config_options'

    def __init__(self, geth, provider_uri, worker_address, federated_only, rest_host,
                 rest_port, db_filepath, network, registry_filepath, dev, poa, light,
                 gas_strategy, signer_uri, availability_check):

        if federated_only:
            # TODO: consider rephrasing in a more universal voice.
            if geth:
                raise click.BadOptionUsage(option_name="--geth",
                                           message="--geth cannot be used in federated mode.")

            if registry_filepath:
                raise click.BadOptionUsage(option_name="--registry-filepath",
                                           message=f"--registry-filepath cannot be used in federated mode.")

        eth_node = NO_BLOCKCHAIN_CONNECTION
        provider_uri = provider_uri
        if geth:
            eth_node = actions.get_provider_process()
            provider_uri = eth_node.provider_uri(scheme='file')

        self.eth_node = eth_node
        self.provider_uri = provider_uri
        self.signer_uri = signer_uri
        self.worker_address = worker_address
        self.federated_only = federated_only
        self.rest_host = rest_host
        self.rest_port = rest_port  # FIXME: not used in generate()
        self.db_filepath = db_filepath
        self.domains = {network} if network else None  # TODO: #1580
        self.registry_filepath = registry_filepath
        self.dev = dev
        self.poa = poa
        self.light = light
        self.gas_strategy = gas_strategy
        self.availability_check = availability_check

    def create_config(self, emitter, config_file):
        if self.dev:
            return UrsulaConfiguration(
                emitter=emitter,
                dev_mode=True,
                domains={TEMPORARY_DOMAIN},
                poa=self.poa,
                light=self.light,
                registry_filepath=self.registry_filepath,
                provider_process=self.eth_node,
                provider_uri=self.provider_uri,
                signer_uri=self.signer_uri,
                gas_strategy=self.gas_strategy,
                checksum_address=self.worker_address,
                federated_only=self.federated_only,
                rest_host=self.rest_host,
                rest_port=self.rest_port,
                db_filepath=self.db_filepath,
                availability_check=self.availability_check
            )
        else:
            try:
                return UrsulaConfiguration.from_configuration_file(
                    emitter=emitter,
                    filepath=config_file,
                    domains=self.domains,
                    registry_filepath=self.registry_filepath,
                    provider_process=self.eth_node,
                    provider_uri=self.provider_uri,
                    signer_uri=self.signer_uri,
                    gas_strategy=self.gas_strategy,
                    rest_host=self.rest_host,
                    rest_port=self.rest_port,
                    db_filepath=self.db_filepath,
                    poa=self.poa,
                    light=self.light,
                    federated_only=self.federated_only,
                    availability_check=self.availability_check
                )
            except FileNotFoundError:
                return actions.handle_missing_configuration_file(character_config_class=UrsulaConfiguration,
                                                                 config_file=config_file)
            except NucypherKeyring.AuthenticationFailed as e:
                emitter.echo(str(e), color='red', bold=True)
                # TODO: Exit codes (not only for this, but for other exceptions)
                return click.get_current_context().exit(1)

    def generate_config(self, emitter, config_root, force):

        assert not self.dev  # TODO: Raise instead

        worker_address = self.worker_address
        if (not worker_address) and not self.federated_only:
            if not worker_address:
                prompt = "Select worker account"
                worker_address = select_client_account(emitter=emitter,
                                                       prompt=prompt,
                                                       provider_uri=self.provider_uri,
                                                       show_balances=False)

        rest_host = self.rest_host
        if not rest_host:
            rest_host = os.environ.get(NUCYPHER_ENVVAR_WORKER_IP_ADDRESS)
            if not rest_host:
                # TODO: Something less centralized... :-(
                # TODO: Ask Ursulas instead
                rest_host = actions.determine_external_ip_address(emitter, force=force)

        return UrsulaConfiguration.generate(password=get_nucypher_password(confirm=True),
                                            config_root=config_root,
                                            rest_host=rest_host,
                                            rest_port=self.rest_port,
                                            db_filepath=self.db_filepath,
                                            domains=self.domains,
                                            federated_only=self.federated_only,
                                            worker_address=worker_address,
                                            registry_filepath=self.registry_filepath,
                                            provider_process=self.eth_node,
                                            provider_uri=self.provider_uri,
                                            signer_uri=self.signer_uri,
                                            gas_strategy=self.gas_strategy,
                                            poa=self.poa,
                                            light=self.light,
                                            availability_check=self.availability_check)

    def get_updates(self) -> dict:
        payload = dict(rest_host=self.rest_host,
                       rest_port=self.rest_port,
                       db_filepath=self.db_filepath,
                       domains=self.domains,
                       federated_only=self.federated_only,
                       checksum_address=self.worker_address,
                       registry_filepath=self.registry_filepath,
                       provider_uri=self.provider_uri,
                       signer_uri=self.signer_uri,
                       gas_strategy=self.gas_strategy,
                       poa=self.poa,
                       light=self.light,
                       availability_check=self.availability_check)
        # Depends on defaults being set on Configuration classes, filtrates None values
        updates = {k: v for k, v in payload.items() if v is not None}
        return updates


group_config_options = group_options(
    UrsulaConfigOptions,
    geth=option_geth,
    provider_uri=option_provider_uri(),
    signer_uri=option_signer_uri,
    gas_strategy=option_gas_strategy,
    worker_address=click.option('--worker-address', help="Run the worker-ursula with a specified address", type=EIP55_CHECKSUM_ADDRESS),
    federated_only=option_federated_only,
    rest_host=click.option('--rest-host', help="The host IP address to run Ursula network services on", type=click.STRING),
    rest_port=click.option('--rest-port', help="The host port to run Ursula network services on", type=NETWORK_PORT),
    db_filepath=option_db_filepath,
    network=option_network,
    registry_filepath=option_registry_filepath,
    poa=option_poa,
    light=option_light,
    dev=option_dev,
    availability_check=click.option('--availability-check/--disable-availability-check', help="Enable or disable self-health checks while running", is_flag=True, default=None)
)


class UrsulaCharacterOptions:

    __option_name__ = 'character_options'

    def __init__(self, config_options, lonely, teacher_uri, min_stake):
        self.config_options = config_options
        self.lonely = lonely
        self.teacher_uri = teacher_uri
        self.min_stake = min_stake

    def create_character(self, emitter, config_file, json_ipc, load_seednodes=True):

        ursula_config = self.config_options.create_config(emitter, config_file)

        # TODO: WAT
        client_password = None
        if not ursula_config.federated_only:
            if not self.config_options.dev and not json_ipc:
                client_password = get_client_password(checksum_address=ursula_config.worker_address,
                                                      envvar=NUCYPHER_ENVVAR_WORKER_ETH_PASSWORD)

        try:
            URSULA = actions.make_cli_character(character_config=ursula_config,
                                                emitter=emitter,
                                                min_stake=self.min_stake,
                                                teacher_uri=self.teacher_uri,
                                                unlock_keyring=not self.config_options.dev,
                                                lonely=self.lonely,
                                                client_password=client_password,
                                                load_preferred_teachers=load_seednodes and not self.lonely,
                                                start_learning_now=load_seednodes)
            return ursula_config, URSULA

        except NucypherKeyring.AuthenticationFailed as e:
            emitter.echo(str(e), color='red', bold=True)
            # TODO: Exit codes (not only for this, but for other exceptions)
            return click.get_current_context().exit(1)


group_character_options = group_options(
    UrsulaCharacterOptions,
    config_options=group_config_options,
    lonely=click.option('--lonely', help="Do not connect to seednodes", is_flag=True),
    teacher_uri=option_teacher_uri,
    min_stake=option_min_stake)


@click.group()
def ursula():
    """
    "Ursula the Untrusted" PRE Re-encryption node management commands.
    """


@ursula.command()
@group_config_options
@option_force
@option_config_root
@group_general_config
def init(general_config, config_options, force, config_root):
    """
    Create a new Ursula node configuration.
    """
    emitter = _setup_emitter(general_config, config_options.worker_address)
    _pre_launch_warnings(emitter, dev=None, force=force)
    if not config_root:
        config_root = general_config.config_root
    if not config_options.federated_only and not config_options.domains:  # TODO: Again, weird network/domains mapping. See UrsulaConfigOptions' constructor. #1580
        config_options.domains = {select_network(emitter)}
    ursula_config = config_options.generate_config(emitter, config_root, force)
    painting.paint_new_installation_help(emitter, new_configuration=ursula_config)


@ursula.command()
@group_config_options
@option_config_file
@option_force
@group_general_config
def destroy(general_config, config_options, config_file, force):
    """
    Delete Ursula node configuration.
    """
    emitter = _setup_emitter(general_config, config_options.worker_address)
    _pre_launch_warnings(emitter, dev=config_options.dev, force=force)
    if not config_file:
        config_file = select_config_file(emitter=emitter,
                                         checksum_address=config_options.worker_address,
                                         config_class=UrsulaConfiguration)
    ursula_config = config_options.create_config(emitter, config_file)
    actions.destroy_configuration(emitter, character_config=ursula_config, force=force)


@ursula.command()
@group_config_options
@option_config_file
@group_general_config
def forget(general_config, config_options, config_file):
    """
    Forget all known nodes.
    """
    emitter = _setup_emitter(general_config, config_options.worker_address)
    _pre_launch_warnings(emitter, dev=config_options.dev, force=None)
    ursula_config = config_options.create_config(emitter, config_file)
    actions.forget(emitter, configuration=ursula_config)


@ursula.command()
@group_character_options
@option_config_file
@option_dry_run
@group_general_config
@click.option('--interactive', '-I', help="Run interactively", is_flag=True, default=False)
@click.option('--prometheus', help="Run the ursula prometheus exporter", is_flag=True, default=False)
@click.option('--metrics-port', help="Run a Prometheus metrics exporter on specified HTTP port", type=NETWORK_PORT)
def run(general_config, character_options, config_file, interactive, dry_run, metrics_port, prometheus):
    """Run an "Ursula" node."""

    worker_address = character_options.config_options.worker_address
    emitter = _setup_emitter(general_config, worker_address=worker_address)
    _pre_launch_warnings(emitter, dev=character_options.config_options.dev, force=None)

    if not character_options.config_options.dev and not config_file:
        config_file = select_config_file(emitter=emitter,
                                         checksum_address=worker_address,
                                         config_class=UrsulaConfiguration)

    ursula_config, URSULA = character_options.create_character(
            emitter=emitter,
            config_file=config_file,
            json_ipc=general_config.json_ipc
    )

    return URSULA.run(emitter=emitter,
                      start_reactor=not dry_run,
                      interactive=interactive,
                      prometheus=prometheus)


@ursula.command(name='save-metadata')
@group_character_options
@option_config_file
@group_general_config
def save_metadata(general_config, character_options, config_file):
    """
    Manually write node metadata to disk without running.
    """
    emitter = _setup_emitter(general_config, character_options.config_options.worker_address)
    _pre_launch_warnings(emitter, dev=character_options.config_options.dev, force=None)
    _, URSULA = character_options.create_character(emitter, config_file, general_config.json_ipc, load_seednodes=False)
    metadata_path = URSULA.write_node_metadata(node=URSULA)
    emitter.message(f"Successfully saved node metadata to {metadata_path}.", color='green')


@ursula.command()
@group_config_options
@option_config_file
@group_general_config
def config(general_config, config_options, config_file):
    """
    View and optionally update the Ursula node's configuration.
    """
    emitter = _setup_emitter(general_config, config_options.worker_address)
    if not config_file:
        config_file = select_config_file(emitter=emitter,
                                         checksum_address=config_options.worker_address,
                                         config_class=UrsulaConfiguration)
    emitter.echo(f"Ursula Configuration {config_file} \n {'='*55}")
    return get_or_update_configuration(emitter=emitter,
                                       config_class=UrsulaConfiguration,
                                       filepath=config_file,
                                       config_options=config_options)


@ursula.command(name='confirm-activity')
@group_character_options
@option_config_file
@group_general_config
def confirm_activity(general_config, character_options, config_file):
    """
    Manually confirm-activity for the current period.
    """
    emitter = _setup_emitter(general_config, character_options.config_options.worker_address)
    _pre_launch_warnings(emitter, dev=character_options.config_options.dev, force=None)
    _, URSULA = character_options.create_character(emitter, config_file, general_config.json_ipc, load_seednodes=False)

    confirmed_period = URSULA.staking_agent.get_current_period() + 1
    click.echo(f"Confirming activity for period {confirmed_period}", color='blue')
    receipt = URSULA.confirm_activity()

    economics = EconomicsFactory.get_economics(registry=URSULA.registry)
    date = datetime_at_period(period=confirmed_period,
                              seconds_per_period=economics.seconds_per_period)

    # TODO: Double-check dates here
    emitter.echo(f'\nActivity confirmed for period #{confirmed_period} '
                 f'(starting at {date})', bold=True, color='blue')
    painting.paint_receipt_summary(emitter=emitter,
                                   receipt=receipt,
                                   chain_name=URSULA.staking_agent.blockchain.client.chain_name)

    # TODO: Check ActivityConfirmation event (see #1193)


def _setup_emitter(general_config, worker_address):
    # Banner
    emitter = general_config.emitter
    emitter.clear()
    emitter.banner(URSULA_BANNER.format(worker_address or ''))

    return emitter


def _pre_launch_warnings(emitter, dev, force):
    if dev:
        emitter.echo("WARNING: Running in Development mode", color='yellow', verbosity=1)
    if force:
        emitter.echo("WARNING: Force is enabled", color='yellow', verbosity=1)
