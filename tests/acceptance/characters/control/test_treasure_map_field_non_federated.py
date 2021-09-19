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

from nucypher.characters.control.specifications.fields import EncryptedTreasureMap
from nucypher.control.specifications.exceptions import InvalidInputData


def test_treasure_map(enacted_blockchain_policy):
    treasure_map = enacted_blockchain_policy.treasure_map

    field = EncryptedTreasureMap()
    serialized = field._serialize(value=treasure_map, attr=None, obj=None)
    assert serialized == b64encode(bytes(treasure_map)).decode()

    deserialized = field._deserialize(value=serialized, attr=None, data=None)
    assert deserialized == treasure_map

    with pytest.raises(InvalidInputData):
        field._deserialize(value=b64encode(b"TreasureMap").decode(), attr=None, data=None)
