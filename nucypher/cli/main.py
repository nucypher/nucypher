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

from nucypher.cli.commands import (
    enrico,
    status,
    ursula,
    porter,
    bond,
)
from nucypher.cli.painting.help import echo_version, echo_config_root_path, echo_logging_root_path


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
    enrico.enrico,  # Encryptor of Data

    # PRE Application
    bond.bond,
    bond.unbond,

    # Utility Commands
    status.status,      # Network status explorer
    porter.porter,      # Network support services

)

for entry_point in ENTRY_POINTS:
    nucypher_cli.add_command(entry_point)
