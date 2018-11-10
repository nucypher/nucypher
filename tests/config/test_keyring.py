import pytest

from umbral.keys import UmbralPrivateKey
from umbral.signing import Signer

from nucypher.config.keyring import NucypherKeyring
from nucypher.crypto.powers import DelegatingPower, EncryptingPower


@pytest.mark.skip("Redacted and refactored for sensitive info leakage")
def test_validate_passphrase():
    # Passphrase too short
    passphrase = 'x' * 5
    with pytest.raises(ValueError):
        _keyring = NucypherKeyring.generate(passphrase=passphrase)

    # Empty passphrase is provided
    with pytest.raises(ValueError):
        _keyring = NucypherKeyring.generate(passphrase="")


def test_generate_alice_keyring(tmpdir):
    passphrase = 'x' * 16

    keyring = NucypherKeyring.generate(
        passphrase=passphrase,
        encrypting=True,
        wallet=False,
        tls=False,
        keyring_root=tmpdir
    )

    enc_pubkey = keyring.encrypting_public_key
    assert enc_pubkey is not None

    with pytest.raises(NucypherKeyring.KeyringLocked):
        _enc_keypair = keyring.derive_crypto_power(EncryptingPower).keypair

    keyring.unlock(passphrase)
    enc_keypair = keyring.derive_crypto_power(EncryptingPower).keypair

    assert enc_pubkey == enc_keypair.pubkey

    label = b'test'

    delegating_power = keyring.derive_crypto_power(DelegatingPower)
    delegating_pubkey = delegating_power.get_pubkey_from_label(label)

    bob_pubkey = UmbralPrivateKey.gen_key().get_pubkey()
    signer = Signer(UmbralPrivateKey.gen_key())
    delegating_pubkey_again, _kfrags = delegating_power.generate_kfrags(
        bob_pubkey, signer, label, m=2, n=3
    )

    assert delegating_pubkey == delegating_pubkey_again

    another_delegating_power = keyring.derive_crypto_power(DelegatingPower)
    another_delegating_pubkey = another_delegating_power.get_pubkey_from_label(label)

    assert delegating_pubkey == another_delegating_pubkey