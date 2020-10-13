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

from bytestring_splitter import BytestringSplitter, VariableLengthBytestring
from marshmallow import fields

from nucypher.characters.control.specifications.exceptions import InvalidInputData, InvalidNativeDataTypes
from nucypher.characters.control.specifications.fields.base import BaseField
from nucypher.crypto.constants import HRAC_LENGTH
from nucypher.crypto.kits import UmbralMessageKit
from nucypher.crypto.signing import Signature


class TreasureMap(BaseField, fields.Field):

    def _serialize(self, value, attr, obj, **kwargs):
        return b64encode(bytes(value)).decode()

    def _deserialize(self, value, attr, data, **kwargs):
        try:
            return b64decode(value)
        except InvalidNativeDataTypes as e:
            raise InvalidInputData(f"Could not parse {self.name}: {e}")

    def _validate(self, value):

        splitter = BytestringSplitter(Signature,
                                  (bytes, HRAC_LENGTH),  # hrac
                                  (UmbralMessageKit, VariableLengthBytestring)
                                  )  # TODO: USe the one from TMap
        try:
            signature, hrac, tmap_message_kit = splitter(value)
            return True
        except InvalidNativeDataTypes as e:
            raise InvalidInputData(f"Could not parse {self.name}: {e}")
