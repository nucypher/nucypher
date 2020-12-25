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


from collections import namedtuple

import click
import functools

from nucypher.blockchain.eth.constants import NUCYPHER_CONTRACT_NAMES
from nucypher.cli.types import (
    EIP55_CHECKSUM_ADDRESS,
    EXISTING_READABLE_FILE,
    GWEI,
    NETWORK_PORT,
    NuCypherNetworkName,
    WEI,
    STAKED_TOKENS_RANGE,
    MIN_ALLOWED_LOCKED_TOKENS
)
from nucypher.utilities.logging import Logger

# Alphabetical

option_checksum_address = click.option('--checksum-address', help="Run with a specified account", type=EIP55_CHECKSUM_ADDRESS)
option_config_file = click.option('--config-file', help="Path to configuration file", type=EXISTING_READABLE_FILE)
option_config_root = click.option('--config-root', help="Custom configuration directory", type=click.Path())
option_dev = click.option('--dev', '-d', help="Enable development mode", is_flag=True)
option_db_filepath = click.option('--db-filepath', help="The database filepath to connect to", type=click.STRING)
option_dry_run = click.option('--dry-run', '-x', help="Execute normally without actually starting the node", is_flag=True)
option_etherscan = click.option('--etherscan/--no-etherscan', help="Enable/disable viewing TX in Etherscan")
option_event_name = click.option('--event-name', help="Specify an event by name", type=click.STRING)
option_federated_only = click.option('--federated-only/--decentralized', '-F', help="Connect only to federated nodes", is_flag=True, default=None)
option_force = click.option('--force', help="Don't ask for confirmation", is_flag=True)
option_gas_price = click.option('--gas-price', help="Set a static gas price (in GWEI)", type=GWEI)
option_gas_strategy = click.option('--gas-strategy', help="Operate with a specified gas price strategy", type=click.STRING)  # TODO: GAS_STRATEGY_CHOICES
option_max_gas_price = click.option('--max-gas-price', help="Maximum acceptable gas price (in GWEI)", type=GWEI)
option_hw_wallet = click.option('--hw-wallet/--no-hw-wallet')
option_light = click.option('--light', help="Indicate that node is light", is_flag=True, default=None)
option_lonely = click.option('--lonely', help="Do not connect to seednodes", is_flag=True)
option_m = click.option('--m', help="M-Threshold KFrags", type=click.INT)
option_min_stake = click.option('--min-stake', help="The minimum stake the teacher must have to be locally accepted.", type=STAKED_TOKENS_RANGE, default=MIN_ALLOWED_LOCKED_TOKENS)
option_n = click.option('--n', help="N-Total KFrags", type=click.INT)
option_parameters = click.option('--parameters', help="Filepath to a JSON file containing additional parameters", type=EXISTING_READABLE_FILE)
option_participant_address = click.option('--participant-address', help="Participant's checksum address.", type=EIP55_CHECKSUM_ADDRESS)
option_poa = click.option('--poa/--disable-poa', help="Inject POA middleware", is_flag=True, default=None)
option_registry_filepath = click.option('--registry-filepath', help="Custom contract registry filepath", type=EXISTING_READABLE_FILE)
option_signer_uri = click.option('--signer', 'signer_uri', '-S', default=None, type=str)
option_staking_address = click.option('--staking-address', help="Address of a NuCypher staker", type=EIP55_CHECKSUM_ADDRESS)
option_teacher_uri = click.option('--teacher', 'teacher_uri', help="An Ursula URI to start learning from (seednode)", type=click.STRING)
_option_middleware = click.option('-Z', '--mock-networking', help="Use in-memory transport instead of networking", count=True)

# Avoid circular input
option_rate = click.option('--rate', help="Policy rate per period (in wei)", type=WEI)  # TODO: Is wei a sane unit here? Perhaps gwei?


#
# Alphabetical
#

def option_contract_name(required: bool = False):
    return click.option(
        '--contract-name',
        help="Specify a single contract by name",
        type=click.Choice(NUCYPHER_CONTRACT_NAMES),
        required=required
    )


def option_controller_port(default=None):
    return click.option(
        '--controller-port',
        help="The host port to run Alice HTTP services on",
        type=NETWORK_PORT,
        default=default)


def option_discovery_port(default=None):
    return click.option(
        '--discovery-port',
        help="The host port to run node discovery services on",
        type=NETWORK_PORT,
        default=default)


def option_label(required: bool = False):
    return click.option(
        '--label',
        help="The label for a policy",
        type=click.STRING,
        required=required)


def option_message_kit(required: bool = False):
    return click.option(
        '--message-kit',
        help="The message kit unicode string encoded in base64",
        type=click.STRING,
        required=required)


def option_network(required: bool = False,
                   default: str = None,  # NetworksInventory.DEFAULT is not a good global default (2214)
                   validate: bool = False):
    return click.option(
        '--network',
        help="NuCypher Network/Domain Name",
        type=NuCypherNetworkName(validate=validate),
        required=required,
        default=default)


def option_policy_encrypting_key(required: bool = False):
    return click.option(
        '--policy-encrypting-key',
        help="Encrypting Public Key for Policy as hexadecimal string",
        type=click.STRING,
        required=required)


def option_provider_uri(default=None, required: bool = False):
    return click.option(
        '--provider', 'provider_uri',
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


def wrap_option(handler, **options):

    assert len(options) == 1
    name = list(options)[0]
    dec = options[name]

    @functools.wraps(handler)
    def _decorator(func):

        @functools.wraps(func)
        def wrapper(**kwargs):
            if name not in kwargs:
                raise ValueError(
                        f"When trying to wrap a CLI option with {handler}, "
                        f"{name} was not found among arguments")
            option_val = kwargs[name]
            option_name, new_val = handler(option_val)
            del kwargs[name]
            kwargs[option_name] = new_val
            return func(**kwargs)

        wrapper = dec(wrapper)

        return wrapper

    return _decorator


def process_middleware(mock_networking) -> tuple:
    #################
    # MUST NOT RAISE!
    #################
    try:
        from tests.utils.middleware import MockRestMiddleware
    except ImportError:
        # It's okay to not crash here despite not having the tests package available.
        logger = Logger("CLI-Middleware-Optional-Handler")
        logger.info('--mock-networking flag is unavailable without dev install.')
    if mock_networking:
        middleware = MockRestMiddleware()
    else:
        from nucypher.network.middleware import RestMiddleware
        middleware = RestMiddleware()
    return 'middleware', middleware


option_middleware = wrap_option(
    process_middleware,
    mock_networking=_option_middleware,
)
