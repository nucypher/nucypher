"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.

"""

import shutil

import click
from twisted.logger import Logger
from twisted.logger import globalLogPublisher

from constant_sorrow import constants
from constant_sorrow.constants import TEMPORARY_DOMAIN
from nucypher.characters.lawful import Ursula
from nucypher.cli import moe, ursula, status
from nucypher.cli.config import echo_version, nucypher_click_config
from nucypher.cli.painting import BANNER, paint_configuration, paint_known_nodes
from nucypher.cli.processes import UrsulaCommandProtocol
from nucypher.config.characters import UrsulaConfiguration
from nucypher.config.constants import DEFAULT_CONFIG_ROOT


#
# Common CLI
#

@click.group()
@click.option('--version', help="Echo the CLI version", is_flag=True, callback=echo_version, expose_value=False, is_eager=True)
@click.option('-v', '--verbose', help="Specify verbosity level", count=True)
@nucypher_click_config
def nucypher_cli(click_config, verbose):
    click.echo(BANNER)
    click_config.verbose = verbose
    if click_config.verbose:
        click.secho("Verbose mode is enabled", fg='blue')


nucypher_cli.add_command(status.status)
nucypher_cli.add_command(moe.moe)
nucypher_cli.add_command(ursula.ursula)
