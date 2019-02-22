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

from nucypher.characters.banners import NUCYPHER_BANNER
from nucypher.cli import status
from nucypher.cli.characters import moe, ursula, alice, bob, enrico
from nucypher.cli.config import nucypher_click_config
from nucypher.cli.painting import echo_version
from nucypher.utilities.logging import GlobalConsoleLogger


@click.group()
@click.option('--version', help="Echo the CLI version", is_flag=True, callback=echo_version, expose_value=False, is_eager=True)
@click.option('-v', '--verbose', help="Specify verbosity level", count=True)
@click.option('-J', '--json', help="Send all output to stdout as JSON", is_flag=True, default=False)
@click.option('--no-logs', help="Disable all logging output", is_flag=True, default=False)
@nucypher_click_config
def nucypher_cli(click_config, verbose, json, no_logs):

    if not no_logs:
        GlobalConsoleLogger.start_if_not_started()

    if not json:
        click.echo(NUCYPHER_BANNER)

    click_config.verbose = verbose
    click_config.json = json
    click_config.no_logs = no_logs

    if click_config.verbose:
        click.secho("Verbose mode is enabled", fg='blue')


nucypher_cli.add_command(status.status)
nucypher_cli.add_command(alice.alice)
nucypher_cli.add_command(bob.bob)
nucypher_cli.add_command(enrico.enrico)
nucypher_cli.add_command(moe.moe)
nucypher_cli.add_command(ursula.ursula)
