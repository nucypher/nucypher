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
from constant_sorrow.constants import NO_KEYRING_ATTACHED


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


def paint_new_installation_help(emitter, new_configuration, filepath):
    character_config_class = new_configuration.__class__
    character_name = character_config_class.NAME.lower()

    if new_configuration.keyring != NO_KEYRING_ATTACHED:
        maybe_public_key = bytes(new_configuration.keyring.signing_public_key).hex()
    else:
        maybe_public_key = "(no keyring attached)"

    emitter.message(f"Generated keyring", color='green')
    emitter.message(f"""
    
Public key (stamp):   {maybe_public_key}
Path to keyring: {new_configuration.keyring_root}

- You can share your public key with anyone. Others need it to interact with you.
- Never share secret keys with anyone! 
- Backup your keyring! Character keys are required to interact with the protocol!
- Remember your password! Without the password, it's impossible to decrypt the key!

""")

    default_config_filepath = True
    if new_configuration.default_filepath() != filepath:
        default_config_filepath = False
    emitter.message(f'Generated configuration file at {"default" if default_config_filepath else "non-default"} '
                    f'filepath {filepath}', color='green')

    # add hint about --config-file
    if not default_config_filepath:
        emitter.message(f'* NOTE: for a non-default configuration filepath use `--config-file "{filepath}"` '
                        f'with subsequent `{character_name}` CLI commands', color='yellow')

    # Felix
    if character_name == 'felix':
        hint = '''
To initialize a new faucet recipient database run: nucypher felix createdb 
'''

    # Ursula
    elif character_name == 'ursula':
        hint = '''
* Review configuration  -> nucypher ursula config
* Start working         -> nucypher ursula run
'''

    elif character_name == 'alice':
        hint = '''
* Review configuration  -> nucypher alice config
* View public keys      -> nucypher alice public-keys
* Grant access          -> nucypher alice grant
* Revoke access         -> nucypher alice revoke
* Start HTTP server     -> nucypher alice run
'''

    elif character_name == 'bob':
        hint = '''
* Review configuration  -> nucypher bob config
* View public keys      -> nucypher bob public-keys
* Fetch & Decrypt       -> nucypher bob retrieve
* Open dispute          -> nucypher bob challenge
* Start HTTP server     -> nucypher bob run
'''

    else:
        raise ValueError(f'Unknown character type "{character_name}"')
    emitter.echo(hint, color='green')


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
