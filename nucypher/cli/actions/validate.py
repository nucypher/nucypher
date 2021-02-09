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
from collections import namedtuple

import click
import maya

from nucypher.characters.control.emitters import StdoutEmitter
from nucypher.characters.lawful import Alice

Precondition = namedtuple('Precondition', 'options condition')


def validate_grant_command(
        emitter: StdoutEmitter,
        alice: Alice,
        force: bool,
        bob: str,
        bob_verifying_key: str,
        bob_encrypting_key: str,
        label: str,
        expiration: maya.MayaDT,
        rate: int,
        value: int
):

    # Force mode validation
    if force:
        required = (
            Precondition(
                options='--bob or --bob-encrypting-key and --bob-verifying-key.',
                condition=bob or all((bob_verifying_key, bob_encrypting_key))
             ),

            Precondition(options='--label', condition=bool(label)),

            Precondition(options='--expiration', condition=bool(expiration))
        )
        triggered = False
        for condition in required:
            # see what condition my condition was in.
            if not condition.condition:
                triggered = True
                emitter.error(f'Missing options in force mode: {condition.options}')
        if triggered:
            raise click.Abort()

    # Handle federated
    if alice.federated_only:
        if any((value, rate)):
            message = "Can't use --value or --rate with a federated Alice."
            raise click.BadOptionUsage(option_name="--value, --rate", message=message)
    elif bool(value) and bool(rate):
        raise click.BadOptionUsage(option_name="--rate", message="Can't use --value if using --rate")

    # From Bob card
    if bob:
        if any((bob_encrypting_key, bob_verifying_key)):
            message = '--bob cannot be used with --bob-encrypting-key or --bob-verifying key'
            raise click.BadOptionUsage(option_name='--bob', message=message)

    # From hex public keys
    else:
        if not all((bob_encrypting_key, bob_verifying_key)):
            if force:
                emitter.message('Missing options in force mode: --bob or --bob-encrypting-key and --bob-verifying-key.')
                click.Abort()
            emitter.message("*Caution: Only enter public keys*")
