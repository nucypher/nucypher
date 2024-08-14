from pathlib import Path

import click

from nucypher.cli.actions.auth import (
    collect_mnemonic,
    get_client_password,
    get_nucypher_password,
    recover_keystore,
)
from nucypher.cli.actions.configure import (
    collect_operator_ip_address,
    destroy_configuration,
    get_or_update_configuration,
    handle_missing_configuration_file,
    perform_startup_ip_check,
    update_config_keystore_path,
)
from nucypher.cli.actions.migrate import migrate
from nucypher.cli.actions.select import (
    select_client_account,
    select_config_file,
    select_domain,
)
from nucypher.cli.config import group_general_config
from nucypher.cli.literature import (
    DEVELOPMENT_MODE_WARNING,
    FORCE_MODE_WARNING,
    SELECT_OPERATOR_ACCOUNT,
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
    option_min_stake,
    option_poa,
    option_polygon_endpoint,
    option_pre_payment_method,
    option_registry_filepath,
    option_signer_uri,
    option_teacher_uri,
)
from nucypher.cli.painting.help import paint_new_installation_help
from nucypher.cli.types import (
    EIP55_CHECKSUM_ADDRESS,
    EXISTING_READABLE_FILE,
    NETWORK_PORT,
    OPERATOR_IP,
)
from nucypher.cli.utils import make_cli_character, setup_emitter
from nucypher.config.characters import UrsulaConfiguration
from nucypher.config.constants import (
    DEFAULT_CONFIG_FILEPATH,
    NUCYPHER_ENVVAR_OPERATOR_ETH_PASSWORD,
    TEMPORARY_DOMAIN_NAME,
)
from nucypher.crypto.keystore import Keystore
from nucypher.crypto.powers import RitualisticPower
from nucypher.utilities.emitters import StdoutEmitter
from nucypher.utilities.prometheus.metrics import PrometheusMetricsConfig


class UrsulaConfigOptions:

    __option_name__ = "config_options"

    def __init__(
        self,
        eth_endpoint: str,
        operator_address: str,
        rest_host: str,
        rest_port: int,
        domain: str,
        registry_filepath: Path,
        dev: bool,
        poa: bool,
        light: bool,
        gas_strategy: str,
        max_gas_price: int,  # gwei
        signer_uri: str,
        lonely: bool,
        polygon_endpoint: str,
        pre_payment_method: str,
    ):

        self.eth_endpoint = eth_endpoint
        self.signer_uri = signer_uri
        self.operator_address = operator_address
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
                poa=self.poa,
                light=self.light,
                registry_filepath=self.registry_filepath,
                eth_endpoint=self.eth_endpoint,
                signer_uri=self.signer_uri,
                gas_strategy=self.gas_strategy,
                max_gas_price=self.max_gas_price,
                operator_address=self.operator_address,
                rest_host=self.rest_host,
                rest_port=self.rest_port,
                pre_payment_method=self.pre_payment_method,
                polygon_endpoint=self.polygon_endpoint,
            )
        else:
            if not config_file:
                config_file = select_config_file(
                    emitter=emitter,
                    checksum_address=self.operator_address,
                    config_class=UrsulaConfiguration,
                    do_auto_migrate=True,
                )
            else:
                # config file specified
                migrate(emitter=emitter, config_file=config_file)

            try:
                return UrsulaConfiguration.from_configuration_file(
                    emitter=emitter,
                    filepath=config_file,
                    domain=self.domain,
                    registry_filepath=self.registry_filepath,
                    eth_endpoint=self.eth_endpoint,
                    signer_uri=self.signer_uri,
                    gas_strategy=self.gas_strategy,
                    max_gas_price=self.max_gas_price,
                    rest_host=self.rest_host,
                    rest_port=self.rest_port,
                    poa=self.poa,
                    light=self.light,
                    pre_payment_method=self.pre_payment_method,
                    polygon_endpoint=self.polygon_endpoint,
                )
            except FileNotFoundError:
                return handle_missing_configuration_file(character_config_class=UrsulaConfiguration, config_file=config_file)
            except Keystore.AuthenticationFailed as e:
                emitter.error(str(e))
                # TODO: Exit codes (not only for this, but for other exceptions)
                return click.get_current_context().exit(1)

    def generate_config(self, emitter, config_root, force, key_material, with_mnemonic):

        if self.dev:
            raise RuntimeError(
                "Persistent configurations cannot be created in development mode."
            )

        if not self.operator_address:
            prompt = SELECT_OPERATOR_ACCOUNT
            self.operator_address = select_client_account(
                emitter=emitter,
                prompt=prompt,
                domain=self.domain,
                polygon_endpoint=self.polygon_endpoint,
                signer_uri=self.signer_uri,
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
            password=get_nucypher_password(emitter=emitter, confirm=True),
            key_material=bytes.fromhex(key_material) if key_material else None,
            with_mnemonic=with_mnemonic,
            config_root=config_root,
            rest_host=self.rest_host,
            rest_port=self.rest_port,
            domain=self.domain,
            operator_address=self.operator_address,
            registry_filepath=self.registry_filepath,
            eth_endpoint=self.eth_endpoint,
            signer_uri=self.signer_uri,
            gas_strategy=self.gas_strategy,
            max_gas_price=self.max_gas_price,
            poa=self.poa,
            light=self.light,
            pre_payment_method=self.pre_payment_method,
            polygon_endpoint=self.polygon_endpoint,
        )

    def get_updates(self) -> dict:
        payload = dict(
            rest_host=self.rest_host,
            rest_port=self.rest_port,
            domain=self.domain,
            operator_address=self.operator_address,
            registry_filepath=self.registry_filepath,
            eth_endpoint=self.eth_endpoint,
            signer_uri=self.signer_uri,
            gas_strategy=self.gas_strategy,
            max_gas_price=self.max_gas_price,
            poa=self.poa,
            light=self.light,
            pre_payment_method=self.pre_payment_method,
            polygon_endpoint=self.polygon_endpoint,
        )
        # Depends on defaults being set on Configuration classes, filtrates None values
        updates = {k: v for k, v in payload.items() if v is not None}
        return updates


group_config_options = group_options(
    # NOTE: Don't set defaults here or they will be applied to config updates. Use the Config API.
    UrsulaConfigOptions,
    eth_endpoint=option_eth_endpoint(),
    signer_uri=option_signer_uri,
    gas_strategy=option_gas_strategy,
    max_gas_price=option_max_gas_price,
    operator_address=click.option(
        "--operator-address",
        help="Run with the specified operator address",
        type=EIP55_CHECKSUM_ADDRESS,
    ),
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

    def __init__(self, config_options: UrsulaConfigOptions, teacher_uri, min_stake):
        self.config_options = config_options
        self.teacher_uri = teacher_uri
        self.min_stake = min_stake

    def create_character(self, emitter, config_file, json_ipc, load_seednodes=True):
        ursula_config = self.config_options.create_config(emitter, config_file)
        password_required = all((not self.config_options.dev, not json_ipc))
        __password = None
        if password_required:
            __password = get_client_password(
                checksum_address=ursula_config.operator_address,
                envvar=NUCYPHER_ENVVAR_OPERATOR_ETH_PASSWORD,
            )

        try:
            URSULA = make_cli_character(
                character_config=ursula_config,
                emitter=emitter,
                eth_endpoint=ursula_config.eth_endpoint,
                min_stake=self.min_stake,
                teacher_uri=self.teacher_uri,
                unlock_keystore=not self.config_options.dev,
                client_password=__password,
                unlock_signer=False,  # Ursula's unlock is managed separately using client_password.
                lonely=self.config_options.lonely,
                start_learning_now=load_seednodes,
                json_ipc=json_ipc,
            )
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
@click.option(
    "--with-mnemonic",
    help="Initialize with a mnemonic phrase instead of generating a new keypair from scratch",
    is_flag=True,
)
def init(
    general_config, config_options, force, config_root, key_material, with_mnemonic
):
    """Create a new Ursula node configuration."""
    emitter = setup_emitter(general_config, config_options.operator_address)
    _pre_launch_warnings(emitter, dev=None, force=force)

    if not config_root:
        config_root = general_config.config_root

    keystore_path = Path(config_root) / Keystore._DIR_NAME
    if keystore_path.exists() and any(keystore_path.iterdir()):
        click.clear()
        emitter.echo(
            f"There are existing secret keys in '{keystore_path}'.\n"
            "The 'init' command is a one-time operation, do not run it again.\n",
            color="red",
        )

        emitter.echo(
            "To review your existing configuration, run:\n\n"
            "nucypher ursula config\n\n"
            "To run your node with the existing configuration, run:\n\n"
            "nucypher ursula run\n",
            color="cyan",
        )
        return click.get_current_context().exit(1)

    click.clear()
    if with_mnemonic:
        emitter.echo(
            "Hello Operator, welcome back :-) \n\n"
            "You are about to initialize a new Ursula node configuration using an existing mnemonic phrase.\n"
            "Have your mnemonic phrase ready and ensure you are in a secure environment.\n"
            "Please follow the prompts.",
            color="cyan",
        )
    else:
        emitter.echo(
            "Hello Operator, welcome on board :-) \n\n"
            "NOTE: Initializing a new Ursula node configuration is a one-time operation\n"
            "for the lifetime of your node.  This is a two-step process:\n\n"
            "1. Creating a password to encrypt your operator keys\n"
            "2. Securing a taco node seed phase\n\n"
            "Please follow the prompts.",
            color="cyan",
        )

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
        emitter=emitter,
        config_root=config_root,
        force=force,
        key_material=key_material,
        with_mnemonic=with_mnemonic,
    )
    filepath = ursula_config.to_configuration_file()
    paint_new_installation_help(
        emitter, new_configuration=ursula_config, filepath=filepath
    )


@ursula.command()
@option_config_file
@click.option(
    "--keystore-filepath",
    help="Path to keystore .priv file",
    type=EXISTING_READABLE_FILE,
    required=False,
)
@click.option(
    "--view-mnemonic",
    help="View mnemonic seed words",
    is_flag=True,
)
def audit(config_file, keystore_filepath, view_mnemonic):
    """Audit a mnemonic phrase against a local keystore or view mnemonic seed words."""
    emitter = StdoutEmitter()
    if keystore_filepath and config_file:
        raise click.BadOptionUsage(
            "--keystore-filepath",
            message=click.style(
                "--keystore-filepath is incompatible with --config-file",
                fg="red",
            ),
        )

    config_file = config_file or DEFAULT_CONFIG_FILEPATH
    if not config_file.exists():
        emitter.error(f"Ursula configuration file not found - {config_file.absolute()}")
        raise click.Abort()

    if keystore_filepath:
        keystore = Keystore(keystore_filepath)
    else:
        ursula_config = UrsulaConfiguration.from_configuration_file(
            filepath=config_file
        )
        keystore = ursula_config.keystore

    password = get_nucypher_password(emitter=emitter, confirm=False)
    try:
        keystore.unlock(password=password)
    except Keystore.AuthenticationFailed:
        emitter.error("Password is incorrect.")
        raise click.Abort()

    emitter.message("Password is correct.", color="green")

    if view_mnemonic:
        mnemonic = keystore.get_mnemonic()
        emitter.message(f"\n{mnemonic}", color="cyan")
        return

    try:
        correct = keystore.audit(words=collect_mnemonic(emitter), password=password)
    except Keystore.InvalidMnemonic:
        emitter.message("Mnemonic is incorrect.", color="red")
        return
    emitter.message(
        f"Mnemonic is {'' if correct else 'in'}correct.",
        color="green" if correct else "red",
    )


@ursula.command()
@option_config_file
@click.option(
    "--keystore-filepath",
    help="Path to keystore .priv file",
    type=EXISTING_READABLE_FILE,
    required=False,
)
def recover(config_file, keystore_filepath):
    emitter = StdoutEmitter()
    if keystore_filepath and config_file:
        raise click.BadOptionUsage(
            "--keystore-filepath",
            message=click.style(
                "--keystore-filepath is incompatible with --config-file",
                fg="red",
            ),
        )
    config_file = config_file or DEFAULT_CONFIG_FILEPATH
    if not config_file.exists():
        emitter.error(f"Ursula configuration file not found - {config_file.absolute()}")
        click.Abort()
    keystore = recover_keystore(emitter=emitter)
    update_config_keystore_path(
        keystore_path=keystore.keystore_path, config_file=config_file
    )
    emitter.message(
        f"Updated {config_file} to use keystore filepath: {keystore.keystore_path}",
        color="green",
    )


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
@option_config_file
@click.option(
    "--keystore-filepath",
    help="Path to keystore .priv file",
    type=EXISTING_READABLE_FILE,
)
@click.option(
    "--from-mnemonic",
    help="View TACo public keys from mnemonic seed words",
    is_flag=True,
)
def public_keys(config_file, keystore_filepath, from_mnemonic):
    """Display the public keys of a keystore."""
    emitter = StdoutEmitter()

    if sum(1 for i in (keystore_filepath, config_file, from_mnemonic) if i) > 1:
        raise click.BadOptionUsage(
            "--keystore-filepath",
            message=click.style(
                "Exactly one of --keystore-filepath, --config-file, or --from-mnemonic must be specified",
                fg="red",
            ),
        )

    if from_mnemonic:
        keystore = Keystore.from_mnemonic(collect_mnemonic(emitter))
    else:
        config_file = config_file or DEFAULT_CONFIG_FILEPATH
        ursula_config = UrsulaConfiguration.from_configuration_file(
            filepath=config_file
        )
        keystore = Keystore(keystore_filepath or ursula_config.keystore.keystore_path)
        keystore.unlock(get_nucypher_password(emitter=emitter, confirm=False))

    ritualistic_power = keystore.derive_crypto_power(RitualisticPower)
    ferveo_public_key = bytes(ritualistic_power.public_key()).hex()
    emitter.message(f"\nFerveo Public Key: {ferveo_public_key}", color="cyan")


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
    "--metrics-listen-address",
    help="Run a Prometheus metrics exporter on the specified IP address",
    default="",
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
    metrics_listen_address,
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
            port=metrics_port,
            listen_address=metrics_listen_address,
            collection_interval=metrics_interval,
        )

    ursula_config, URSULA = character_options.create_character(
        emitter=emitter, config_file=config_file, json_ipc=general_config.json_ipc
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
    migrate    - migrate existing configuration file to the latest version.
    """
    emitter = setup_emitter(general_config, config_options.operator_address)

    if not config_file:
        if action == "migrate":
            # This is required because normally outdated configuration files
            # are excluded from interactive selection, making it impossible to
            # select a configuration file that is requires a migration.
            emitter.error(
                "--config-file <FILEPATH> is required to run a configuration file migration."
            )
            raise click.Abort()
        config_file = select_config_file(
            emitter=emitter,
            checksum_address=config_options.operator_address,
            config_class=UrsulaConfiguration,
        )
    if action == "ip-address":
        rest_host = collect_operator_ip_address(
            emitter=emitter,
            domain=config_options.domain,
            force=force,
            eth_endpoint=config_options.eth_endpoint,
        )
        config_options.rest_host = rest_host
    elif action == "migrate":
        migrate(emitter=emitter, config_file=config_file)
        return  # Don't run the rest of the command

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
