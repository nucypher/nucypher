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

from nucypher.core import EncryptedTreasureMap as EncryptedTreasureMapClass, TreasureMap as TreasureMapClass

from nucypher.control.specifications.exceptions import InvalidInputData
from nucypher.control.specifications.fields.base import Base64BytesRepresentation


class EncryptedTreasureMap(Base64BytesRepresentation):
    """
    JSON Parameter representation of EncryptedTreasureMap.
    """
    def _deserialize(self, value, attr, data, **kwargs):
        try:
            encrypted_treasure_map_bytes = super()._deserialize(value, attr, data, **kwargs)
            return EncryptedTreasureMapClass.from_bytes(encrypted_treasure_map_bytes)
        except Exception as e:
            raise InvalidInputData(f"Could not convert input for {self.name} to an EncryptedTreasureMap: {e}") from e


class TreasureMap(Base64BytesRepresentation):
    """
    JSON Parameter representation of (unencrypted) TreasureMap.
    """
    def _deserialize(self, value, attr, data, **kwargs):
        try:
            treasure_map_bytes = super()._deserialize(value, attr, data, **kwargs)
            return TreasureMapClass.from_bytes(treasure_map_bytes)
        except Exception as e:
            raise InvalidInputData(f"Could not convert input for {self.name} to a TreasureMap: {e}") from e
