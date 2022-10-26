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

import pytest
from nucypher_core.umbral import SecretKey

from nucypher.control.specifications.exceptions import InvalidInputData
from nucypher.utilities.porter.control.specifications.fields import Key


def test_key():
    field = Key()

    umbral_pub_key = SecretKey.random().public_key()
    other_umbral_pub_key = SecretKey.random().public_key()

    serialized = field._serialize(value=umbral_pub_key, attr=None, obj=None)
    assert serialized == bytes(umbral_pub_key).hex()
    assert serialized != bytes(other_umbral_pub_key).hex()

    deserialized = field._deserialize(value=serialized, attr=None, data=None)
    assert deserialized == umbral_pub_key
    assert deserialized != other_umbral_pub_key

    with pytest.raises(InvalidInputData):
        field._deserialize(value=b"PublicKey".hex(), attr=None, data=None)
