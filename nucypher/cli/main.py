

import click

from nucypher.cli.commands import (
    status,
    ursula,
    bond
)
from nucypher.cli.painting.help import (
    echo_version,
    echo_config_root_path,
    echo_logging_root_path
)


@click.group()
@click.option('--version', help="Echo the CLI version",
              is_flag=True, callback=echo_version, expose_value=False, is_eager=True)
@click.option('--config-path', help="Echo the configuration root directory path",
              is_flag=True, callback=echo_config_root_path, expose_value=False, is_eager=True)
@click.option('--logging-path', help="Echo the logging root directory path",
              is_flag=True, callback=echo_logging_root_path, expose_value=False, is_eager=True)
def nucypher_cli():
    """Top level command for all things nucypher."""


#
# Character CLI Entry Points
#

ENTRY_POINTS = (

    # Characters & Actors
    ursula.ursula,  # Untrusted Re-Encryption Proxy

    # PRE Application
    bond.bond,
    bond.unbond,

    # Utility Commands
    status.status,  # Network status explorer

)

for entry_point in ENTRY_POINTS:
    nucypher_cli.add_command(entry_point)
