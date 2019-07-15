import pytest

from umbral.keys import UmbralPrivateKey
from umbral.signing import Signer

from nucypher.config.keyring import NucypherKeyring
from nucypher.crypto.powers import DelegatingPower, DecryptingPower
from nucypher.utilities.sandbox.constants import INSECURE_DEVELOPMENT_PASSWORD
from constant_sorrow.constants import FEDERATED_ADDRESS


def test_generate_alice_keyring(tmpdir):

    keyring = NucypherKeyring.generate(
        checksum_address=FEDERATED_ADDRESS,
        password=INSECURE_DEVELOPMENT_PASSWORD,
        encrypting=True,
        rest=False,
        keyring_root=tmpdir
    )

    enc_pubkey = keyring.encrypting_public_key
    assert enc_pubkey is not None

    with pytest.raises(NucypherKeyring.KeyringLocked):
        _dec_keypair = keyring.derive_crypto_power(DecryptingPower).keypair

    keyring.unlock(password=INSECURE_DEVELOPMENT_PASSWORD)
    dec_keypair = keyring.derive_crypto_power(DecryptingPower).keypair

    assert enc_pubkey == dec_keypair.pubkey

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
