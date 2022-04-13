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


from pathlib import Path

import click

from nucypher.blockchain.eth.signers.software import ClefSigner
from nucypher.blockchain.eth.networks import NetworksInventory
from nucypher.cli.actions.auth import get_client_password, get_nucypher_password, recover_keystore
from nucypher.cli.actions.configure import (
    destroy_configuration,
    handle_missing_configuration_file,
    get_or_update_configuration,
    collect_operator_ip_address
)
from nucypher.cli.actions.configure import forget as forget_nodes, perform_startup_ip_check
from nucypher.cli.actions.select import select_client_account, select_config_file, select_network
from nucypher.cli.commands.deploy import option_gas_strategy
from nucypher.cli.config import group_general_config
from nucypher.cli.literature import (
    DEVELOPMENT_MODE_WARNING,
    FORCE_MODE_WARNING,
    SUCCESSFUL_MANUALLY_SAVE_METADATA
)
from nucypher.cli.options import (
    group_options,
    option_config_file,
    option_config_root,
    option_db_filepath,
    option_dev,
    option_dry_run,
    option_federated_only,
    option_force,
    option_light,
    option_min_stake,
    option_network,
    option_poa,
    option_eth_provider_uri,
    option_registry_filepath,
    option_signer_uri,
    option_teacher_uri,
    option_lonely,
    option_max_gas_price,
    option_key_material,
    option_payment_provider,
    option_payment_method,
    option_payment_network,
    option_policy_registry_filepath
)
from nucypher.cli.painting.help import paint_new_installation_help
from nucypher.cli.types import EIP55_CHECKSUM_ADDRESS, NETWORK_PORT, OPERATOR_IP
from nucypher.cli.utils import make_cli_character, setup_emitter
from nucypher.config.characters import UrsulaConfiguration
from nucypher.config.constants import (
    NUCYPHER_ENVVAR_OPERATOR_ETH_PASSWORD,
    TEMPORARY_DOMAIN
)
from nucypher.crypto.keystore import Keystore



class UrsulaConfigOptions:

    __option_name__ = 'config_options'

    def __init__(self,
                 eth_provider_uri: str,
                 operator_address: str,
                 federated_only: bool,
                 rest_host: str,
                 rest_port: int,
                 db_filepath: Path,
                 network: str,
                 registry_filepath: Path,
                 policy_registry_filepath: Path,
                 dev: bool,
                 poa: bool,
                 light: bool,
                 gas_strategy: str,
                 max_gas_price: int,  # gwei
                 signer_uri: str,
                 availability_check: bool,
                 lonely: bool,
                 payment_method: str,
                 payment_provider: str,
                 payment_network: str
                 ):

        if federated_only:
            if registry_filepath or policy_registry_filepath:
                raise click.BadOptionUsage(option_name="--registry-filepath",
                                           message=click.style("--registry-filepath and --policy-registry-filepath cannot be used in federated mode.", fg="red"))

        self.eth_provider_uri = eth_provider_uri
        self.signer_uri = signer_uri
        self.operator_address = operator_address
        self.federated_only = federated_only
        self.rest_host = rest_host
        self.rest_port = rest_port  # FIXME: not used in generate()
        self.db_filepath = db_filepath
        self.domain = network
        self.registry_filepath = registry_filepath
        self.policy_registry_filepath = policy_registry_filepath
        self.dev = dev
        self.poa = poa
        self.light = light
        self.gas_strategy = gas_strategy
        self.max_gas_price = max_gas_price
        self.availability_check = availability_check
        self.lonely = lonely
        self.payment_method = payment_method
        self.payment_provider = payment_provider
        self.payment_network = payment_network

    def create_config(self, emitter, config_file):
        if self.dev:
            return UrsulaConfiguration(
                emitter=emitter,
                dev_mode=True,
                domain=TEMPORARY_DOMAIN,
                poa=self.poa,
                light=self.light,
                registry_filepath=self.registry_filepath,
                policy_registry_filepath=self.policy_registry_filepath,
                eth_provider_uri=self.eth_provider_uri,
                signer_uri=self.signer_uri,
                gas_strategy=self.gas_strategy,
                max_gas_price=self.max_gas_price,
                checksum_address=self.operator_address,
                federated_only=self.federated_only,
                rest_host=self.rest_host,
                rest_port=self.rest_port,
                db_filepath=self.db_filepath,
                availability_check=self.availability_check,
                payment_method=self.payment_method,
                payment_provider=self.payment_provider,
                payment_network=self.payment_network
            )
        else:
            if not config_file:
                config_file = select_config_file(emitter=emitter,
                                                 checksum_address=self.operator_address,
                                                 config_class=UrsulaConfiguration)
            try:
                return UrsulaConfiguration.from_configuration_file(
                    emitter=emitter,
                    filepath=config_file,
                    domain=self.domain,
                    registry_filepath=self.registry_filepath,
                    policy_registry_filepath=self.policy_registry_filepath,
                    eth_provider_uri=self.eth_provider_uri,
                    signer_uri=self.signer_uri,
                    gas_strategy=self.gas_strategy,
                    max_gas_price=self.max_gas_price,
                    rest_host=self.rest_host,
                    rest_port=self.rest_port,
                    db_filepath=self.db_filepath,
                    poa=self.poa,
                    light=self.light,
                    federated_only=self.federated_only,
                    availability_check=self.availability_check,
                    payment_method=self.payment_method,
                    payment_provider=self.payment_provider,
                    payment_network=self.payment_network
                )
            except FileNotFoundError:
                return handle_missing_configuration_file(character_config_class=UrsulaConfiguration, config_file=config_file)
            except Keystore.AuthenticationFailed as e:
                emitter.error(str(e))
                # TODO: Exit codes (not only for this, but for other exceptions)
                return click.get_current_context().exit(1)

    def generate_config(self, emitter, config_root, force, key_material):

        if self.dev:
            raise RuntimeError('Persistent configurations cannot be created in development mode.')

        if (not self.operator_address) and not self.federated_only:
            prompt = "Select operator account"
            self.operator_address = select_client_account(emitter=emitter,
                                                          prompt=prompt,
                                                          eth_provider_uri=self.eth_provider_uri,
                                                          signer_uri=self.signer_uri)

        # Resolve rest host
        if not self.rest_host:
            self.rest_host = collect_operator_ip_address(emitter, network=self.domain, force=force)

        return UrsulaConfiguration.generate(password=get_nucypher_password(emitter=emitter, confirm=True),
                                            key_material=bytes.fromhex(key_material) if key_material else None,
                                            config_root=config_root,
                                            rest_host=self.rest_host,
                                            rest_port=self.rest_port,
                                            db_filepath=self.db_filepath,
                                            domain=self.domain,
                                            federated_only=self.federated_only,
                                            operator_address=self.operator_address,
                                            registry_filepath=self.registry_filepath,
                                            policy_registry_filepath=self.policy_registry_filepath,
                                            eth_provider_uri=self.eth_provider_uri,
                                            signer_uri=self.signer_uri,
                                            gas_strategy=self.gas_strategy,
                                            max_gas_price=self.max_gas_price,
                                            poa=self.poa,
                                            light=self.light,
                                            availability_check=self.availability_check,
                                            payment_method=self.payment_method,
                                            payment_provider=self.payment_provider,
                                            payment_network=self.payment_network
                                            )

    def get_updates(self) -> dict:
        payload = dict(rest_host=self.rest_host,
                       rest_port=self.rest_port,
                       db_filepath=self.db_filepath,
                       domain=self.domain,
                       federated_only=self.federated_only,
                       operator_address=self.operator_address,
                       registry_filepath=self.registry_filepath,
                       policy_registry_filepath=self.policy_registry_filepath,
                       eth_provider_uri=self.eth_provider_uri,
                       signer_uri=self.signer_uri,
                       gas_strategy=self.gas_strategy,
                       max_gas_price=self.max_gas_price,
                       poa=self.poa,
                       light=self.light,
                       availability_check=self.availability_check,
                       payment_method=self.payment_method,
                       payment_provider=self.payment_provider,
                       payment_network=self.payment_network
                       )
        # Depends on defaults being set on Configuration classes, filtrates None values
        updates = {k: v for k, v in payload.items() if v is not None}
        return updates


group_config_options = group_options(
    # NOTE: Don't set defaults here or they will be applied to config updates. Use the Config API.
    UrsulaConfigOptions,
    eth_provider_uri=option_eth_provider_uri(),
    signer_uri=option_signer_uri,
    gas_strategy=option_gas_strategy,
    max_gas_price=option_max_gas_price,
    operator_address=click.option('--operator-address', help="Run with the specified operator address", type=EIP55_CHECKSUM_ADDRESS),
    federated_only=option_federated_only,
    rest_host=click.option('--rest-host', help="The host IP address to run Ursula network services on", type=OPERATOR_IP),
    rest_port=click.option('--rest-port', help="The host port to run Ursula network services on", type=NETWORK_PORT),
    db_filepath=option_db_filepath,
    network=option_network(),
    registry_filepath=option_registry_filepath,
    policy_registry_filepath=option_policy_registry_filepath,
    poa=option_poa,
    light=option_light,
    dev=option_dev,
    availability_check=click.option('--availability-check/--disable-availability-check', help="Enable or disable self-health checks while running", is_flag=True, default=None),
    lonely=option_lonely,
    payment_provider=option_payment_provider,
    payment_network=option_payment_network,
    payment_method=option_payment_method,
)


class UrsulaCharacterOptions:

    __option_name__ = 'character_options'

    def __init__(self, config_options: UrsulaConfigOptions, teacher_uri, min_stake):
        self.config_options = config_options
        self.teacher_uri = teacher_uri
        self.min_stake = min_stake

    def create_character(self, emitter, config_file, json_ipc, load_seednodes=True):
        ursula_config = self.config_options.create_config(emitter, config_file)
        is_clef = ClefSigner.is_valid_clef_uri(self.config_options.signer_uri)
        password_required = all((not ursula_config.federated_only,
                                 not self.config_options.dev,
                                 not json_ipc,
                                 not is_clef))
        __password = None
        if password_required:
            __password = get_client_password(checksum_address=ursula_config.operator_address,
                                             envvar=NUCYPHER_ENVVAR_OPERATOR_ETH_PASSWORD)

        try:
            URSULA = make_cli_character(character_config=ursula_config,
                                        emitter=emitter,
                                        min_stake=self.min_stake,
                                        teacher_uri=self.teacher_uri,
                                        unlock_keystore=not self.config_options.dev,
                                        client_password=__password,
                                        unlock_signer=False,  # Ursula's unlock is managed separately using client_password.
                                        lonely=self.config_options.lonely,
                                        start_learning_now=load_seednodes,
                                        json_ipc=json_ipc)
            return ursula_config, URSULA

        except Keystore.AuthenticationFailed as e:
            emitter.error(str(e))
            # TODO: Exit codes (not only for this, but for other exceptions)
            return click.get_current_context().exit(1)


group_character_options = group_options(
    UrsulaCharacterOptions,
    config_options=group_config_options,
    teacher_uri=option_teacher_uri,
    min_stake=option_min_stake
)


@click.group()
def ursula():
    """"Ursula the Untrusted" PRE Re-encryption node management commands."""


@ursula.command()
@group_config_options
@option_force
@option_config_root
@group_general_config
@option_key_material
def init(general_config, config_options, force, config_root, key_material):
    """Create a new Ursula node configuration."""
    emitter = setup_emitter(general_config, config_options.operator_address)
    _pre_launch_warnings(emitter, dev=None, force=force)
    if not config_root:
        config_root = general_config.config_root
    if not config_options.federated_only and not config_options.eth_provider_uri:
        raise click.BadOptionUsage('--eth-provider', message=click.style("--eth-provider is required to initialize a new ursula.", fg="red"))
    if not config_options.federated_only and not config_options.payment_provider:
        raise click.BadOptionUsage('--payment-provider', message=click.style("--payment-provider is required to initialize a new ursula.", fg="red"))
    if not config_options.federated_only and not config_options.domain:
        config_options.domain = select_network(emitter, message="Select Staking Network", network_type=NetworksInventory.ETH)
    if not config_options.federated_only and not config_options.payment_network:
        config_options.payment_network = select_network(emitter, message="Select Payment Network", network_type=NetworksInventory.POLYGON)
    ursula_config = config_options.generate_config(emitter=emitter,
                                                   config_root=config_root,
                                                   force=force,
                                                   key_material=key_material)
    filepath = ursula_config.to_configuration_file()
    paint_new_installation_help(emitter, new_configuration=ursula_config, filepath=filepath)


@ursula.command()
@group_config_options
@group_general_config
def recover(general_config, config_options):
    # TODO: Combine with work in PR #2682
    # TODO: Integrate regeneration of configuration files
    emitter = setup_emitter(general_config, config_options.operator_address)
    recover_keystore(emitter=emitter)


@ursula.command()
@group_config_options
@option_config_file
@option_force
@group_general_config
def destroy(general_config, config_options, config_file, force):
    """Delete Ursula node configuration."""
    emitter = setup_emitter(general_config, config_options.operator_address)
    _pre_launch_warnings(emitter, dev=config_options.dev, force=force)
    ursula_config = config_options.create_config(emitter, config_file)
    destroy_configuration(emitter, character_config=ursula_config, force=force)


@ursula.command()
@group_config_options
@option_config_file
@group_general_config
def forget(general_config, config_options, config_file):
    """Forget all known nodes."""
    emitter = setup_emitter(general_config, config_options.operator_address)
    _pre_launch_warnings(emitter, dev=config_options.dev, force=None)
    ursula_config = config_options.create_config(emitter, config_file)
    forget_nodes(emitter, configuration=ursula_config)


@ursula.command()
@group_character_options
@option_config_file
@option_dry_run
@option_force
@group_general_config
@click.option('--interactive', '-I', help="Run interactively", is_flag=True, default=False)
@click.option('--prometheus', help="Run the ursula prometheus exporter", is_flag=True, default=False)
@click.option('--metrics-port', help="Run a Prometheus metrics exporter on specified HTTP port", type=NETWORK_PORT)
@click.option("--metrics-listen-address", help="Run a prometheus metrics exporter on specified IP address", default='')
@click.option("--metrics-prefix", help="Create metrics params with specified prefix", default="ursula")
@click.option("--metrics-interval", help="The frequency of metrics collection", type=click.INT, default=90)
@click.option("--ip-checkup/--no-ip-checkup", help="Verify external IP matches configuration", default=True)
def run(general_config, character_options, config_file, interactive, dry_run, prometheus, metrics_port,
        metrics_listen_address, metrics_prefix, metrics_interval, force, ip_checkup):
    """Run an "Ursula" node."""

    emitter = setup_emitter(general_config)
    dev_mode = character_options.config_options.dev
    lonely = character_options.config_options.lonely

    # TODO re-add prometheus logic once prometheus functionality is revamped for Threshold (#2928)
    if prometheus:
        raise click.BadOptionUsage(
            option_name="prometheus",
            message=click.style(
                "prometheus is not currently supported "
                "in this version as part of the merge to "
                "the Threshold Network; it will be in a "
                "future version",
                fg="red"
            )
        )
    # if prometheus and not metrics_port:
    #     # Require metrics port when using prometheus
    #     raise click.BadOptionUsage(option_name='metrics-port',
    #                                message=click.style('--metrics-port is required when using --prometheus', fg="red"))

    _pre_launch_warnings(emitter, dev=dev_mode, force=None)

    prometheus_config: 'PrometheusMetricsConfig' = None
    # if prometheus and not dev_mode:
    #     # Locally scoped to prevent import without prometheus explicitly installed
    #     from nucypher.utilities.prometheus.metrics import PrometheusMetricsConfig
    #     prometheus_config = PrometheusMetricsConfig(port=metrics_port,
    #                                                 metrics_prefix=metrics_prefix,
    #                                                 listen_address=metrics_listen_address,
    #                                                 collection_interval=metrics_interval)

    ursula_config, URSULA = character_options.create_character(emitter=emitter,
                                                               config_file=config_file,
                                                               json_ipc=general_config.json_ipc)

    if ip_checkup and not (dev_mode or lonely):
        # Always skip startup IP checks for dev and lonely modes.
        perform_startup_ip_check(emitter=emitter, ursula=URSULA, force=force)

    try:
        URSULA.run(emitter=emitter,
                   start_reactor=not dry_run,
                   interactive=interactive,
                   prometheus_config=prometheus_config,
                   preflight=not dev_mode)
    finally:
        if dry_run:
            URSULA.stop()


@ursula.command(name='save-metadata')
@group_character_options
@option_config_file
@group_general_config
def save_metadata(general_config, character_options, config_file):
    """Manually write node metadata to disk without running."""
    emitter = setup_emitter(general_config, character_options.config_options.operator_address)
    _pre_launch_warnings(emitter, dev=character_options.config_options.dev, force=None)
    _, URSULA = character_options.create_character(emitter, config_file, general_config.json_ipc, load_seednodes=False)
    metadata_path = URSULA.write_node_metadata(node=URSULA)
    emitter.message(SUCCESSFUL_MANUALLY_SAVE_METADATA.format(metadata_path=metadata_path), color='green')


@ursula.command()
@click.argument('action', required=False)
@group_config_options
@option_config_file
@group_general_config
@option_force
def config(general_config, config_options, config_file, force, action):
    """
    View and optionally update the Ursula node's configuration.

    \b
    Sub-Commands
    ~~~~~~~~~~~~~
    ip-address - automatically detect and configure the external IP address.

    """
    emitter = setup_emitter(general_config, config_options.operator_address)
    if not config_file:
        config_file = select_config_file(emitter=emitter,
                                         checksum_address=config_options.operator_address,
                                         config_class=UrsulaConfiguration)
    if action == 'ip-address':
        rest_host = collect_operator_ip_address(emitter=emitter, network=config_options.domain, force=force)
        config_options.rest_host = rest_host
    elif action:
        emitter.error(f'"{action}" is not a valid command.')
        raise click.Abort()
    updates = config_options.get_updates()
    get_or_update_configuration(emitter=emitter,
                                config_class=UrsulaConfiguration,
                                filepath=config_file,
                                updates=updates)


def _pre_launch_warnings(emitter, dev, force):
    if dev:
        emitter.echo(DEVELOPMENT_MODE_WARNING, color='yellow', verbosity=1)
    if force:
        emitter.echo(FORCE_MODE_WARNING, color='yellow', verbosity=1)
