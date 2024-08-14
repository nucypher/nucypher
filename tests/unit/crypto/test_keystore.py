import os
import random
import string
from pathlib import Path

import pytest
from constant_sorrow.constants import KEYSTORE_LOCKED
from cryptography.hazmat.primitives._serialization import Encoding
from mnemonic.mnemonic import Mnemonic
from nucypher_core.umbral import SecretKeyFactory

from nucypher.crypto.constants import _ENTROPY_BITS
from nucypher.crypto.keystore import (
    _DELEGATING_INFO,
    _MNEMONIC_LANGUAGE,
    InvalidPassword,
    Keystore,
    _assemble_keystore,
    _deserialize_keystore,
    _read_keystore,
    _serialize_keystore,
    _write_keystore,
    validate_keystore_filename,
)
from nucypher.crypto.powers import (
    DecryptingPower,
    DelegatingPower,
    SigningPower,
    ThresholdRequestDecryptingPower,
    TLSHostingPower,
)
from nucypher.utilities.networking import LOOPBACK_ADDRESS
from tests.constants import INSECURE_DEVELOPMENT_PASSWORD


@pytest.fixture
def mnemonic():
    _mnemonic = Mnemonic(_MNEMONIC_LANGUAGE)
    return _mnemonic.generate(strength=_ENTROPY_BITS)


def test_invalid_keystore_path_parts(tmp_path, tmp_path_factory):

    # Setup
    not_hex = 'h' + ''.join(random.choice(string.ascii_letters) for _ in range(Keystore._ID_SIZE))
    invalid_paths = (
        'nosuffix',                 # missing suffix
        'deadbeef.priv',            # missing created epoch
        f'123-{not_hex[:3]}.priv',  # too short
        f'123-{not_hex}.priv',      # not hex
    )

    # Test
    for invalid_path in invalid_paths:
        invalid_path = Path(invalid_path)
        with pytest.raises(Keystore.Invalid, match=f'{invalid_path} is not a valid keystore filename'):
            validate_keystore_filename(path=invalid_path)


def test_invalid_keystore_file_type(tmp_path, tmp_path_factory):

    # Not a file
    invalid_path = Path()
    with pytest.raises(ValueError, match="Keystore path must be a file."):
        _keystore = Keystore(invalid_path)
    invalid_path = Path(tmp_path)
    with pytest.raises(ValueError, match="Keystore path must be a file."):
        _keystore = Keystore(invalid_path)

    # Not an existing file
    invalid_path = Path('does-not-exist')
    with pytest.raises(Keystore.NotFound, match=f"Keystore '{invalid_path.absolute()}' does not exist."):
        _keystore = Keystore(invalid_path)


def test_keystore_instantiation_defaults(tmp_path_factory):

    # Setup
    parent = Path(tmp_path_factory.mktemp('test-keystore-'))
    parent.touch(exist_ok=True)
    keystore_id = ''.join(random.choice(string.hexdigits.lower()) for _ in range(Keystore._ID_SIZE))
    path = parent / f'123-{keystore_id}.priv'
    path.touch()

    # Test
    keystore = Keystore(path)
    assert keystore.keystore_path == path  # retains the correct keystore path
    assert keystore.id == keystore_id      # accurately parses filename for ID
    assert not keystore.is_unlocked        # defaults to locked
    assert keystore._Keystore__secret is KEYSTORE_LOCKED
    assert parent in keystore.keystore_path.parents  # created in the correct directory


def test_keystore_generation_defaults(tmp_path_factory, mnemonic):

    # Setup
    parent = Path(tmp_path_factory.mktemp('test-keystore-'))
    parent.touch(exist_ok=True)

    # Test
    keystore = Keystore.generate(
        phrase=mnemonic,
        keystore_password=INSECURE_DEVELOPMENT_PASSWORD,
        keystore_dir=parent,
    )
    assert not keystore.is_unlocked  # defaults to locked
    assert keystore._Keystore__secret is KEYSTORE_LOCKED
    assert parent in keystore.keystore_path.parents  # created in the correct directory


def test_keystore_invalid_password(tmpdir, mnemonic):
    with pytest.raises(InvalidPassword):
        _keystore = Keystore.generate(
            keystore_password="short", keystore_dir=tmpdir, phrase=mnemonic
        )


def test_keystore_generate_report_interactive_false(tmpdir, mnemonic):
    _keystore = Keystore.generate(
        keystore_password=INSECURE_DEVELOPMENT_PASSWORD,
        keystore_dir=tmpdir,
        phrase=mnemonic,
    )
    assert len(mnemonic.split(" ")) == 24


def test_keystore_derive_crypto_power_without_unlock(tmpdir, mnemonic):
    keystore = Keystore.generate(
        phrase=mnemonic,
        keystore_password=INSECURE_DEVELOPMENT_PASSWORD,
        keystore_dir=tmpdir,
    )
    with pytest.raises(Keystore.Locked):
        keystore.derive_crypto_power(power_class=DecryptingPower)


def test_keystore_serializer():
    encrypted_secret, psalt, wsalt = b'peanuts! Get your peanuts!', b'sea salt', b'bath salt'
    payload = _assemble_keystore(encrypted_secret=encrypted_secret, password_salt=psalt, wrapper_salt=wsalt)
    serialized_payload = _serialize_keystore(payload)
    deserialized_key_data = _deserialize_keystore(serialized_payload)
    assert deserialized_key_data['key'] == encrypted_secret
    assert deserialized_key_data['password_salt'] == psalt
    assert deserialized_key_data['wrapper_salt'] == wsalt


def test_keystore_lock_unlock(tmpdir, mnemonic):
    keystore = Keystore.generate(
        phrase=mnemonic,
        keystore_password=INSECURE_DEVELOPMENT_PASSWORD,
        keystore_dir=tmpdir,
    )

    # locked by default
    assert not keystore.is_unlocked
    assert keystore._Keystore__secret is KEYSTORE_LOCKED

    # incorrect password
    with pytest.raises(Keystore.AuthenticationFailed):
        keystore.unlock('opensaysme')

    # unlock
    keystore.unlock(INSECURE_DEVELOPMENT_PASSWORD)
    assert keystore.is_unlocked
    assert keystore._Keystore__secret != KEYSTORE_LOCKED
    assert isinstance(keystore._Keystore__secret, bytes)

    # unlock when already unlocked
    keystore.unlock(INSECURE_DEVELOPMENT_PASSWORD)
    assert keystore.is_unlocked

    # incorrect password when already unlocked
    with pytest.raises(Keystore.AuthenticationFailed):
        keystore.unlock('opensaysme')

    # lock
    keystore.lock()
    assert not keystore.is_unlocked

    # lock when already locked
    keystore.lock()
    assert not keystore.is_unlocked


def test_write_keystore_file(temp_dir_path):
    temp_filepath = Path(temp_dir_path) / "test_private_key_serialization_file"
    encrypted_secret, psalt, wsalt = b'peanuts! Get your peanuts!', b'sea salt', b'bath_salt'
    payload = _assemble_keystore(encrypted_secret=encrypted_secret, password_salt=psalt, wrapper_salt=wsalt)
    _write_keystore(path=temp_filepath, payload=payload, serializer=_serialize_keystore)
    deserialized_payload_from_file = _read_keystore(path=temp_filepath, deserializer=_deserialize_keystore)
    assert deserialized_payload_from_file['key'] == encrypted_secret
    assert deserialized_payload_from_file['password_salt'] == psalt
    assert deserialized_payload_from_file['wrapper_salt'] == wsalt


def test_decrypt_keystore(tmpdir, mocker):

    # Setup
    mnemonic = Mnemonic(_MNEMONIC_LANGUAGE)
    words = mnemonic.generate(strength=_ENTROPY_BITS)
    secret = bytes(mnemonic.to_entropy(words))

    spy = mocker.spy(Mnemonic, 'generate')

    # Decrypt post-generation
    keystore = Keystore.generate(
        phrase=words,
        keystore_password=INSECURE_DEVELOPMENT_PASSWORD,
        keystore_dir=tmpdir,
    )
    keystore.unlock(password=INSECURE_DEVELOPMENT_PASSWORD)
    assert spy.call_count == 0
    assert keystore._Keystore__secret == secret

    # Decrypt from keystore file
    keystore_path = keystore.keystore_path
    del words
    del keystore
    keystore = Keystore(keystore_path=keystore_path)
    keystore.unlock(INSECURE_DEVELOPMENT_PASSWORD)
    assert keystore._Keystore__secret == secret


def test_keystore_persistence(tmpdir, mnemonic):
    """Regression test for keystore file persistence"""
    keystore = Keystore.generate(
        phrase=mnemonic,
        keystore_password=INSECURE_DEVELOPMENT_PASSWORD,
        keystore_dir=tmpdir,
    )
    keystore.unlock(password=INSECURE_DEVELOPMENT_PASSWORD)
    path = keystore.keystore_path
    del keystore
    assert path.exists()


def test_restore_keystore_from_mnemonic(tmpdir, mocker):

    # Setup
    words = Mnemonic(_MNEMONIC_LANGUAGE).generate(strength=_ENTROPY_BITS)
    spy = mocker.spy(Mnemonic, 'generate')

    # Decrypt post-generation
    keystore = Keystore.generate(
        phrase=words,
        keystore_password=INSECURE_DEVELOPMENT_PASSWORD,
        keystore_dir=tmpdir,
    )
    keystore.unlock(password=INSECURE_DEVELOPMENT_PASSWORD)
    mnemonic = Mnemonic(_MNEMONIC_LANGUAGE)
    assert spy.call_count == 0
    secret = bytes(mnemonic.to_entropy(words))
    keystore_path = keystore.keystore_path

    # remove local and disk references, simulating a
    # lost keystore or forgotten password.
    del keystore
    os.unlink(keystore_path)

    # prove the keystore is lost or missing
    assert not keystore_path.exists()
    with pytest.raises(Keystore.NotFound):
        _keystore = Keystore(keystore_path=keystore_path)

    # Restore with user-supplied words and a new password
    keystore = Keystore.restore(words=words, password="ANewHope", keystore_dir=tmpdir)
    keystore.unlock(password="ANewHope")
    assert keystore._Keystore__secret == secret


def test_import_custom_keystore(tmpdir):
    # Too short - 32 bytes is required
    custom_secret = b"tooshort"
    with pytest.raises(
        ValueError,
        match=f"Entropy bytes bust be exactly {SecretKeyFactory.seed_size()}.",
    ):
        _keystore = Keystore.import_secure(
            key_material=custom_secret,
            password=INSECURE_DEVELOPMENT_PASSWORD,
            keystore_dir=tmpdir,
        )

    # Too short - 32 bytes is required
    custom_secret = b"thisisabunchofbytesthatisabittoolong"
    with pytest.raises(
        ValueError,
        match=f"Entropy bytes bust be exactly {SecretKeyFactory.seed_size()}.",
    ):
        _keystore = Keystore.import_secure(
            key_material=custom_secret,
            password=INSECURE_DEVELOPMENT_PASSWORD,
            keystore_dir=tmpdir,
        )

    # Import private key
    custom_secret = os.urandom(SecretKeyFactory.seed_size())  # insecure but works
    keystore = Keystore.import_secure(
        key_material=custom_secret,
        password=INSECURE_DEVELOPMENT_PASSWORD,
        keystore_dir=tmpdir,
    )
    keystore.unlock(password=INSECURE_DEVELOPMENT_PASSWORD)
    assert keystore._Keystore__secret == custom_secret
    keystore.lock()

    path = keystore.keystore_path
    del keystore

    # Restore custom secret from encrypted keystore file
    keystore = Keystore(keystore_path=path)
    keystore.unlock(password=INSECURE_DEVELOPMENT_PASSWORD)
    assert keystore._Keystore__secret == custom_secret


def test_derive_signing_power(tmpdir, mnemonic):
    keystore = Keystore.generate(
        phrase=mnemonic,
        keystore_password=INSECURE_DEVELOPMENT_PASSWORD,
        keystore_dir=tmpdir,
    )
    keystore.unlock(password=INSECURE_DEVELOPMENT_PASSWORD)
    signing_power = keystore.derive_crypto_power(power_class=SigningPower)
    assert signing_power.public_key().to_compressed_bytes().hex()
    assert signing_power.keypair.fingerprint()


def test_derive_decrypting_power(tmpdir, mnemonic):
    keystore = Keystore.generate(
        phrase=mnemonic,
        keystore_password=INSECURE_DEVELOPMENT_PASSWORD,
        keystore_dir=tmpdir,
    )
    keystore.unlock(password=INSECURE_DEVELOPMENT_PASSWORD)
    decrypting_power = keystore.derive_crypto_power(power_class=DecryptingPower)
    assert decrypting_power.public_key().to_compressed_bytes().hex()
    assert decrypting_power.keypair.fingerprint()


def test_derive_delegating_power(tmpdir, mnemonic):
    keystore = Keystore.generate(
        phrase=mnemonic,
        keystore_password=INSECURE_DEVELOPMENT_PASSWORD,
        keystore_dir=tmpdir,
    )
    keystore.unlock(password=INSECURE_DEVELOPMENT_PASSWORD)
    delegating_power = keystore.derive_crypto_power(power_class=DelegatingPower)
    parent_skf = SecretKeyFactory.from_secure_randomness(keystore._Keystore__secret)
    child_skf = parent_skf.make_factory(_DELEGATING_INFO)
    ref_pk = child_skf.make_key(b"some-label").public_key()
    assert (
        delegating_power._get_privkey_from_label(label=b"some-label").public_key()
        == ref_pk
    )


def test_derive_hosting_power(tmpdir, mnemonic):
    keystore = Keystore.generate(
        phrase=mnemonic,
        keystore_password=INSECURE_DEVELOPMENT_PASSWORD,
        keystore_dir=tmpdir,
    )
    keystore.unlock(password=INSECURE_DEVELOPMENT_PASSWORD)
    hosting_power = keystore.derive_crypto_power(power_class=TLSHostingPower, host=LOOPBACK_ADDRESS)
    assert hosting_power.public_key().public_numbers()
    assert hosting_power.keypair.certificate.public_bytes(encoding=Encoding.PEM)
    rederived_hosting_power = keystore.derive_crypto_power(power_class=TLSHostingPower, host=LOOPBACK_ADDRESS)
    assert hosting_power.public_key().public_numbers() == rederived_hosting_power.public_key().public_numbers()


def test_derive_threshold_request_decrypting_power(tmpdir, mnemonic):
    keystore = Keystore.generate(
        phrase=mnemonic,
        keystore_password=INSECURE_DEVELOPMENT_PASSWORD,
        keystore_dir=tmpdir,
    )
    keystore.unlock(password=INSECURE_DEVELOPMENT_PASSWORD)
    threshold_request_decrypting_power = keystore.derive_crypto_power(
        power_class=ThresholdRequestDecryptingPower
    )

    ritual_id = 23
    public_key = threshold_request_decrypting_power.get_pubkey_from_ritual_id(
        ritual_id=ritual_id
    )
    other_public_key = threshold_request_decrypting_power.get_pubkey_from_ritual_id(
        ritual_id=ritual_id
    )
    assert bytes(public_key) == bytes(other_public_key)

    different_ritual_public_key = (
        threshold_request_decrypting_power.get_pubkey_from_ritual_id(ritual_id=0)
    )
    assert bytes(public_key) != bytes(different_ritual_public_key)


def test_keystore_wallet_generation(tmpdir, mock_write_wallet_to_file):
    _keystore, _words = Keystore.generate(
        INSECURE_DEVELOPMENT_PASSWORD, keystore_dir=tmpdir, interactive=False
    )
    assert mock_write_wallet_to_file.called
