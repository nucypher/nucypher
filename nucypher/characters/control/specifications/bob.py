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

import nucypher.control.specifications.fields as base_fields
from nucypher.characters.control.specifications import fields as character_fields
from nucypher.characters.control.specifications.fields.treasuremap import EncryptedTreasureMap
from nucypher.control.specifications.base import BaseSchema
from nucypher.cli import options


class RetrieveAndDecrypt(BaseSchema):

    policy_encrypting_key = character_fields.Key(
        required=True,
        load_only=True,
        click=options.option_policy_encrypting_key(required=True)
    )
    alice_verifying_key = character_fields.Key(
        required=True,
        load_only=True,
        click=click.option(
            '--alice-verifying-key',
            '-avk',
            help="Alice's verifying key as a hexadecimal string",
            type=click.STRING,
            required=True)
    )
    message_kit = character_fields.MessageKit(
        required=True,
        load_only=True,
        click=options.option_message_kit(required=True)
    )
    # optional
    treasure_map = character_fields.TreasureMap(
        required=False,
        load_only=True,
        click=click.option(
            '--treasure-map',
            '-t',
            help="Treasure Map for retrieve",
            type=click.STRING,
            required=False))

    encrypted_treasure_map = EncryptedTreasureMap(required=True,
                                                  load_only=True,
                                                  click=options.option_treasure_map)

    cleartexts = base_fields.List(character_fields.Cleartext(), dump_only=True)


class PublicKeys(BaseSchema):
    bob_encrypting_key = character_fields.Key(dump_only=True)
    bob_verifying_key = character_fields.Key(dump_only=True)
