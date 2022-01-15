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


import re
from typing import Tuple, Any, Type

import pytest

from nucypher.utilities.versioning import Versioned


def _check_valid_version_tuple(version: Any, cls: Type):
    if not isinstance(version, tuple):
        pytest.fail(f"Old version handlers keys for {cls.__name__} must be a tuple")
    if not len(version) == Versioned._VERSION_PARTS:
        pytest.fail(f"Old version handlers keys for {cls.__name__} must be a {str(Versioned._VERSION_PARTS)}-tuple")
    if not all(isinstance(part, int) for part in version):
        pytest.fail(f"Old version handlers version parts {cls.__name__} must be integers")


class A(Versioned):

    def __init__(self, x: int):
        self.x = x

    @classmethod
    def _brand(cls):
        return b"ABCD"

    @classmethod
    def _version(cls) -> Tuple[int, int]:
        return 2, 1

    def _payload(self) -> bytes:
        return self.x.to_bytes(1, 'big')

    @classmethod
    def _old_version_handlers(cls):
        return {
            (2, 0): cls._from_bytes_v2_0,
        }

    @classmethod
    def _from_bytes_v2_0(cls, data):
        # v2.0 saved a 4 byte integer in hex format
        int_hex, remainder = data[:2], data[2:]
        int_bytes = bytes.fromhex(int_hex.decode())
        return cls(int.from_bytes(int_bytes, 'big')), remainder

    @classmethod
    def _from_bytes_current(cls, data):
        # v2.1 saves a 4 byte integer as 4 bytes
        int_bytes, remainder = data[:1], data[1:]
        return cls(int.from_bytes(int_bytes, 'big')), remainder


def test_unique_branding():
    brands = tuple(v._brand() for v in Versioned.__subclasses__())
    brands_set = set(brands)
    if len(brands) != len(brands_set):
        duplicate_brands = list(brands)
        for brand in brands_set:
            duplicate_brands.remove(brand)
        pytest.fail(f"Duplicated brand(s) {duplicate_brands}.")


def test_valid_branding():
    for cls in Versioned.__subclasses__():
        if len(cls._brand()) != cls._BRAND_SIZE:
            pytest.fail(f"Brand must be exactly {str(Versioned._BRAND_SIZE)} bytes.")
        if not re.fullmatch(rb'\w+', cls._brand()):
            pytest.fail(f"Brand must be alphanumeric; Got {cls._brand()}")

def test_valid_version_implementation():
    for cls in Versioned.__subclasses__():
        _check_valid_version_tuple(version=cls._version(), cls=cls)


def test_valid_old_handlers_index():
    for cls in Versioned.__subclasses__():
        for version in cls._deserializers():
            _check_valid_version_tuple(version=version, cls=cls)


def test_version_metadata():
    major, minor = A._version()
    assert A.version_string() == f'{major}.{minor}'


def test_versioning_header_prepend():
    a = A(1)  # stake sauce
    assert a.x == 1

    serialized = bytes(a)
    assert len(serialized) > Versioned._HEADER_SIZE

    header = serialized[:Versioned._HEADER_SIZE]
    brand = header[:Versioned._BRAND_SIZE]
    assert brand == A._brand()

    version = header[Versioned._BRAND_SIZE:]
    major, minor = version[:Versioned._VERSION_PART_SIZE], version[Versioned._VERSION_PART_SIZE:]
    major_number = int.from_bytes(major, 'big')
    minor_number = int.from_bytes(minor, 'big')
    assert (major_number, minor_number) == A._version()


def test_versioning_input_too_short():
    empty = b'ABCD\x00\x01'
    with pytest.raises(ValueError, match='Invalid bytes for A.'):
        A.from_bytes(empty)
        

def test_versioning_empty_payload():
    empty = b'ABCD\x00\x02\x00\x01'
    with pytest.raises(ValueError, match='No content to deserialize A.'):
        A.from_bytes(empty)


def test_versioning_invalid_brand():
    invalid = b'\x01\x02\x00\x03\x00\x0112'
    with pytest.raises(Versioned.InvalidHeader, match="Incompatible bytes for A."):
        A.from_bytes(invalid)

    # A partially invalid brand, to check that the regexp validates
    # the whole brand and not just the beginning of it.
    invalid = b'ABC \x00\x02\x00\x0112'
    with pytest.raises(Versioned.InvalidHeader, match="Incompatible bytes for A."):
        A.from_bytes(invalid)


def test_versioning_incorrect_brand():
    incorrect = b'ABAB\x00\x0112'
    with pytest.raises(Versioned.InvalidHeader, match="Incorrect brand. Expected b'ABCD', Got b'ABAB'."):
        A.from_bytes(incorrect)


def test_unknown_future_major_version():
    empty = b'ABCD\x00\x03\x00\x0212'
    message = 'Incompatible versioned bytes for A. Compatible version is 2.x, Got 3.2.'
    with pytest.raises(ValueError, match=message):
        A.from_bytes(empty)


def test_incompatible_old_major_version(mocker):
    current_spy = mocker.spy(A, "_from_bytes_current")
    v1_data = b'ABCD\x00\x01\x00\x0012'
    message = 'Incompatible versioned bytes for A. Compatible version is 2.x, Got 1.0.'
    with pytest.raises(Versioned.IncompatibleVersion, match=message):
        A.from_bytes(v1_data)
    assert not current_spy.call_count


def test_incompatible_future_major_version(mocker):
    current_spy = mocker.spy(A, "_from_bytes_current")
    v1_data = b'ABCD\x00\x03\x00\x0012'
    message = 'Incompatible versioned bytes for A. Compatible version is 2.x, Got 3.0.'
    with pytest.raises(Versioned.IncompatibleVersion, match=message):
        A.from_bytes(v1_data)
    assert not current_spy.call_count


def test_resolve_version():
    # past
    v2_0 = 2, 0
    resolved_version = A._resolve_version(version=v2_0)
    assert resolved_version == v2_0

    # present
    v2_1 = 2, 1
    resolved_version = A._resolve_version(version=v2_1)
    assert resolved_version == v2_1

    # future minor version resolves to the latest minor version.
    v2_2 = 2, 2
    resolved_version = A._resolve_version(version=v2_2)
    assert resolved_version == v2_1


def test_old_minor_version_handler_routing(mocker):
    current_spy = mocker.spy(A, "_from_bytes_current")
    v2_0_spy = mocker.spy(A, "_from_bytes_v2_0")

    # Old minor version
    v2_0_data = b'ABCD\x00\x02\x00\x0012'
    a = A.from_bytes(v2_0_data)
    assert a.x == 18

    # Old minor version was correctly routed to the v2.0 handler.
    assert v2_0_spy.call_count == 1
    v2_0_spy.assert_called_with(b'12')
    assert not current_spy.call_count


def test_current_minor_version_handler_routing(mocker):
    current_spy = mocker.spy(A, "_from_bytes_current")
    v2_0_spy = mocker.spy(A, "_from_bytes_v2_0")

    v2_1_data = b'ABCD\x00\x02\x00\x01\x12'
    a = A.from_bytes(v2_1_data)
    assert a.x == 18

    # Current version was correctly routed to the v2.1 handler.
    assert current_spy.call_count == 1
    current_spy.assert_called_with(b'\x12')
    assert not v2_0_spy.call_count


def test_future_minor_version_handler_routing(mocker):
    current_spy = mocker.spy(A, "_from_bytes_current")
    v2_0_spy = mocker.spy(A, "_from_bytes_v2_0")

    v2_2_data = b'ABCD\x00\x02\x02\x01\x12'
    a = A.from_bytes(v2_2_data)
    assert a.x == 18

    # Future minor version was correctly routed to
    # the current minor version handler.
    assert current_spy.call_count == 1
    current_spy.assert_called_with(b'\x12')
    assert not v2_0_spy.call_count
