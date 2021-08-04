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

from marshmallow import fields

from nucypher.control.specifications.exceptions import InvalidInputData
from nucypher.control.specifications.fields.base import BaseField
from nucypher.crypto.constants import HRAC_LENGTH, KECCAK_DIGEST_LENGTH


class TreasureMapID(BaseField, fields.String):

    def _validate(self, value):
        treasure_map_id = bytes.fromhex(value)
        # FIXME federated has map id length 32 bytes but decentralized has length 16 bytes ... huh? - #2725
        if len(treasure_map_id) != KECCAK_DIGEST_LENGTH and len(treasure_map_id) != HRAC_LENGTH:
            raise InvalidInputData(f"Could not convert input for {self.name} to a valid TreasureMap ID: invalid length")
