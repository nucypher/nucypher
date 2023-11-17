import functools
from collections import namedtuple
from pathlib import Path
from typing import Sequence

import click

from nucypher.blockchain.eth.constants import TACO_CONTRACT_NAMES
from nucypher.cli.types import (
    EXISTING_READABLE_FILE,
    GWEI,
    MIN_AUTHORIZATION,
    PRE_PAYMENT_METHOD_CHOICES,
    STAKED_TOKENS_RANGE,
    NuCypherDomainName,
)

# Alphabetical

option_config_file = click.option(
    "--config-file", help="Path to configuration file", type=EXISTING_READABLE_FILE
)
option_config_root = click.option(
    "--config-root",
    help="Custom configuration directory",
    type=click.Path(path_type=Path),
)
option_dev = click.option("--dev", "-d", help="Enable development mode", is_flag=True)
option_dry_run = click.option(
    "--dry-run",
    "-x",
    help="Execute normally without actually starting the node",
    is_flag=True,
)
option_event_name = click.option(
    "--event-name", help="Specify an event by name", type=click.STRING
)
option_force = click.option("--force", help="Don't ask for confirmation", is_flag=True)
option_gas_strategy = click.option(
    "--gas-strategy",
    help="Operate with a specified gas price strategy",
    type=click.STRING,
)  # TODO: GAS_STRATEGY_CHOICES
option_key_material = click.option(
    "--key-material",
    help="A pre-secured hex-encoded secret to use for private key derivations",
    type=click.STRING,
)
option_max_gas_price = click.option(
    "--max-gas-price", help="Maximum acceptable gas price (in GWEI)", type=GWEI
)
option_light = click.option(
    "--light", help="Indicate that node is light", is_flag=True, default=None
)
option_lonely = click.option(
    "--lonely", help="Do not connect to seednodes", is_flag=True
)
option_min_stake = click.option(
    "--min-stake",
    help="The minimum stake the teacher must have to be locally accepted.",
    type=STAKED_TOKENS_RANGE,
    default=MIN_AUTHORIZATION,
)
option_polygon_endpoint = click.option(
    "--polygon-endpoint",
    "polygon_endpoint",
    help="Connection URL for Polygon chain",
    type=click.STRING,
    required=False,
)
option_pre_payment_method = click.option(
    "--pre-payment-method",
    help="PRE payment method name",
    type=PRE_PAYMENT_METHOD_CHOICES,
    required=False,
)
option_poa = click.option(
    "--poa/--disable-poa", help="Inject POA middleware", is_flag=True, default=None
)
option_registry_filepath = click.option(
    "--registry-filepath",
    help="Custom contract registry filepath",
    type=EXISTING_READABLE_FILE,
)
option_signer_uri = click.option("--signer", "signer_uri", "-S", default=None, type=str)
option_teacher_uri = click.option(
    "--teacher",
    "teacher_uri",
    help="An Ursula URI to start learning from (seednode)",
    type=click.STRING,
)
_option_middleware = click.option(
    "-Z",
    "--mock-networking",
    help="Use in-memory transport instead of networking",
    count=True,
)

#
# Alphabetical
#

def option_contract_name(
    required: bool = False, valid_options: Sequence[str] = TACO_CONTRACT_NAMES
):
    return click.option(
        '--contract-name',
        help="Specify a single contract by name",
        type=click.Choice(valid_options),
        required=required
    )


def option_domain(
    required: bool = False,
    default: str = None,  # nucypher.blockchain.eth.domains.DEFAULT.name is not a good global default (#2214)
    validate: bool = False,
):
    return click.option(
        "--domain",
        help="TACo Domain Name",
        type=NuCypherDomainName(validate=validate),
        required=required,
        default=default)


def option_eth_endpoint(default=None, required: bool = False):
    return click.option(
        "--eth-endpoint",
        "eth_endpoint",
        help="Blockchain provider's URI i.e. 'file:///path/to/geth.ipc'",
        type=click.STRING,
        required=required,
        default=default
    )


def group_options(option_class, **options):
    argnames = sorted(list(options.keys()))
    decorators = list(options.values())

    if isinstance(option_class, str):
        option_name = option_class
        option_class = namedtuple(option_class, argnames)
    else:
        option_name = option_class.__option_name__

    def _decorator(func):

        @functools.wraps(func)
        def wrapper(**kwargs):
            to_group = {}
            for name in argnames:
                if name not in kwargs:
                    raise ValueError(
                        f"When trying to group CLI options into {option_name}, "
                        f"{name} was not found among arguments")
                to_group[name] = kwargs[name]
                del kwargs[name]

            kwargs[option_name] = option_class(**to_group)
            return func(**kwargs)

        for dec in decorators:
            wrapper = dec(wrapper)

        return wrapper

    return _decorator
