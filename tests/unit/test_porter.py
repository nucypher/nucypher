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
from nucypher.control.specifications.fields import StringList
from nucypher.crypto.kits import RetrievalKit as RetrievalKitClass
from nucypher.crypto.umbral_adapter import SecretKey, encrypt, Capsule as CapsuleClass
from nucypher.utilities.porter.control.specifications.fields import (
    HRAC,
    UrsulaChecksumAddress,
)
from nucypher.utilities.porter.control.specifications.fields.retrieve import RetrievalKit, Capsule
from tests.utils.policy import retrieval_request_setup


def test_hrac_field(enacted_federated_policy):
    hrac = enacted_federated_policy.treasure_map.hrac

    field = HRAC()
    serialized = field._serialize(value=hrac, attr=None, obj=None)
    assert serialized == bytes(hrac).hex()

    deserialized = field._deserialize(value=serialized, attr=None, data=None)
    assert deserialized == bytes(hrac)

    field._validate(value=bytes(hrac))
    with pytest.raises(InvalidInputData):
        field._validate(value=b'not hrac')


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


@pytest.mark.skip("To be fixed by follow-up PR")
def test_reencryption_request_field(enacted_federated_policy,
                                    federated_ursulas,
                                    federated_bob,
                                    federated_alice,
                                    get_random_checksum_address):
    # Setup
    ursula_address, request = retrieval_request_setup(enacted_federated_policy,
                                                         federated_ursulas,
                                                         federated_bob,
                                                         federated_alice)
    reencrypt_result = b"cfrags and signatures"

    # Test Work Order
    request_bytes = bytes(request)
    field = ReencryptionRequest()
    serialized = field._serialize(value=request, attr=None, obj=None)
    assert serialized == b64encode(request_bytes).decode()

    deserialized = field._deserialize(value=serialized, attr=None, data=None)
    assert deserialized == request_bytes

    # Test Work Order Result
    field = ReencryptionResult()
    serialized = field._serialize(value=reencrypt_result, attr=None, obj=None)
    assert serialized == b64encode(reencrypt_result).decode()

    deserialized = field.deserialize(value=serialized, attr=None, data=None)
    assert deserialized == reencrypt_result


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


def test_retrieval_kit_field():
    encrypting_key = SecretKey.random().public_key()
    capsule, _ = encrypt(encrypting_key, b'testing_retrieval_kit')

    retrieval_kit = RetrievalKitClass(capsule, set())

    field = RetrievalKit()
    serialized = field._serialize(value=retrieval_kit, attr=None, obj=None)
    assert serialized == b64encode(bytes(retrieval_kit)).decode()

    deserialized = field.deserialize(value=serialized, attr=None, data=None)
    assert isinstance(deserialized, RetrievalKitClass)
    assert deserialized.capsule == capsule
    assert len(deserialized.queried_addresses) == 0

    with pytest.raises(InvalidInputData):
        field.deserialize(value=b"non_base_64_data", attr=None, data=None)

    with pytest.raises(InvalidInputData):
        field.deserialize(value=b64encode(b"invalid_retrieval_kit_bytes").decode(), attr=None, data=None)


def test_capsule_field():
    encrypting_key = SecretKey.random().public_key()
    capsule, _ = encrypt(encrypting_key, b'testing_retrieval_kit')

    field = Capsule()
    serialized = field._serialize(value=capsule, attr=None, obj=None)
    assert serialized == b64encode(bytes(capsule)).decode()

    deserialized = field._deserialize(value=serialized, attr=None, data=None)
    assert isinstance(deserialized, CapsuleClass)
    assert deserialized == capsule

    with pytest.raises(InvalidInputData):
        field._deserialize(value=b64encode(b"faux_capsule").decode(), attr=None, data=None)
