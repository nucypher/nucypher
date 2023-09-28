import click

from nucypher.cli.commands import taco, ursula
from nucypher.cli.painting.help import (
    echo_config_root_path,
    echo_logging_root_path,
    echo_version,
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
# CLI Entry Points
#

ENTRY_POINTS = (
    ursula.ursula,
    taco.taco,
    # add more entry points here
)

for entry_point in ENTRY_POINTS:
    nucypher_cli.add_command(entry_point)
