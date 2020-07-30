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
from nucypher.crypto.kits import UmbralMessageKit as UmbralMessageKitClass
from nucypher.config.splitters import BYTESTRING_REGISTRY


class UmbralMessageKit(BaseField, fields.Field):

    def _serialize(self, value: UmbralMessageKitClass, attr, obj, **kwargs):
        return b64encode(value.to_bytes()).decode()

    def _deserialize(self, value, attr, data, **kwargs):
        if isinstance(value, bytes):
            return value
        try:
            return b64decode(value)
        except InvalidNativeDataTypes as e:
            raise InvalidInputData(f"Could not parse {self.name}: {e}")

    def _validate(self, value):

        try:
            value = b64decode(value)
            metadata = UmbralMessageKitClass.splitter().get_metadata(value)

            if not UmbralMessageKitClass.splitter().validate_checksum(value):
                if metadata['checksum'] in BYTESTRING_REGISTRY:
                    raise InvalidInputData(f"Input data seems to be the bytes for a {BYTESTRING_REGISTRY[metadata['checksum']].__name__} and not a MessageKit")
                raise InvalidInputData(f"Could not validate supplied MessageKit bytes against known any supported bytestring formats")

            if metadata['version'] > UmbralMessageKitClass.version:
                raise InvalidInputData("Version incompatibility.  Please update your NuCypher Software")
            return True

        except InvalidNativeDataTypes as e:
            raise InvalidInputData(f"Could not parse {self.name}: {e}")
