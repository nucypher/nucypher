import sha3
from constant_sorrow.constants import PUBLIC_ONLY
from nucypher_core.umbral import SecretKey

from nucypher.crypto import keypairs


def test_gen_keypair_if_needed():
    new_dec_keypair = keypairs.DecryptingKeypair()
    assert new_dec_keypair._privkey is not None
    assert new_dec_keypair.pubkey is not None
    assert new_dec_keypair.pubkey == new_dec_keypair._privkey.public_key()

    new_sig_keypair = keypairs.SigningKeypair()
    assert new_sig_keypair._privkey is not None
    assert new_sig_keypair.pubkey is not None
    assert new_sig_keypair.pubkey == new_sig_keypair._privkey.public_key()


def test_keypair_with_umbral_keys():
    umbral_privkey = SecretKey.random()
    umbral_pubkey = umbral_privkey.public_key()

    new_keypair_from_priv = keypairs.Keypair(umbral_privkey)
    assert new_keypair_from_priv._privkey == umbral_privkey
    assert (
        new_keypair_from_priv.pubkey.to_compressed_bytes()
        == umbral_pubkey.to_compressed_bytes()
    )

    new_keypair_from_pub = keypairs.Keypair(public_key=umbral_pubkey)
    assert (
        new_keypair_from_pub.pubkey.to_compressed_bytes()
        == umbral_pubkey.to_compressed_bytes()
    )
    assert new_keypair_from_pub._privkey == PUBLIC_ONLY


def test_keypair_serialization():
    umbral_pubkey = SecretKey.random().public_key()
    new_keypair = keypairs.Keypair(public_key=umbral_pubkey)

    pubkey_bytes = new_keypair.pubkey.to_compressed_bytes()
    assert pubkey_bytes == umbral_pubkey.to_compressed_bytes()


def test_keypair_fingerprint():
    umbral_pubkey = SecretKey.random().public_key()
    new_keypair = keypairs.Keypair(public_key=umbral_pubkey)

    fingerprint = new_keypair.fingerprint()
    assert fingerprint is not None

    umbral_fingerprint = (
        sha3.keccak_256(umbral_pubkey.to_compressed_bytes()).hexdigest().encode()
    )
    assert fingerprint == umbral_fingerprint


def test_signing():
    umbral_privkey = SecretKey.random()
    sig_keypair = keypairs.SigningKeypair(umbral_privkey)

    msg = b'peace at dawn'
    signature = sig_keypair.sign(msg)
    assert signature.verify(sig_keypair.pubkey, msg)

    bad_msg = b'bad message'
    assert not signature.verify(sig_keypair.pubkey, bad_msg)


# TODO: Add test for DecryptingKeypair.decrypt
