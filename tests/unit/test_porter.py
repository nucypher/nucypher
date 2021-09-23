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

from nucypher.core import RetrievalKit as RetrievalKitClass

from nucypher.control.specifications.exceptions import InvalidInputData
from nucypher.control.specifications.fields import StringList
from nucypher.crypto.umbral_adapter import SecretKey, encrypt
from nucypher.utilities.porter.control.specifications.fields import HRAC, UrsulaChecksumAddress
from nucypher.utilities.porter.control.specifications.fields.retrieve import RetrievalKit


def test_hrac_field(enacted_federated_policy):
    hrac = enacted_federated_policy.treasure_map.hrac

    field = HRAC()
    serialized = field._serialize(value=hrac, attr=None, obj=None)
    assert serialized == bytes(hrac).hex()

    deserialized = field._deserialize(value=serialized, attr=None, data=None)
    assert deserialized == hrac

    with pytest.raises(InvalidInputData):
        field._deserialize(value=b'not hrac', attr=None, data=None)


def test_ursula_checksum_address_field(get_random_checksum_address):
    ursula_checksum = get_random_checksum_address()
    other_address = get_random_checksum_address()

    assert ursula_checksum != other_address

    field = UrsulaChecksumAddress()
    serialized = field._serialize(value=ursula_checksum, attr=None, obj=None)
    assert serialized == ursula_checksum
    assert serialized != other_address

    deserialized = field._deserialize(value=serialized, attr=None, data=None)
    assert deserialized == ursula_checksum
    assert deserialized != other_address

    field._deserialize(value=ursula_checksum, attr=None, data=None)
    field._deserialize(value=ursula_checksum.lower(), attr=None, data=None)
    field._deserialize(value=ursula_checksum.upper(), attr=None, data=None)
    field._deserialize(value=other_address, attr=None, data=None)
    field._deserialize(value=other_address.lower(), attr=None, data=None)
    field._deserialize(value=other_address.upper(), attr=None, data=None)

    with pytest.raises(InvalidInputData):
        field._deserialize(value="0xdeadbeef", attr=None, data=None)


def test_ursula_checksum_address_string_list_field(get_random_checksum_address):
    ursula_1 = get_random_checksum_address()
    ursula_2 = get_random_checksum_address()
    ursula_3 = get_random_checksum_address()
    ursula_4 = get_random_checksum_address()

    assert ursula_1 != ursula_2
    assert ursula_2 != ursula_3
    assert ursula_3 != ursula_4

    field = StringList(UrsulaChecksumAddress)

    deserialized = field._deserialize(value=f"{ursula_1},{ursula_2},{ursula_3},{ursula_4}", attr=None, data=None)
    assert deserialized == [ursula_1, ursula_2, ursula_3, ursula_4]

    # list instead
    data = [ursula_1, ursula_2, ursula_3, ursula_4]
    deserialized = field._deserialize(value=data, attr=None, data=None)
    assert deserialized == data

    # single entry
    deserialized = field._deserialize(value=f"{ursula_1}", attr=None, data=None)
    assert deserialized == [ursula_1]

    deserialized = field._deserialize(value=[ursula_1], attr=None, data=None)
    assert deserialized == [ursula_1]

    with pytest.raises(InvalidInputData):
        field._deserialize(value="0xdeadbeef", attr=None, data=None)

    with pytest.raises(InvalidInputData):
        field._deserialize(value=f"{ursula_1},{ursula_2},{ursula_3},{ursula_4},0xdeadbeef", attr=None, data=None)


def test_retrieval_kit_field(get_random_checksum_address):
    field = RetrievalKit()

    def run_tests_on_kit(kit: RetrievalKitClass):
        serialized = field._serialize(value=kit, attr=None, obj=None)
        assert serialized == b64encode(bytes(kit)).decode()

        deserialized = field._deserialize(value=serialized, attr=None, data=None)
        assert isinstance(deserialized, RetrievalKitClass)
        assert deserialized.capsule == kit.capsule
        assert deserialized.queried_addresses == kit.queried_addresses

    # kit with list of ursulas
    encrypting_key = SecretKey.random().public_key()
    capsule, _ = encrypt(encrypting_key, b'testing retrieval kit with 2 ursulas')
    ursulas = [get_random_checksum_address(), get_random_checksum_address()]
    run_tests_on_kit(kit=RetrievalKitClass(capsule, ursulas))

    # kit with no ursulas
    encrypting_key = SecretKey.random().public_key()
    capsule, _ = encrypt(encrypting_key, b'testing retrieval kit with no ursulas')
    run_tests_on_kit(kit=RetrievalKitClass(capsule, []))

    with pytest.raises(InvalidInputData):
        field._deserialize(value=b"non_base_64_data", attr=None, data=None)

    with pytest.raises(InvalidInputData):
        field._deserialize(value=b64encode(b"invalid_retrieval_kit_bytes").decode(), attr=None, data=None)
