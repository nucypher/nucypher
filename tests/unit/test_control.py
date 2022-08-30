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
import json
from base64 import b64encode

import pytest

from nucypher.control.specifications.exceptions import InvalidInputData
from nucypher.control.specifications.fields import (
    Base64BytesRepresentation,
    Base64JSON,
    PositiveInteger,
    String,
    StringList,
)


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
        # attempt to serialize a non-serializable object
        field._serialize(value=Exception("non-serializable"), attr=None, obj=None)

    with pytest.raises(InvalidInputData):
        # attempt to deserialize none base64 data
        field._deserialize(value=b"raw bytes with non base64 chars ?&^%", attr=None, data=None)


def test_base64_json_field():
    # test data
    dict_data = {
        "domain": {"name": "tdec", "version": 1, "chainId": 1, "salt": "blahblahblah"},
        "message": {
            "address": "0x03e75d7dd38cce2e20ffee35ec914c57780a8e29",
            "conditions": b64encode(
                "random condition for reencryption".encode()
            ).decode(),
            "blockNumber": 15440685,
            "blockHash": "0x2220da8b777767df526acffd5375ebb340fc98e53c1040b25ad1a8119829e3bd",
        },
    }
    list_data = [12.5, 1.2, 4.3]
    str_data = "Everything in the universe has a rhythm, everything dances."  # -- Maya Angelou
    num_data = 1234567890
    bool_data = True

    # test serialization/deserialization of data
    test_data = [dict_data, list_data, str_data, num_data, bool_data]
    field = Base64JSON()
    for d in test_data:
        serialized = field._serialize(value=d, attr=None, obj=None)
        assert serialized == b64encode(json.dumps(d).encode()).decode()

        deserialized = field._deserialize(value=serialized, attr=None, data=None)
        assert deserialized == d

    with pytest.raises(InvalidInputData):
        # attempt to serialize non-json serializable object
        field._serialize(value=Exception("non-serializable"), attr=None, obj=None)

    with pytest.raises(InvalidInputData):
        # attempt to deserialize invalid data
        field._deserialize(
            value=b"raw bytes with non base64 chars ?&^%", attr=None, data=None
        )
