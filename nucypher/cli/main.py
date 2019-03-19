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


import click
from twisted.logger import globalLogPublisher

from nucypher.characters.banners import NUCYPHER_BANNER
from nucypher.characters.control.emitters import StdoutEmitter, IPCStdoutEmitter
from nucypher.cli import status
from nucypher.cli.actions import destroy_configuration_root
from nucypher.cli.characters import moe, ursula, alice, bob, enrico, felix
from nucypher.cli.config import nucypher_click_config, NucypherClickConfig
from nucypher.cli.painting import echo_version
from nucypher.network.middleware import RestMiddleware
from nucypher.utilities.logging import GlobalConsoleLogger, getJsonFileObserver, SimpleObserver, logToSentry
from nucypher.utilities.sandbox.middleware import MockRestMiddleware


@click.group()
@click.option('--version', help="Echo the CLI version", is_flag=True, callback=echo_version, expose_value=False, is_eager=True)
@click.option('-v', '--verbose', help="Specify verbosity level", count=True)
@click.option('-Z', '--mock-networking', help="Use in-memory transport instead of networking", count=True)
@click.option('-J', '--json-ipc', help="Send all output to stdout as JSON", is_flag=True)
@click.option('-Q', '--quiet', help="Disable console printing", is_flag=True)
@click.option('-L', '--no-logs', help="Disable all logging output", is_flag=True)
@click.option('-D', '--debug', help="Enable debugging mode", is_flag=True)
@click.option('--no-registry', help="Skip importing the default contract registry", is_flag=True)
@nucypher_click_config
def nucypher_cli(click_config,
                 verbose,
                 mock_networking,
                 json_ipc,
                 no_logs,
                 quiet,
                 debug,
                 no_registry):

    # Session Emitter for pre and post character control engagement.
    if json_ipc:
        emitter = IPCStdoutEmitter(quiet=quiet, capture_stdout=NucypherClickConfig.capture_stdout)
    else:
        emitter = StdoutEmitter(quiet=quiet, capture_stdout=NucypherClickConfig.capture_stdout)

    click_config.attach_emitter(emitter)
    click_config.emit(message=NUCYPHER_BANNER)

    if debug and quiet:
        raise click.BadOptionUsage(option_name="quiet", message="--debug and --quiet cannot be used at the same time.")

    if debug:
        click_config.log_to_sentry = False
        click_config.log_to_file = True                 # File Logging
        globalLogPublisher.addObserver(SimpleObserver())  # Console Logging
        globalLogPublisher.removeObserver(logToSentry)  # No Sentry
        GlobalConsoleLogger.set_log_level(log_level_name='debug')

    elif quiet:  # Disable Logging
        globalLogPublisher.removeObserver(logToSentry)
        globalLogPublisher.removeObserver(SimpleObserver)
        globalLogPublisher.removeObserver(getJsonFileObserver())

    # Logging
    if not no_logs:
        GlobalConsoleLogger.start_if_not_started()

    # CLI Session Configuration
    click_config.verbose = verbose
    click_config.mock_networking = mock_networking
    click_config.json_ipc = json_ipc
    click_config.no_logs = no_logs
    click_config.quiet = quiet
    click_config.no_registry = no_registry
    click_config.debug = debug

    # Only used for testing outputs;
    # Redirects outputs to in-memory python containers.
    if mock_networking:
        click_config.emit(message="WARNING: Mock networking is enabled")
        click_config.middleware = MockRestMiddleware()
    else:
        click_config.middleware = RestMiddleware()

    # Global Warnings
    if click_config.verbose:
        click_config.emit("Verbose mode is enabled", color='blue')


@click.command()
@click.option('--logs', help="Also destroy logs", is_flag=True)
@click.option('--force', help="Don't ask for confirmation and Ignore Errors", is_flag=True)
@click.option('--config-root', help="Custom configuration directory", type=click.Path())
def remove(logs, force, config_root):
    destroy_configuration_root(config_root=config_root, force=force, logs=logs)


#
# Character CLI Entry Points (Fan Out Input)
#

r"""
            ursula
              |                    
              |  moe 
              |  /                 
              | /
stdin --> cli.main --- alice
              | \
              |  \ 
              |  bob 
              |
            enrico 
            


New character CLI modules must be added here
for the entry point to be attached to the nucypher base command.

Inversely, commenting out an entry point here will disable it.
"""

ENTRY_POINTS = (

    # Utility Sub-Commands
    remove,         # Remove NuCypher Files
    status.status,  # Network Status

    # Characters
    alice.alice,    # Author of Policies
    bob.bob,        # Builder of Capsules
    enrico.enrico,  # Encryptor of Data
    moe.moe,        # Monitor
    ursula.ursula,  # Untrusted Re-Encryption Proxy
    felix.felix     # Faucet
)

for entry_point in ENTRY_POINTS:
    nucypher_cli.add_command(entry_point)
