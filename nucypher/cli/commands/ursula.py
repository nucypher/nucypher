from pathlib import Path

import click

from nucypher.cli.actions.auth import (
    get_wallet_password,
    get_nucypher_password,
    recover_keystore,
)
from nucypher.cli.actions.configure import (
    collect_operator_ip_address,
    destroy_configuration,
    get_or_update_configuration,
    handle_missing_configuration_file,
    perform_startup_ip_check,
)
from nucypher.cli.actions.select import (
    select_domain,
)
from nucypher.cli.config import group_general_config
from nucypher.cli.literature import (
    DEVELOPMENT_MODE_WARNING,
    FORCE_MODE_WARNING,
)
from nucypher.cli.options import (
    group_options,
    option_config_file,
    option_config_root,
    option_dev,
    option_domain,
    option_dry_run,
    option_eth_endpoint,
    option_force,
    option_gas_strategy,
    option_key_material,
    option_light,
    option_lonely,
    option_max_gas_price,
    option_poa,
    option_polygon_endpoint,
    option_pre_payment_method,
    option_registry_filepath,
    option_peer_uri,
)
from nucypher.cli.painting.help import paint_new_installation_help
from nucypher.cli.types import NETWORK_PORT, OPERATOR_IP
from nucypher.cli.utils import make_cli_character, setup_emitter
from nucypher.config.characters import UrsulaConfiguration
from nucypher.config.constants import (
    NUCYPHER_ENVVAR_OPERATOR_ETH_PASSWORD,
    TEMPORARY_DOMAIN_NAME,
    DEFAULT_CONFIG_ROOT,
)
from nucypher.config.migrations import MIGRATIONS
from nucypher.config.migrations.common import (
    InvalidMigration,
    WrongConfigurationVersion,
)
from nucypher.crypto.keystore import Keystore
from nucypher.utilities.prometheus.metrics import PrometheusMetricsConfig

DEFAULT_CONFIG_FILEPATH = DEFAULT_CONFIG_ROOT / "ursula.json"


class UrsulaConfigOptions:

    __option_name__ = "config_options"

    def __init__(
        self,
        eth_endpoint: str,
        rest_host: str,
        rest_port: int,
        domain: str,
        registry_filepath: Path,
        dev: bool,
        poa: bool,
        light: bool,
        gas_strategy: str,
        max_gas_price: int,  # gwei
        wallet_filepath: Path,
        lonely: bool,
        polygon_endpoint: str,
        pre_payment_method: str,
    ):

        self.eth_endpoint = eth_endpoint
        self.wallet_filepath = wallet_filepath
        self.rest_host = rest_host
        self.rest_port = rest_port  # FIXME: not used in generate()
        self.domain = domain
        self.registry_filepath = registry_filepath
        self.dev = dev
        self.poa = poa
        self.light = light
        self.gas_strategy = gas_strategy
        self.max_gas_price = max_gas_price
        self.lonely = lonely
        self.pre_payment_method = pre_payment_method
        self.polygon_endpoint = polygon_endpoint

    def create_config(self, emitter, config_file):
        if self.dev:
            return UrsulaConfiguration(
                emitter=emitter,
                dev_mode=True,
                domain=TEMPORARY_DOMAIN_NAME,
                registry_filepath=self.registry_filepath,
                eth_endpoint=self.eth_endpoint,
                wallet_filepath=UrsulaConfiguration.DEFAULT_WALLET_FILEPATH,
                gas_strategy=self.gas_strategy,
                max_gas_price=self.max_gas_price,
                rest_host=self.rest_host,
                rest_port=self.rest_port,
                pre_payment_method=self.pre_payment_method,
                polygon_endpoint=self.polygon_endpoint,
            )
        else:
            if not config_file:
                config_file = DEFAULT_CONFIG_FILEPATH
            try:
                return UrsulaConfiguration.from_configuration_file(
                    emitter=emitter,
                    filepath=config_file,
                    domain=self.domain,
                    registry_filepath=self.registry_filepath,
                    eth_endpoint=self.eth_endpoint,
                    wallet_filepath=self.wallet_filepath,
                    gas_strategy=self.gas_strategy,
                    max_gas_price=self.max_gas_price,
                    rest_host=self.rest_host,
                    rest_port=self.rest_port,
                    pre_payment_method=self.pre_payment_method,
                    polygon_endpoint=self.polygon_endpoint,
                )
            except FileNotFoundError:
                return handle_missing_configuration_file(character_config_class=UrsulaConfiguration, config_file=config_file)
            except Keystore.AuthenticationFailed as e:
                emitter.error(str(e))
                # TODO: Exit codes (not only for this, but for other exceptions)
                return click.get_current_context().exit(1)

    @staticmethod
    def _check_for_existing_config(self, config_root, force):
        if not config_root:
            config_root = Path(DEFAULT_CONFIG_ROOT)
        existing_config_files = config_root.exists() and any(config_root.iterdir())
        if existing_config_files and not force:
            raise click.FileError(
                str(config_root),
                hint="There is an existing configuration at the default location. "
                     "Use --config-root to specify a custom location or use --force to "
                     "overwrite existing configuration.",
            )

    def generate_config(self, emitter, config_root, force, key_material):

        self._check_for_existing_config(self, config_root, force)
        if self.dev:
            raise RuntimeError(
                "Persistent configurations cannot be created in development mode."
            )

        # Resolve rest host
        if not self.rest_host:
            self.rest_host = collect_operator_ip_address(
                emitter,
                domain=self.domain,
                force=force,
                eth_endpoint=self.eth_endpoint,
            )

        return UrsulaConfiguration.generate(
            key_material=bytes.fromhex(key_material) if key_material else None,
            keystore_password=get_nucypher_password(emitter=emitter, confirm=True),
            wallet_password=get_wallet_password(envvar=NUCYPHER_ENVVAR_OPERATOR_ETH_PASSWORD, confirm=True),
            wallet_filepath=self.wallet_filepath,
            config_root=config_root,
            rest_host=self.rest_host,
            rest_port=self.rest_port,
            domain=self.domain,
            registry_filepath=self.registry_filepath,
            eth_endpoint=self.eth_endpoint,
            gas_strategy=self.gas_strategy,
            max_gas_price=self.max_gas_price,
            pre_payment_method=self.pre_payment_method,
            polygon_endpoint=self.polygon_endpoint,
        )

    def get_updates(self) -> dict:
        payload = dict(
            rest_host=self.rest_host,
            rest_port=self.rest_port,
            domain=self.domain,
            registry_filepath=self.registry_filepath,
            eth_endpoint=self.eth_endpoint,
            wallet_filepath=self.wallet_filepath,
            gas_strategy=self.gas_strategy,
            max_gas_price=self.max_gas_price,
            polygon_endpoint=self.polygon_endpoint,
        )
        # Depends on defaults being set on Configuration classes, filtrates None values
        updates = {k: v for k, v in payload.items() if v is not None}
        return updates


group_config_options = group_options(
    # NOTE: Don't set defaults here or they will be applied to config updates. Use the Config API.
    UrsulaConfigOptions,
    eth_endpoint=option_eth_endpoint(),
    wallet_filepath=click.option(
        "--wallet-filepath", "-w",
        help="The filepath to an encrypted ethereum software wallet in web3 secret storage format.",
        type=click.Path(exists=True, file_okay=True, dir_okay=False, readable=True),
    ),
    gas_strategy=option_gas_strategy,
    max_gas_price=option_max_gas_price,
    rest_host=click.option(
        "--rest-host",
        help="The host IP address to run Ursula network services on",
        type=OPERATOR_IP,
    ),
    rest_port=click.option(
        "--rest-port",
        help="The host port to run Ursula network services on",
        type=NETWORK_PORT,
    ),
    domain=option_domain(),
    registry_filepath=option_registry_filepath,
    poa=option_poa,
    light=option_light,
    dev=option_dev,
    lonely=option_lonely,
    polygon_endpoint=option_polygon_endpoint,
    pre_payment_method=option_pre_payment_method,
)


class UrsulaCharacterOptions:

    __option_name__ = 'character_options'

    def __init__(self, config_options: UrsulaConfigOptions, peer_uri):
        self.config_options = config_options
        self.peer_uri = peer_uri

    def create_character(self, emitter, config_file):
        ursula_config = self.config_options.create_config(emitter, config_file)

        try:
            URSULA = make_cli_character(
                character_config=ursula_config,
                emitter=emitter,
                eth_endpoint=ursula_config.eth_endpoint,
                peer_uri=self.peer_uri,
                unlock=not self.config_options.dev,
                lonely=self.config_options.lonely,
            )
            return ursula_config, URSULA

        except Keystore.AuthenticationFailed as e:
            emitter.error(str(e))
            # TODO: Exit codes (not only for this, but for other exceptions)
            return click.get_current_context().exit(1)


group_character_options = group_options(
    UrsulaCharacterOptions,
    config_options=group_config_options,
    peer_uri=option_peer_uri,
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
    emitter = setup_emitter(general_config)
    _pre_launch_warnings(emitter, dev=None, force=force)
    if not config_root:
        config_root = general_config.config_root
    if not config_options.eth_endpoint:
        raise click.BadOptionUsage(
            "--eth-endpoint",
            message=click.style(
                "--eth-endpoint is required to initialize a new ursula.", fg="red"
            ),
        )
    if not config_options.polygon_endpoint:
        raise click.BadOptionUsage(
            "--polygon-endpoint",
            message=click.style(
                "--polygon-endpoint is required to initialize a new ursula.",
                fg="red",
            ),
        )
    if not config_options.domain:
        config_options.domain = select_domain(
            emitter,
            message="Select TACo Domain",
        )
    ursula_config = config_options.generate_config(
        emitter=emitter, config_root=config_root, force=force, key_material=key_material
    )
    filepath = ursula_config.to_configuration_file()
    paint_new_installation_help(
        emitter, new_configuration=ursula_config, filepath=filepath
    )


@ursula.command()
@group_config_options
@group_general_config
def recover(general_config, config_options):
    # TODO: Combine with work in PR #2682
    # TODO: Integrate regeneration of configuration files
    emitter = setup_emitter(general_config, )
    recover_keystore(emitter=emitter)


@ursula.command()
@group_config_options
@option_config_file
@option_force
@group_general_config
def destroy(general_config, config_options, config_file, force):
    """Delete Ursula node configuration."""
    emitter = setup_emitter(general_config, )
    _pre_launch_warnings(emitter, dev=config_options.dev, force=force)
    ursula_config = config_options.create_config(emitter, config_file)
    destroy_configuration(emitter, character_config=ursula_config, force=force)


@ursula.command()
@group_character_options
@option_config_file
@option_dry_run
@option_force
@group_general_config
@click.option(
    "--prometheus",
    help="Enable the prometheus metrics exporter",
    is_flag=True,
    default=False,
)
@click.option(
    "--metrics-port",
    help="Specify the HTTP port of the Prometheus metrics exporter (if prometheus enabled)",
    default=9101,
    type=NETWORK_PORT,
)
@click.option(
    "--metrics-interval",
    help="The frequency of metrics collection in seconds (if prometheus enabled)",
    type=click.INT,
    default=90,
)
@click.option(
    "--ip-checkup/--no-ip-checkup",
    help="Verify external IP matches configuration",
    default=True,
)
def run(
    general_config,
    character_options,
    config_file,
    dry_run,
    prometheus,
    metrics_port,
    metrics_interval,
    force,
    ip_checkup,
):
    """Run an "Ursula" node."""

    emitter = setup_emitter(general_config)
    dev_mode = character_options.config_options.dev
    lonely = character_options.config_options.lonely

    _pre_launch_warnings(emitter, dev=dev_mode, force=None)

    prometheus_config = None
    if prometheus:
        prometheus_config = PrometheusMetricsConfig(
            port=metrics_port, collection_interval=metrics_interval
        )

    ursula_config, URSULA = character_options.create_character(
        emitter=emitter, config_file=config_file,
    )

    if ip_checkup and not (dev_mode or lonely):
        # Always skip startup IP checks for dev and lonely modes.
        perform_startup_ip_check(emitter=emitter, ursula=URSULA, force=force)

    try:
        URSULA.run(emitter=emitter,
                   start_reactor=not dry_run,
                   prometheus_config=prometheus_config,
                   preflight=not dev_mode)
    finally:
        if dry_run:
            URSULA.stop()


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
    emitter = setup_emitter(general_config, )
    if action == "ip-address":
        rest_host = collect_operator_ip_address(
            emitter=emitter,
            domain=config_options.domain,
            force=force,
            eth_endpoint=config_options.eth_endpoint,
        )
        config_options.rest_host = rest_host
    updates = config_options.get_updates()
    get_or_update_configuration(emitter=emitter,
                                config_class=UrsulaConfiguration,
                                filepath=config_file,
                                updates=updates)


@ursula.command()
@group_config_options
@option_config_file
@group_general_config
def migrate(general_config, config_options, config_file):
    emitter = setup_emitter(general_config, )

    for jump, migration in MIGRATIONS.items():
        old, new = jump
        emitter.message(f"Checking migration {old} -> {new}")
        if not migration:
            emitter.echo(
                f"Migration {old} -> {new} not found.",
                color="yellow",
                verbosity=1,
            )
            continue  # no migration script
        try:
            migration(config_file)
            emitter.echo(
                f"Successfully ran migration {old} -> {new}",
                color="green",
                verbosity=1,
            )

        except WrongConfigurationVersion:
            emitter.echo(
                f"Migration {old} -> {new} not required.",
                color="yellow",
                verbosity=1,
            )
            continue  # already migrated

        except InvalidMigration as e:
            emitter.error(f"Migration {old} -> {new} failed: {str(e)}")
            return click.Abort()


def _pre_launch_warnings(emitter, dev, force):
    if dev:
        emitter.echo(DEVELOPMENT_MODE_WARNING, color='yellow', verbosity=1)
    if force:
        emitter.echo(FORCE_MODE_WARNING, color='yellow', verbosity=1)
