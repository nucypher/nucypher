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

import os
from marshmallow import fields

from nucypher.characters.control.specifications.exceptions import InvalidInputData, InvalidNativeDataTypes
from nucypher.characters.control.specifications.fields.base import BaseField


class FileField(BaseField, fields.String):

    def _deserialize(self, value, attr, data, **kwargs):
        with open(value, 'rb') as plaintext_file:
            plaintext = plaintext_file.read()  # TODO: #2106 Handle large files
        return plaintext

    def _validate(self, value):
        return os.path.exists(value) and os.path.isfile(value)
