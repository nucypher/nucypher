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
import datetime
from base64 import b64encode, b64decode

import maya
import pytest

from nucypher.core import MessageKit as MessageKitClass

from nucypher.crypto.umbral_adapter import SecretKey, Signer
from nucypher.characters.control.specifications.fields import (
    DateTime,
    FileField,
    Key,
    MessageKit,
    UmbralSignature,
    EncryptedTreasureMap
)
from nucypher.characters.lawful import Enrico
from nucypher.control.specifications.exceptions import InvalidInputData


#
# FIXME currently fails, 'Label' also has inconsistency - see #2714
# def test_cleartext():
#     field = Cleartext()
#
#     data = b"sdasdadsdad"
#     serialized = field._serialize(value=data, attr=None, obj=None)
#
#     deserialized = field._deserialize(value=serialized, attr=None, data=None)
#     assert deserialized == data


def test_file(tmpdir):
    text = b"I never saw a wild thing sorry for itself. A small bird will drop frozen dead from a bough without " \
           b"ever having felt sorry for itself."  # -- D.H. Lawrence

    filepath = tmpdir / "dh_lawrence.txt"
    with open(filepath, 'wb') as f:
        f.write(text)

    file_field = FileField()
    deserialized = file_field._deserialize(value=filepath, attr=None, data=None)
    assert deserialized == text

    file_field._validate(value=filepath)

    non_existent_file = tmpdir / "non_existent_file.txt"
    file_field._validate(value=non_existent_file)


def test_date_time():
    field = DateTime()

    # test data
    now = maya.now()

    serialized = field._serialize(value=now, attr=None, obj=None)
    assert serialized == now.iso8601()

    deserialized = field._deserialize(value=serialized, attr=None, data=None)
    assert deserialized == now

    # modified time
    new_time = now + datetime.timedelta(hours=5)

    serialized_new_time = field._serialize(value=new_time, attr=None, obj=None)
    assert serialized_new_time != now.iso8601()
    assert serialized_new_time == new_time.iso8601()

    deserialized_new_time = field._deserialize(value=serialized_new_time, attr=None, data=None)
    assert deserialized_new_time != now
    assert deserialized_new_time == new_time

    # invalid date
    with pytest.raises(InvalidInputData):
        field._deserialize(value="test", attr=None, data=None)


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


def test_message_kit(enacted_federated_policy, federated_alice):
    # Setup
    enrico = Enrico.from_alice(federated_alice, label=enacted_federated_policy.label)
    message = 'this is a message'
    plaintext_bytes = bytes(message, encoding='utf-8')
    message_kit = enrico.encrypt_message(plaintext=plaintext_bytes)
    message_kit_bytes = bytes(message_kit)
    message_kit = MessageKitClass.from_bytes(message_kit_bytes)

    # Test
    field = MessageKit()
    serialized = field._serialize(value=message_kit, attr=None, obj=None)
    assert serialized == b64encode(bytes(message_kit)).decode()

    deserialized = field._deserialize(value=serialized, attr=None, data=None)
    assert deserialized == message_kit

    with pytest.raises(InvalidInputData):
        field._deserialize(value=b"MessageKit", attr=None, data=None)


def test_umbral_signature():
    umbral_priv_key = SecretKey.random()
    signer = Signer(umbral_priv_key)

    message = b'this is a message'
    signature = signer.sign(message)
    other_signature = signer.sign(b'this is a different message')

    field = UmbralSignature()
    serialized = field._serialize(value=signature, attr=None, obj=None)
    assert serialized == b64encode(bytes(signature)).decode()
    assert serialized != b64encode(bytes(other_signature)).decode()

    deserialized = field._deserialize(value=serialized, attr=None, data=None)
    assert deserialized == signature
    assert deserialized != other_signature

    field._validate(value=bytes(signature))
    field._validate(value=bytes(other_signature))

    with pytest.raises(InvalidInputData):
        field._validate(value=b"UmbralSignature")


def test_treasure_map(enacted_federated_policy):
    treasure_map = enacted_federated_policy.treasure_map

    field = EncryptedTreasureMap()
    serialized = field._serialize(value=treasure_map, attr=None, obj=None)
    assert serialized == b64encode(bytes(treasure_map)).decode()

    deserialized = field._deserialize(value=serialized, attr=None, data=None)
    assert deserialized == treasure_map

    with pytest.raises(InvalidInputData):
        field._deserialize(value=b64encode(b"TreasureMap").decode(), attr=None, data=None)
