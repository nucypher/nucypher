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


import collections
from distutils.util import strtobool
import functools
import os

import click
from constant_sorrow.constants import NO_PASSWORD, NO_BLOCKCHAIN_CONNECTION
from nacl.exceptions import CryptoError
from twisted.logger import Logger
from twisted.logger import globalLogPublisher

from nucypher.blockchain.eth.registry import EthereumContractRegistry
from nucypher.characters.banners import NUCYPHER_BANNER
from nucypher.characters.control.emitters import StdoutEmitter, IPCStdoutEmitter
from nucypher.config.constants import NUCYPHER_SENTRY_ENDPOINT
from nucypher.config.node import NodeConfiguration
from nucypher.network.middleware import RestMiddleware
from nucypher.utilities.logging import (
    logToSentry,
    getTextFileObserver,
    initialize_sentry,
    getJsonFileObserver,
    GlobalLogger,
    ConsoleLoggingObserver,
)
from nucypher.utilities.sandbox.middleware import MockRestMiddleware


def get_env_bool(var_name: str, default: bool) -> bool:
    if var_name in os.environ:
        # TODO: which is better: to fail on an incorrect envvar, or to use the default?
        # Currently doing the former.
        return strtoobool(os.environ[var_name])
    else:
        return default


class NucypherClickConfig:

    # Output Sinks
    capture_stdout = False
    __emitter = None
    __sentry_endpoint = NUCYPHER_SENTRY_ENDPOINT

    # Environment Variables
    config_file = os.environ.get('NUCYPHER_CONFIG_FILE')
    sentry_endpoint = os.environ.get("NUCYPHER_SENTRY_DSN", __sentry_endpoint)
    log_to_sentry = get_env_bool("NUCYPHER_SENTRY_LOGS", True)
    log_to_file = get_env_bool("NUCYPHER_FILE_LOGS", True)

    def __init__(self):

        # Logging
        self.log = Logger(self.__class__.__name__)

        # Auth
        self.__keyring_password = NO_PASSWORD

        # Blockchain
        self.accounts = NO_BLOCKCHAIN_CONNECTION
        self.blockchain = NO_BLOCKCHAIN_CONNECTION

    def set_options(self,
                    mock_networking,
                    json_ipc,
                    verbose,
                    quiet,
                    no_logs,
                    no_sentry,
                    debug,
                    no_registry):

        # Session Emitter for pre and post character control engagement.
        if json_ipc:
            emitter = IPCStdoutEmitter(quiet=quiet, capture_stdout=NucypherClickConfig.capture_stdout)
        else:
            emitter = StdoutEmitter(quiet=quiet, capture_stdout=NucypherClickConfig.capture_stdout)

        self.attach_emitter(emitter)
        self.emit(message=NUCYPHER_BANNER)

        if debug and quiet:
            raise click.BadOptionUsage(
                option_name="quiet",
                message="--debug and --quiet cannot be used at the same time.")

        if no_sentry is not None:
            self.log_to_sentry = not no_sentry

        if no_logs is not None:
            self.log_to_file = not no_logs

        #self.log_to_console = not quiet
        self.verbose = verbose

        if debug:
            self.log_to_sentry = False
            self.log_to_file = True
            self.log_to_console = True
            self.verbose = 2
        else:
            self.log_to_console = False

        GlobalLogger.set_log_level_from_verbosity(self.verbose)
        GlobalLogger.set_sentry_logging(self.log_to_sentry)
        GlobalLogger.set_file_logging(self.log_to_file)
        GlobalLogger.set_console_logging(self.log_to_console)

        # CLI Session Configuration
        self.mock_networking = mock_networking
        self.json_ipc = json_ipc
        self.no_registry = no_registry
        self.debug = debug

        # Only used for testing outputs;
        # Redirects outputs to in-memory python containers.
        if mock_networking:
            self.emit(message="WARNING: Mock networking is enabled")
            self.middleware = MockRestMiddleware()
        else:
            self.middleware = RestMiddleware()

        # Global Warnings
        if self.verbose:
            self.emit(message="Verbose mode is enabled", color='blue')

    def connect_to_blockchain(self, character_configuration, recompile_contracts: bool = False, full_sync: bool = True):
        try:
            character_configuration.connect_to_blockchain(recompile_contracts=recompile_contracts, full_sync=full_sync)
            character_configuration.connect_to_contracts()

        except EthereumContractRegistry.NoRegistry:
            _registry_filepath = EthereumContractRegistry.from_latest_publication()

        except Exception as e:
            if self.debug:
                raise
            click.secho(str(e), fg='red', bold=True)
            raise click.Abort()

        # Success
        else:
            self.blockchain = character_configuration.blockchain
            self.accounts = self.blockchain.interface.w3.eth.accounts

    def get_password(self, confirm: bool = False) -> str:
        keyring_password = os.environ.get("NUCYPHER_KEYRING_PASSWORD", NO_PASSWORD)

        if keyring_password is NO_PASSWORD:  # Collect password, prefer env var
            prompt = "Enter keyring password"
            keyring_password = click.prompt(prompt, confirmation_prompt=confirm, hide_input=True)

        self.__keyring_password = keyring_password
        return self.__keyring_password

    def unlock_keyring(self,
                       password: str,
                       character_configuration: NodeConfiguration,
                       unlock_wallet: bool = True):

        if self.log_to_console:
            self.emit(message='Decrypting NuCypher keyring...', color='yellow')

        if character_configuration.dev_mode:
            return True  # Dev accounts are always unlocked

        # NuCypher
        try:
            character_configuration.keyring.unlock(password=password)  # Takes ~3 seconds, ~1GB Ram
        except CryptoError:
            raise character_configuration.keyring.AuthenticationFailed

        # Ethereum Client  # TODO : Integrate with Powers API
        if not character_configuration.federated_only and unlock_wallet:
            self.emit(message='Decrypting Ethereum Node Keyring...', color='yellow')
            character_configuration.blockchain.interface.unlock_account(address=character_configuration.checksum_address,
                                                                        password=password)

    @classmethod
    def attach_emitter(cls, emitter) -> None:
        cls.__emitter = emitter

    @classmethod
    def emit(cls, *args, **kwargs):
        cls.__emitter(*args, **kwargs)


class NucypherDeployerClickConfig(NucypherClickConfig):

    __secrets = ('miner_secret', 'policy_secret', 'escrow_proxy_secret', 'mining_adjudicator_secret')
    Secrets = collections.namedtuple('Secrets', __secrets)

    def collect_deployment_secrets(self) -> Secrets:

        # Deployment Environment Variables
        self.miner_escrow_deployment_secret = os.environ.get("NUCYPHER_MINERS_ESCROW_SECRET")
        self.policy_manager_deployment_secret = os.environ.get("NUCYPHER_POLICY_MANAGER_SECRET")
        self.user_escrow_proxy_deployment_secret = os.environ.get("NUCYPHER_USER_ESCROW_PROXY_SECRET")
        self.mining_adjudicator_deployment_secret = os.environ.get("NUCYPHER_MINING_ADJUDICATOR_SECRET")

        if not self.miner_escrow_deployment_secret:
            self.miner_escrow_deployment_secret = click.prompt('Enter MinerEscrow Deployment Secret',
                                                               hide_input=True,
                                                               confirmation_prompt=True)

        if not self.policy_manager_deployment_secret:
            self.policy_manager_deployment_secret = click.prompt('Enter PolicyManager Deployment Secret',
                                                                 hide_input=True,
                                                                 confirmation_prompt=True)

        if not self.user_escrow_proxy_deployment_secret:
            self.user_escrow_proxy_deployment_secret = click.prompt('Enter UserEscrowProxy Deployment Secret',
                                                                    hide_input=True,
                                                                    confirmation_prompt=True)

        if not self.mining_adjudicator_deployment_secret:
            self.mining_adjudicator_deployment_secret = click.prompt('Enter MiningAdjudicator Deployment Secret',
                                                                     hide_input=True,
                                                                     confirmation_prompt=True)

        secrets = self.Secrets(miner_secret=self.miner_escrow_deployment_secret,                    # type: str
                               policy_secret=self.policy_manager_deployment_secret,                 # type: str
                               escrow_proxy_secret=self.user_escrow_proxy_deployment_secret,        # type: str
                               mining_adjudicator_secret=self.mining_adjudicator_deployment_secret  # type: str
                               )
        return secrets


# Register the above click configuration classes as a decorators
_nucypher_click_config = click.make_pass_decorator(NucypherClickConfig, ensure=True)
_nucypher_deployer_config = click.make_pass_decorator(NucypherDeployerClickConfig, ensure=True)


def shared_cli_options(func):

    @click.option('-Z', '--mock-networking', help="Use in-memory transport instead of networking", count=True)
    @click.option('-J', '--json-ipc', help="Send all output to stdout as JSON", is_flag=True)
    @click.option('-v', '--verbose', help="Specify verbosity level", count=True)
    @click.option('-Q', '--quiet', help="Disable console printing", is_flag=True)
    @click.option('-L', '--no-logs', help="Disable all logging output", is_flag=True, default=None)
    @click.option('-S', '--no-sentry', help="Disable sending logs to Sentry", is_flag=True, default=None)
    @click.option('-D', '--debug', help="Enable debugging mode", is_flag=True)
    @click.option('--no-registry', help="Skip importing the default contract registry", is_flag=True)
    @functools.wraps(func)
    def wrapper(config,
                *args,
                mock_networking,
                json_ipc,
                verbose,
                quiet,
                no_logs,
                no_sentry,
                debug,
                no_registry,
                **kwargs):

        config.set_options(
            mock_networking,
            json_ipc,
            verbose,
            quiet,
            no_logs,
            no_sentry,
            debug,
            no_registry)

        return func(config, *args, **kwargs)
    return wrapper


def nucypher_click_config(func):
    @_nucypher_click_config
    @shared_cli_options
    @functools.wraps(func)
    def wrapper(config, *args, **kwargs):
        return func(config, *args, **kwargs)
    return wrapper


def nucypher_deployer_config(func):
    @_nucypher_deployer_config
    @shared_cli_options
    @functools.wraps(func)
    def wrapper(config, *args, **kwargs):
        return func(config, *args, **kwargs)
    return wrapper
