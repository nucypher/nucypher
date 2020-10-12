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
import maya

from nucypher.blockchain.eth.sol.__conf__ import SOLIDITY_COMPILER_VERSION
from nucypher.characters.banners import NUCYPHER_BANNER
from nucypher.config.constants import DEFAULT_CONFIG_ROOT, USER_LOG_DIR, END_OF_POLICIES_PROBATIONARY_PERIOD


def echo_version(ctx, param, value):
    if not value or ctx.resilient_parsing:
        return
    click.secho(NUCYPHER_BANNER, bold=True)
    ctx.exit()


def echo_solidity_version(ctx, param, value):
    if not value or ctx.resilient_parsing:
        return
    click.secho(f"Supported solidity version: {SOLIDITY_COMPILER_VERSION}", bold=True)
    ctx.exit()


def echo_config_root_path(ctx, param, value):
    if not value or ctx.resilient_parsing:
        return
    click.secho(DEFAULT_CONFIG_ROOT)
    ctx.exit()


def echo_logging_root_path(ctx, param, value):
    if not value or ctx.resilient_parsing:
        return
    click.secho(USER_LOG_DIR)
    ctx.exit()


def paint_new_installation_help(emitter, new_configuration):
    character_config_class = new_configuration.__class__
    character_name = character_config_class.NAME.lower()

    emitter.message("Generated keyring {}".format(new_configuration.keyring_root), color='green')
    emitter.message("Saved configuration file {}".format(new_configuration.config_file_location), color='green')

    # Felix
    if character_name == 'felix':
        suggested_db_command = 'nucypher felix createdb'
        how_to_proceed_message = f'\nTo initialize a new faucet database run:'
        emitter.echo(how_to_proceed_message, color='green')
        emitter.echo(f'\n\'{suggested_db_command}\'', color='green')

    # Ursula
    elif character_name == 'ursula' and not new_configuration.federated_only:
        how_to_stake_message = f"\nIf you haven't done it already, initialize a NU stake with 'nucypher stake' or"
        emitter.echo(how_to_stake_message, color='green')

    # Everyone: Give the use a suggestion as to what to do next
    suggested_command = f'nucypher {character_name} run'
    how_to_run_message = f"\nTo start {character_name.capitalize()} run '{suggested_command}'\n"
    emitter.echo(how_to_run_message.format(suggested_command), color='green')


def paint_probationary_period_disclaimer(emitter):
    width = 60
    import textwrap
    disclaimer_title = " DISCLAIMER ".center(width, "=")
    paragraph = f"""
Some areas of the NuCypher network are still under active development;
as a consequence, we have established a probationary period for policies in the network.
Currently the creation of sharing policies with durations beyond {END_OF_POLICIES_PROBATIONARY_PERIOD} are prevented.
After this date the probationary period will be over, and you will be able to create policies with any duration
as supported by nodes on the network.
"""

    text = (
        "\n",
        disclaimer_title,
        *[line.center(width) for line in textwrap.wrap(paragraph, width - 2)],
        "=" * len(disclaimer_title),
        "\n"
    )
    for sentence in text:
        emitter.echo(sentence, color='yellow')


def enforce_probationary_period(emitter, expiration):
    """Used during CLI grant to prevent publication of a policy outside the probationary period."""
    if maya.MayaDT.from_datetime(expiration) > END_OF_POLICIES_PROBATIONARY_PERIOD:
        emitter.echo(f"The requested duration for this policy (until {expiration}) exceeds the probationary period"
                     f" ({END_OF_POLICIES_PROBATIONARY_PERIOD}).", color="red")
        raise click.Abort()
