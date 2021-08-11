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

from eth_utils import to_checksum_address
from marshmallow import fields

from nucypher.characters.control.specifications.fields import Key
from nucypher.cli import types
from nucypher.control.specifications.base import BaseSchema
from nucypher.control.specifications.exceptions import InvalidInputData
from nucypher.control.specifications.fields import String


class UrsulaChecksumAddress(String):
    """Ursula checksum address."""
    click_type = types.EIP55_CHECKSUM_ADDRESS

    def _deserialize(self, value, attr, data, **kwargs):
        try:
            return to_checksum_address(value=value)
        except ValueError as e:
            raise InvalidInputData(f"Could not convert input for {self.name} to a valid checksum address: {e}")


class UrsulaInfoSchema(BaseSchema):
    """Schema for the result of sampling of Ursulas."""
    checksum_address = UrsulaChecksumAddress()
    uri = fields.URL()
    encrypting_key = Key()

    # maintain field declaration ordering
    class Meta:
        ordered = True
