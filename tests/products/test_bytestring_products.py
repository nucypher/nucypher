import pytest


def test_treasuremap_serialization(mock_treasuremap):

    treasuremap = mock_treasuremap
    tm_splitter = treasuremap.splitter
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