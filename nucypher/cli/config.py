# noinspection Mypy



import os

import click

from nucypher.cli.options import group_options
from nucypher.cli.utils import get_env_bool
from nucypher.config.constants import DEFAULT_CONFIG_ROOT, NUCYPHER_SENTRY_ENDPOINT
from nucypher.utilities.emitters import StdoutEmitter
from nucypher.utilities.logging import GlobalLoggerSettings, Logger


class GroupGeneralConfig:
    __option_name__ = 'general_config'

    verbosity = 0

    # Environment Variables
    config_root = DEFAULT_CONFIG_ROOT
    sentry_endpoint = os.environ.get("NUCYPHER_SENTRY_DSN", NUCYPHER_SENTRY_ENDPOINT)
    log_to_sentry = get_env_bool("NUCYPHER_SENTRY_LOGS", False)
    log_to_file = get_env_bool("NUCYPHER_FILE_LOGS", True)
    log_to_json_file = get_env_bool("NUCYPHER_JSON_LOGS", False)

    def __init__(
        self,
        json_ipc: bool,
        verbose: bool,
        quiet: bool,
        no_logs: bool,
        console_logs: bool,
        file_logs: bool,
        json_logs: bool,
        sentry_logs: bool,
        log_level: bool,
        debug: bool,
    ):
        self.log = Logger(self.__class__.__name__)

        # Session Emitter for pre and post character control engagement.
        if verbose and quiet:
            raise click.BadOptionUsage(
                option_name="quiet",
                message="--verbose and --quiet are mutually exclusive "
                        "and cannot be used at the same time.")

        if verbose:
            GroupGeneralConfig.verbosity = 2
        elif quiet:
            GroupGeneralConfig.verbosity = 0
        else:
            GroupGeneralConfig.verbosity = 1

        emitter = StdoutEmitter(verbosity=GroupGeneralConfig.verbosity)

        self.emitter = emitter

        if verbose:
            self.emitter.message("Verbose mode is enabled", color='blue')

        # Logging
        if debug and no_logs:
            message = "--debug and --no-logs cannot be used at the same time."
            raise click.BadOptionUsage(option_name="no-logs", message=message)

        # Defaults
        if file_logs is None:
            file_logs = self.log_to_file
        if json_logs is None:
            json_logs = self.log_to_json_file
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
            json_logs = False
            sentry_logs = False
        if json_ipc:
            console_logs = False

        GlobalLoggerSettings.set_log_level(log_level_name=log_level)

        if console_logs:
            GlobalLoggerSettings.start_console_logging()
        if file_logs:
            GlobalLoggerSettings.start_text_file_logging()
        if json_logs:
            GlobalLoggerSettings.start_json_file_logging()
        if sentry_logs:
            GlobalLoggerSettings.start_sentry_logging(self.sentry_endpoint)
        if json_ipc:
            GlobalLoggerSettings.stop_console_logging()  # JSON-RPC Protection

        self.debug = debug
        self.json_ipc = json_ipc


group_general_config = group_options(
    GroupGeneralConfig,

    verbose=click.option('-v', '--verbose', help="Verbose console messages", is_flag=True),
    quiet=click.option('-Q', '--quiet', help="Disable console messages", is_flag=True),
    no_logs=click.option('-L', '--no-logs', help="Disable all logging output", is_flag=True),

    json_ipc=click.option('-J', '--json-ipc',
                          help="Send all IPC output to stdout as JSON, and turn off the rest",
                          is_flag=True),

    console_logs=click.option(
        '--console-logs/--no-console-logs',
        help="Enable/disable logging to console. Defaults to `--no-console-logs`.",
        default=False),

    file_logs=click.option(
        '--file-logs/--no-file-logs',
        help="Enable/disable logging to text file. Defaults to NUCYPHER_FILE_LOGS, or to `--file-logs` if it is not set.",
        default=None,
    ),
    json_logs=click.option(
        "--json-logs/--no-json-logs",
        help="Enable/disable logging to a json file. Defaults to NUCYPHER_JSON_LOGS, or to `--no-json-logs` if it is not set.",
        default=None),

    sentry_logs=click.option(
        '--sentry-logs/--no-sentry-logs',
        help="Enable/disable logging to Sentry. Defaults to NUCYPHER_SENTRY_LOGS, or to `--sentry-logs` if it is not set.",
        default=None),

    log_level=click.option(
        '--log-level', help="The log level for this process.  Is overridden by --debug.",
        type=click.Choice(['critical', 'error', 'warn', 'info', 'debug']),
        default='info'),

    debug=click.option(
        '-D', '--debug',
        help="Enable debugging mode, crashing on more exceptions instead of trying to recover. "
             "Also sets log level to \"debug\", turns on console and file logging "
             "and turns off Sentry logging.",
        is_flag=True),
)
