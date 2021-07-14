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
from base64 import b64encode

import pytest

from nucypher.control.specifications.exceptions import InvalidInputData
from nucypher.control.specifications.fields import PositiveInteger, StringList, String, Base64BytesRepresentation


def test_positive_integer_field():
    field = PositiveInteger()

    field._validate(value=1)
    field._validate(value=10000)
    field._validate(value=1234567890)
    field._validate(value=22)

    invalid_values = [0, -1, -2, -10, -1000000, -12312311]
    for invalid_value in invalid_values:
        with pytest.raises(InvalidInputData):
            field._validate(value=invalid_value)


def test_string_list_field():
    field = StringList(String)

    data = 'Cornsilk,November,Sienna,India'
    deserialized = field._deserialize(value=data, attr=None, data=None)
    assert deserialized == ['Cornsilk', 'November', 'Sienna', 'India']

    data = ['Cornsilk', 'November', 'Sienna', 'India']
    deserialized = field._deserialize(value=data, attr=None, data=None)
    assert deserialized == data


def test_base64_representation_field():
    field = Base64BytesRepresentation()

    data = b"man in the arena"
    serialized = field._serialize(value=data, attr=None, obj=None)
    assert serialized == b64encode(data).decode()

    deserialized = field._deserialize(value=serialized, attr=None, data=None)
    assert deserialized == data

    with pytest.raises(InvalidInputData):
        # attempt to deserialize none base64 data
        field._deserialize(value=b"raw bytes with non base64 chars ?&^%", attr=None, data=None)
