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

from base64 import b64decode, b64encode

from marshmallow import fields

from nucypher.characters.control.specifications.exceptions import InvalidInputData, InvalidNativeDataTypes
from nucypher.characters.control.specifications.fields.base import BaseField


class TreasureMap(BaseField, fields.Field):

    def _serialize(self, value, attr, obj, **kwargs):
        return b64encode(bytes(value)).decode()

    def _deserialize(self, value, attr, data, **kwargs):
        try:
            return b64decode(value)
        except InvalidNativeDataTypes as e:
            raise InvalidInputData(f"Could not parse {self.name}: {e}")

    def _validate(self, value):
        try:
            # Unsigned TreasureMap (Federated)
            from nucypher.policy.maps import TreasureMap as UnsignedTreasureMap
            splitter = UnsignedTreasureMap.get_splitter(value)
            splitter(value)
        except InvalidNativeDataTypes:
            try:
                # Signed TreasureMap (Blockchain)
                from nucypher.policy.maps import SignedTreasureMap
                splitter = SignedTreasureMap.get_splitter(value)
                splitter(value)
            except InvalidNativeDataTypes as e:
                raise InvalidInputData(f"Could not parse {self.name}: {e}")
        return True
