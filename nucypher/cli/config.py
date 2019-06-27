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
        return strtoobool(os.environ[var_name])
    else:
        return default


class NucypherClickConfig:

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
                    json_ipc,
                    verbose,
                    quiet,
                    no_logs,
                    debug,
                    no_registry,
                    log_level):

        # Session Emitter for pre and post character control engagement.
        if json_ipc:
            emitter = JSONRPCStdoutEmitter(quiet=quiet)
        else:
            emitter = StdoutEmitter(quiet=quiet)

        self.attach_emitter(emitter)

        if debug and quiet:
            raise click.BadOptionUsage(
                option_name="quiet",
                message="--debug and --quiet cannot be used at the same time.")

        log_to_console = False
        log_to_text_file = self.log_to_file
        log_to_json_file = self.log_to_file
        log_to_sentry = self.log_to_sentry

        if debug:
            log_to_console = True
            log_to_json_file = True
            log_to_text_file = True
            log_to_sentry = False
            log_level = 'debug'

        elif quiet:  # Disable Logging
            log_to_console = False
            log_to_json_file = False
            log_to_text_file = True
            log_to_sentry = False

        if no_logs:
            log_to_console = False
            log_to_json_file = False
            log_to_text_file = False
            log_to_sentry = False

        if log_level:
            GlobalLoggerSettings.set_log_level(log_level_name=log_level)
        if log_to_console:
            GlobalLoggerSettings.start_console_logging()
        if log_to_text_file:
            GlobalLoggerSettings.start_text_file_logging()
        if log_to_json_file:
            GlobalLoggerSettings.start_json_file_logging()
        if log_to_sentry:
            GlobalLoggerSettings.start_sentry_logging(self.sentry_endpoint)

        # CLI Session Configuration
        self.verbose = verbose
        self.mock_networking = mock_networking
        self.json_ipc = json_ipc
        self.quiet = quiet
        self.no_registry = no_registry
        self.debug = debug

        # Only used for testing outputs;
        # Redirects outputs to in-memory python containers.
        if mock_networking:
            self.emitter.message("WARNING: Mock networking is enabled")
            self.middleware = MockRestMiddleware()
        else:
            self.middleware = RestMiddleware()

        # Global Warnings
        if self.verbose:
            self.emitter.message("Verbose mode is enabled", color='blue')

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
    @click.option('-J', '--json-ipc', help="Send all output to stdout as JSON", is_flag=True)
    @click.option('-v', '--verbose', help="Specify verbosity level", count=True)
    @click.option('-Q', '--quiet', help="Disable console printing", is_flag=True)
    @click.option('-L', '--no-logs', help="Disable all logging output", is_flag=True)
    @click.option('-D', '--debug', help="Enable debugging mode", is_flag=True)
    @click.option('--no-registry', help="Skip importing the default contract registry", is_flag=True)
    @click.option('--log-level', help="The log level for this process.  Is overridden by --debug.",
                  type=click.Choice(['critical', 'error', 'warn', 'info', 'debug']),
                  default='info')
    @functools.wraps(func)
    def wrapper(config,
                *args,
                mock_networking,
                json_ipc,
                verbose,
                quiet,
                no_logs,
                debug,
                no_registry,
                log_level,
                **kwargs):

        config.set_options(
            mock_networking,
            json_ipc,
            verbose,
            quiet,
            no_logs,
            debug,
            no_registry,
            log_level)

        return func(config, *args, **kwargs)
    return wrapper
