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

from nucypher.utilities.versioning import Versioned
import pytest


class A(Versioned):

    def __init__(self, x):
        self.x = x

    @classmethod
    def _brand(cls):
        return b"AA"

    @classmethod
    def _version(cls):
        return 2

    def _payload(self) -> bytes:
        return bytes(self.x)

    @classmethod
    def _old_version_handlers(cls):
        return {1: cls._from_bytes_v1}

    @classmethod
    def _from_bytes_v1(cls, data):
        return cls(int(data))  # we used to keep it in decimal representation

    @classmethod
    def _from_bytes_current(cls, data):
        return cls(int(data, 16))  # but now we switched to the hexadecimal


def test_versioning_header_prepend():
    a = A(1)  # stake sauce
    serialized = bytes(a)
    header = serialized[:Versioned._HEADER_SIZE]
    brand = header[:Versioned._BRAND_LENGTH]
    assert brand == A._brand()
    version = header[Versioned._BRAND_LENGTH:]
    version_number = int.from_bytes(version, 'big')
    assert version_number == A._version()


def test_versioning_brand():
    invalid = b'\x00\x03\x00\x0112'
    with pytest.raises(Versioned.InvalidHeader, match="Incompatible bytes for A."):
        A.from_bytes(invalid)
    incorrect = b'AB\x00\x0112'
    with pytest.raises(Versioned.InvalidHeader, match="Incorrect brand. Expected b'AA', Got b'AB'."):
        A.from_bytes(incorrect)


def test_versioning_handlers():
    s1 = b'AA\x00\x0112'
    s2 = b'AA\x00\x0212'
    a1 = A.from_bytes(s1)
    assert a1.x == 12
    a2 = A.from_bytes(s2)
    assert a2.x == 18
