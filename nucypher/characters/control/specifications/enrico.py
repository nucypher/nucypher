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

from nucypher.characters.control.specifications import fields
from nucypher.characters.control.specifications.base import BaseSchema
from nucypher.cli import options


class EncryptMessage(BaseSchema):

    # input
    message = fields.Cleartext(
        required=True, load_only=True,
        click=click.option('--message', help="A unicode message to encrypt for a policy")
    )

    policy_encrypting_key = fields.Key(
        required=False,
        load_only=True,
        click=options.option_policy_encrypting_key())

    # output
    message_kit = fields.UmbralMessageKit(dump_only=True)
    signature = fields.String(dump_only=True) # maybe we need a signature field?
