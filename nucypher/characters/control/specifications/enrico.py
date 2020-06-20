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
from marshmallow import post_load

from nucypher.characters.control.specifications import fields, exceptions
from nucypher.cli import options
from nucypher.cli.types import EXISTING_READABLE_FILE
from nucypher.characters.control.specifications.base import BaseSchema


class EncryptMessage(BaseSchema):

    # input
    message = fields.Cleartext(
        load_only=True,
        allow_none=True,
        click=click.option('--message', help="A unicode message to encrypt for a policy")
    )

    file = fields.FileField(
        load_only=True,
        allow_none=True,
        click=click.option('--file', help="Filepath to plaintext file to encrypt", type=EXISTING_READABLE_FILE)
    )

    policy_encrypting_key = fields.Key(
        required=False,
        load_only=True,
        click=options.option_policy_encrypting_key()
    )

    @post_load()
    def format_method_arguments(self, data, **kwargs):
        """
        input can be through either the file input or a raw message,
        we output one of them as the "plaintext" arg to enrico.encrypt_message
        """

        if data.get('message') and data.get('file'):
            raise exceptions.InvalidArgumentCombo("choose either a message or a filepath but not both.")

        if data.get('message'):
            data = bytes(data['message'], encoding='utf-8')
        else:
            data = data['file']

        return {"plaintext": data}

    # output
    message_kit = fields.UmbralMessageKit(dump_only=True)
    signature = fields.UmbralSignature(dump_only=True)
