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


import click

from nucypher.cli import moe, ursula, status, alice, bob, enrico
from nucypher.cli.config import echo_version, nucypher_click_config
from nucypher.cli.painting import BANNER
from nucypher.utilities.logging import GlobalConsoleLogger

GlobalConsoleLogger.start_if_not_started()


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
nucypher_cli.add_command(alice.alice)
nucypher_cli.add_command(bob.bob)
nucypher_cli.add_command(enrico.enrico)
nucypher_cli.add_command(moe.moe)
nucypher_cli.add_command(ursula.ursula)
