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


import functools
import os
from distutils.util import strtobool

import click
from twisted.logger import Logger

from nucypher.characters.control.emitters import StdoutEmitter, JSONRPCStdoutEmitter
from nucypher.config.constants import NUCYPHER_SENTRY_ENDPOINT
from nucypher.network.middleware import RestMiddleware
from nucypher.utilities.logging import GlobalLoggerSettings
from nucypher.utilities.sandbox.middleware import MockRestMiddleware


def get_env_bool(var_name: str, default: bool) -> bool:
    if var_name in os.environ:
        # TODO: which is better: to fail on an incorrect envvar, or to use the default?
        # Currently doing the former.
        return strtobool(os.environ[var_name])
    else:
        return default


class NucypherClickConfig:

    verbosity = 0

    # Output Sinks
    __emitter = None

    # Environment Variables
    config_file = os.environ.get('NUCYPHER_CONFIG_FILE')
    sentry_endpoint = os.environ.get("NUCYPHER_SENTRY_DSN", NUCYPHER_SENTRY_ENDPOINT)
    log_to_sentry = get_env_bool("NUCYPHER_SENTRY_LOGS", True)
    log_to_file = get_env_bool("NUCYPHER_FILE_LOGS", True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Logging
        self.log = Logger(self.__class__.__name__)

    def set_options(self,
                    mock_networking,
                    etherscan,
                    json_ipc,
                    verbose,
                    quiet,
                    no_logs,
                    console_logs,
                    file_logs,
                    sentry_logs,
                    log_level,
                    debug):

        # Session Emitter for pre and post character control engagement.
        if verbose and quiet:
            raise click.BadOptionUsage(
                option_name="quiet",
                message="--verbose and --quiet are mutually exclusive "
                        "and cannot be used at the same time.")

        if verbose:
            NucypherClickConfig.verbosity = 2
        elif quiet:
            NucypherClickConfig.verbosity = 0
        else:
            NucypherClickConfig.verbosity = 1

        if json_ipc:
            emitter = JSONRPCStdoutEmitter(verbosity=NucypherClickConfig.verbosity)
        else:
            emitter = StdoutEmitter(verbosity=NucypherClickConfig.verbosity)

        self.attach_emitter(emitter)

        if verbose:
            self.emitter.message("Verbose mode is enabled", color='blue')

        # Logging

        if debug and no_logs:
            raise click.BadOptionUsage(
                option_name="no-logs",
                message="--debug and --no-logs cannot be used at the same time.")

        # Defaults
        if file_logs is None:
            file_logs = self.log_to_file
        if sentry_logs is None:
            sentry_logs = self.log_to_sentry

        if debug:
            console_logs = True
            file_logs = True
            sentry_logs = False
            log_level = 'debug'

        if no_logs:
            console_logs = False
            file_logs = False
            sentry_logs = False

        GlobalLoggerSettings.set_log_level(log_level_name=log_level)

        if console_logs:
            GlobalLoggerSettings.start_console_logging()
        if file_logs:
            GlobalLoggerSettings.start_text_file_logging()
            GlobalLoggerSettings.start_json_file_logging()
        if sentry_logs:
            GlobalLoggerSettings.start_sentry_logging(self.sentry_endpoint)

        # CLI Session Configuration
        self.mock_networking = mock_networking
        self.debug = debug
        self.json_ipc = json_ipc
        self.etherscan = etherscan

        # Only used for testing outputs;
        # Redirects outputs to in-memory python containers.
        if mock_networking:
            self.emitter.message("WARNING: Mock networking is enabled")
            self.middleware = MockRestMiddleware()
        else:
            self.middleware = RestMiddleware()

    @classmethod
    def attach_emitter(cls, emitter) -> None:
        cls.__emitter = emitter

    @property
    def emitter(cls):
        return cls.__emitter


# Register the above click configuration classes as a decorators
_nucypher_click_config = click.make_pass_decorator(NucypherClickConfig, ensure=True)


def nucypher_click_config(func):
    @_nucypher_click_config
    @click.option('-Z', '--mock-networking', help="Use in-memory transport instead of networking", count=True)
    @click.option('--etherscan/--no-etherscan', help="Enable/disable viewing TX in Etherscan", default=False)
    @click.option('-J', '--json-ipc', help="Send all IPC output to stdout as JSON, and turn off the rest", is_flag=True)
    @click.option('-v', '--verbose', help="Verbose console messages", is_flag=True)
    @click.option('-Q', '--quiet', help="Disable console messages", is_flag=True)
    @click.option('-L', '--no-logs', help="Disable all logging output", is_flag=True)
    @click.option('--console-logs/--no-console-logs',
                  help="Enable/disable logging to console. "
                       "Defaults to `--no-console-logs`.",
                  default=False)
    @click.option('--file-logs/--no-file-logs',
                  help="Enable/disable logging to file. "
                       "Defaults to NUCYPHER_FILE_LOGS, or to `--file-logs` if it is not set.",
                  default=None)
    @click.option('--sentry-logs/--no-sentry-logs',
                  help="Enable/disable logging to Sentry. "
                  "Defaults to NUCYPHER_SENTRY_LOGS, or to `--sentry-logs` if it is not set.",
                  default=None)
    @click.option('--log-level', help="The log level for this process.  Is overridden by --debug.",
                  type=click.Choice(['critical', 'error', 'warn', 'info', 'debug']),
                  default='info')
    @click.option('-D', '--debug',
                  help="Enable debugging mode, crashing on more exceptions instead of trying to recover. "
                       "Also sets log level to \"debug\", turns on console and file logging "
                       "and turns off Sentry logging.",
                  is_flag=True)
    @functools.wraps(func)
    def wrapper(config,
                *args,
                mock_networking,
                etherscan,
                json_ipc,
                verbose,
                quiet,
                no_logs,
                console_logs,
                file_logs,
                sentry_logs,
                log_level,
                debug,
                **kwargs):

        config.set_options(
            mock_networking,
            etherscan,
            json_ipc,
            verbose,
            quiet,
            no_logs,
            console_logs,
            file_logs,
            sentry_logs,
            log_level,
            debug)

        return func(config, *args, **kwargs)
    return wrapper
