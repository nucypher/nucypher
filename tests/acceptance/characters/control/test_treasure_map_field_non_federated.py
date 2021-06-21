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

from nucypher.characters.control.specifications.fields import TreasureMap
from nucypher.control.specifications.exceptions import InvalidInputData


def test_treasure_map(enacted_blockchain_policy):
    treasure_map = enacted_blockchain_policy.treasure_map

    field = TreasureMap(federated_only=False)  # decentralized context
    serialized = field._serialize(value=treasure_map, attr=None, obj=None)
    assert serialized == b64encode(bytes(treasure_map)).decode()

    deserialized = field._deserialize(value=serialized, attr=None, data=None)
    assert deserialized == bytes(treasure_map)

    field._validate(value=bytes(treasure_map))

    with pytest.raises(InvalidInputData):
        field._validate(value=b"TreasureMap")
