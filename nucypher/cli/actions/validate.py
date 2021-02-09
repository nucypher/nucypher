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

from nucypher.characters.control.emitters import StdoutEmitter
from nucypher.characters.lawful import Alice


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

    # Policy option validation
    if alice.federated_only:
        if any((value, rate)):
            message = "Can't use --value or --rate with a federated Alice."
            raise click.BadOptionUsage(option_name="--value, --rate", message=message)
    elif bool(value) and bool(rate):
        raise click.BadOptionUsage(option_name="--rate", message="Can't use --value if using --rate")

    # Force mode validation
    if force:
        required = (
            (bob or (bob_verifying_key and bob_encrypting_key)),
            label,
            expiration
        )
        if not all(required):
            emitter.error('--label, --expiration, and --bob is required in force mode.')
            raise click.Abort()
