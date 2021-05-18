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

from pathlib import Path

import pytest
from constant_sorrow.constants import KEYRING_LOCKED

from nucypher.crypto.keystore import Keystore, InvalidPassword
from nucypher.crypto.keystore import (
    _assemble_keystore,
    _serialize_keystore,
    _deserialize_keystore,
    _write_keystore,
    _read_keystore
)
from nucypher.crypto.powers import DecryptingPower
from tests.constants import INSECURE_DEVELOPMENT_PASSWORD


def test_invalid_keystore_path(tmp_path):
    path = Path()
    with pytest.raises(ValueError, match="Keystore path must be a file."):
        _keystore = Keystore(path)

    path = Path(tmp_path)
    with pytest.raises(ValueError, match="Keystore path must be a file."):
        _keystore = Keystore(path)

    path = Path('does-not-exist')
    with pytest.raises(Keystore.NotFound, match=f"Keystore '{str(path)}' does not exist."):
        _keystore = Keystore(path)


def test_keystore_defaults(tmp_path_factory):
    parent = Path(tmp_path_factory.mktemp('test-keystore-'))
    parent.touch(exist_ok=True)
    path = parent / '123-deadbeef.priv'
    path.touch()
    keystore = Keystore(path)
    assert keystore.keystore_path == path
    assert keystore.id == 'deadbeef'
    assert not keystore.is_unlocked


def test_keyring_invalid_password(tmpdir):
    with pytest.raises(InvalidPassword):
        _keystore = Keystore.generate(keystore_dir=tmpdir, password='short')


def test_keyring_lock_unlock(tmpdir):
    keystore = Keystore.generate(keystore_dir=tmpdir, password=INSECURE_DEVELOPMENT_PASSWORD)

    # locked by default
    assert not keystore.is_unlocked
    assert keystore._Keystore__secret is KEYRING_LOCKED

    # unlock
    keystore.unlock(INSECURE_DEVELOPMENT_PASSWORD)
    assert keystore.is_unlocked
    assert keystore._Keystore__secret != KEYRING_LOCKED
    assert isinstance(keystore._Keystore__secret, bytes)

    # unlock when already unlocked
    keystore.unlock(INSECURE_DEVELOPMENT_PASSWORD)
    assert keystore.is_unlocked

    # lock
    keystore.lock()
    assert not keystore.is_unlocked

    # lock when already locked
    keystore.lock()
    assert not keystore.is_unlocked


def test_keyring_derive_crypto_power_without_unlock(tmpdir):
    keystore = Keystore.generate(keystore_dir=tmpdir, password=INSECURE_DEVELOPMENT_PASSWORD)
    with pytest.raises(Keystore.Locked):
        keystore.derive_crypto_power(power_class=DecryptingPower)


def test_keystore_serializer():
    encrypted_secret, salt = b'peanuts! Get your peanuts!', b'sea salt'
    payload = _assemble_keystore(encrypted_secret=encrypted_secret, salt=salt)
    serialized_payload = _serialize_keystore(payload)
    deserialized_key_data = _deserialize_keystore(serialized_payload)
    assert deserialized_key_data['key'] == encrypted_secret
    assert deserialized_key_data['salt'] == salt


def test_write_read_private_keyfile(temp_dir_path):
    temp_filepath = Path(temp_dir_path) / "test_private_key_serialization_file"
    encrypted_secret, salt = b'peanuts! Get your peanuts!', b'sea salt'
    payload = _assemble_keystore(encrypted_secret=encrypted_secret, salt=salt)
    _write_keystore(path=temp_filepath, payload=payload, serializer=_serialize_keystore)
    deserialized_payload_from_file = _read_keystore(path=temp_filepath, deserializer=_deserialize_keystore)
    assert deserialized_payload_from_file['key'] == encrypted_secret
    assert deserialized_payload_from_file['salt'] == salt


#
# def test_keyring_restoration(tmpdir):
#     keyring = _generate_keyring(tmpdir)
#     keyring.unlock(password=INSECURE_DEVELOPMENT_PASSWORD)
#
#     account = keyring.account
#     checksum_address = keyring.checksum_address
#     certificate_filepath = keyring.certificate_filepath
#     encrypting_public_key_hex = keyring.encrypting_public_key.hex()
#     signing_public_key_hex = keyring.signing_public_key.hex()
#
#     # tls power
#     tls_hosting_power = keyring.derive_crypto_power(power_class=TLSHostingPower, host=LOOPBACK_ADDRESS)
#     tls_hosting_power_public_key_numbers = tls_hosting_power.public_key().public_numbers()
#     tls_hosting_power_certificate_public_bytes = \
#         tls_hosting_power.keypair.certificate.public_bytes(encoding=Encoding.PEM)
#     tls_hosting_power_certificate_filepath = tls_hosting_power.keypair.certificate_filepath
#
#     # decrypting power
#     decrypting_power = keyring.derive_crypto_power(power_class=DecryptingPower)
#     decrypting_power_public_key_hex = decrypting_power.public_key().hex()
#     decrypting_power_fingerprint = decrypting_power.keypair.fingerprint()
#
#     # signing power
#     signing_power = keyring.derive_crypto_power(power_class=SigningPower)
#     signing_power_public_key_hex = signing_power.public_key().hex()
#     signing_power_fingerprint = signing_power.keypair.fingerprint()
#
#     # get rid of object, but not persistent data
#     del keyring
#
#     restored_keyring = Keystore(keyring_root=tmpdir, account=account)
#     restored_keyring.unlock(password=INSECURE_DEVELOPMENT_PASSWORD)
#
#     assert restored_keyring.account == account
#     assert restored_keyring.checksum_address == checksum_address
#     assert restored_keyring.certificate_filepath == certificate_filepath
#     assert restored_keyring.encrypting_public_key.hex() == encrypting_public_key_hex
#     assert restored_keyring.signing_public_key.hex() == signing_public_key_hex
#
#     # tls power
#     restored_tls_hosting_power = restored_keyring.derive_crypto_power(power_class=TLSHostingPower,
#                                                                       host=LOOPBACK_ADDRESS)
#     assert restored_tls_hosting_power.public_key().public_numbers() == tls_hosting_power_public_key_numbers
#     assert restored_tls_hosting_power.keypair.certificate.public_bytes(encoding=Encoding.PEM) == \
#            tls_hosting_power_certificate_public_bytes
#     assert restored_tls_hosting_power.keypair.certificate_filepath == tls_hosting_power_certificate_filepath
#
#     # decrypting power
#     restored_decrypting_power = restored_keyring.derive_crypto_power(power_class=DecryptingPower)
#     assert restored_decrypting_power.public_key().hex() == decrypting_power_public_key_hex
#     assert restored_decrypting_power.keypair.fingerprint() == decrypting_power_fingerprint
#
#     # signing power
#     restored_signing_power = restored_keyring.derive_crypto_power(power_class=SigningPower)
#     assert restored_signing_power.public_key().hex() == signing_power_public_key_hex
#     assert restored_signing_power.keypair.fingerprint() == signing_power_fingerprint
