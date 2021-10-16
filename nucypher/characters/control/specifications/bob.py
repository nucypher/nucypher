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

import nucypher.control.specifications.fields as base_fields
from nucypher.characters.control.specifications import fields as character_fields
from nucypher.characters.control.specifications.fields.treasuremap import EncryptedTreasureMap
from nucypher.cli import options
from nucypher.control.specifications.base import BaseSchema


class RetrieveAndDecrypt(BaseSchema):

    alice_verifying_key = character_fields.Key(
        required=True,
        load_only=True,
        click=options.option_alice_verifying_key(required=True)
    )
    message_kits = base_fields.StringList(
        character_fields.MessageKit(),
        required=True,
        load_only=True,
        click=options.option_message_kit(required=True, multiple=True)
    )
    encrypted_treasure_map = EncryptedTreasureMap(required=True,
                                                  load_only=True,
                                                  click=options.option_treasure_map)

    # output
    cleartexts = base_fields.List(character_fields.Cleartext(), dump_only=True)


class PublicKeys(BaseSchema):
    bob_encrypting_key = character_fields.Key(dump_only=True)
    bob_verifying_key = character_fields.Key(dump_only=True)
