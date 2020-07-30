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
from nucypher.config.splitters import BYTESTRING_REGISTRY


def test_treasuremap_serialization(mock_treasuremap):

    treasuremap = mock_treasuremap
    tm_splitter = treasuremap.splitter()
    treasuremap_bytes = bytes(treasuremap)

    assert treasuremap_bytes.startswith(
        tm_splitter.generate_checksum() + treasuremap.version.to_bytes(2, "big")
    )

    metadata = tm_splitter.get_metadata(treasuremap_bytes)
    assert metadata['version'] == 1
    assert metadata['checksum'] == tm_splitter.generate_checksum()


def test_treasuremap_deserialization(mock_treasuremap):

    treasuremap_bytes = bytes(mock_treasuremap)

    tm_from_bytes = mock_treasuremap.__class__.from_bytes(treasuremap_bytes)

    assert tm_from_bytes._hrac == mock_treasuremap._hrac
    assert bytes(tm_from_bytes.message_kit) == bytes(mock_treasuremap.message_kit)
    assert tm_from_bytes._public_signature == mock_treasuremap._public_signature


def test_message_kit_serialization(mock_messagekit):

    message_kit = mock_messagekit
    mk_splitter = message_kit.splitter()

    message_kit_bytes = message_kit.to_bytes()

    assert message_kit_bytes.startswith(
        mk_splitter.generate_checksum() + message_kit.version.to_bytes(2, "big"))

    metadata = mk_splitter.get_metadata(message_kit_bytes)
    assert metadata['version'] == 1
    assert metadata['checksum'] == mk_splitter.generate_checksum()


def test_messagekit_deserialization(mock_messagekit):

    messagekit_bytes = mock_messagekit.to_bytes()

    mk_from_bytes = mock_messagekit.__class__.from_bytes(messagekit_bytes)

    assert mk_from_bytes.ciphertext == mock_messagekit.ciphertext
    assert bytes(mk_from_bytes.capsule) == bytes(mk_from_bytes.capsule)
    assert mk_from_bytes.sender_verifying_key == mk_from_bytes.sender_verifying_key


def test_bytestring_registry(mock_treasuremap, mock_messagekit):
    tmap_checksum = mock_treasuremap.splitter().generate_checksum()
    mkit_checksum = mock_messagekit.splitter().generate_checksum()

    assert tmap_checksum in BYTESTRING_REGISTRY
    assert BYTESTRING_REGISTRY[tmap_checksum] is mock_treasuremap.__class__

    assert mkit_checksum in BYTESTRING_REGISTRY
    assert BYTESTRING_REGISTRY[mkit_checksum] is mock_messagekit.__class__


def test_decentralized_treasuremap_serialization(mock_decentralized_treasuremap):
    mock_treasuremap = mock_decentralized_treasuremap

    treasuremap = mock_treasuremap
    splitter = treasuremap.splitter()
    treasuremap_bytes = bytes(treasuremap)

    assert treasuremap_bytes.startswith(
        splitter.generate_checksum() + treasuremap.version.to_bytes(2, "big")
    )

    metadata = splitter.get_metadata(treasuremap_bytes)
    assert metadata['version'] == 1
    assert metadata['checksum'] == splitter.generate_checksum()


def test_decentralized_treasuremap_deserialization(mock_decentralized_treasuremap):
    mock_treasuremap = mock_decentralized_treasuremap

    treasuremap_bytes = bytes(mock_treasuremap)

    tm_from_bytes = mock_treasuremap.__class__.from_bytes(treasuremap_bytes)

    assert tm_from_bytes._hrac == mock_treasuremap._hrac
    assert bytes(tm_from_bytes.message_kit) == bytes(mock_treasuremap.message_kit)
    assert tm_from_bytes._public_signature == mock_treasuremap._public_signature
    assert tm_from_bytes._blockchain_signature == mock_treasuremap._blockchain_signature


def test_arrangement_serialization(mock_arrangement):

    arrangement = mock_arrangement
    splitter = arrangement.splitter

    arrangement_bytes = bytes(arrangement)

    assert arrangement_bytes.startswith(
        splitter.generate_checksum() + arrangement.version.to_bytes(2, "big"))

    metadata = splitter.get_metadata(arrangement_bytes)
    assert metadata['version'] == 1
    assert metadata['checksum'] == splitter.generate_checksum()


def test_arrangement_deserialization(mock_arrangement):

    arrangement_bytes = bytes(mock_arrangement)

    arrangment_from_bytes = mock_arrangement.__class__.from_bytes(arrangement_bytes)

    assert arrangment_from_bytes.alice.stamp == mock_arrangement.alice.stamp
    assert arrangment_from_bytes.id == mock_arrangement.id
    assert arrangment_from_bytes.expiration == mock_arrangement.expiration
