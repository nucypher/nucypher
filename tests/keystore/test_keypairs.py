import sha3
from constant_sorrow.constants import PUBLIC_ONLY
from umbral.keys import UmbralPrivateKey

from nucypher.keystore import keypairs


def test_gen_keypair_if_needed():
    new_enc_keypair = keypairs.EncryptingKeypair()
    assert new_enc_keypair._privkey != None
    assert new_enc_keypair.pubkey != None

    new_sig_keypair = keypairs.SigningKeypair()
    assert new_sig_keypair._privkey != None
    assert new_sig_keypair.pubkey != None


def test_keypair_with_umbral_keys():
    umbral_privkey = UmbralPrivateKey.gen_key()
    umbral_pubkey = umbral_privkey.get_pubkey()

    new_keypair_from_priv = keypairs.Keypair(umbral_privkey)
    assert new_keypair_from_priv._privkey.bn_key.to_bytes() == umbral_privkey.bn_key.to_bytes()
    assert new_keypair_from_priv.pubkey.to_bytes() == umbral_pubkey.to_bytes()

    new_keypair_from_pub = keypairs.Keypair(public_key=umbral_pubkey)
    assert new_keypair_from_pub.pubkey.to_bytes() == umbral_pubkey.to_bytes()
    assert new_keypair_from_pub._privkey == PUBLIC_ONLY


def test_keypair_serialization():
    umbral_pubkey = UmbralPrivateKey.gen_key().get_pubkey()
    new_keypair = keypairs.Keypair(public_key=umbral_pubkey)

    pubkey_bytes = new_keypair.serialize_pubkey()
    assert pubkey_bytes == bytes(umbral_pubkey)

    pubkey_b64 = new_keypair.serialize_pubkey(as_b64=True)
    assert pubkey_b64 == umbral_pubkey.to_bytes()


def test_keypair_fingerprint():
    umbral_pubkey = UmbralPrivateKey.gen_key().get_pubkey()
    new_keypair = keypairs.Keypair(public_key=umbral_pubkey)

    fingerprint = new_keypair.fingerprint()
    assert fingerprint != None

    umbral_fingerprint = sha3.keccak_256(bytes(umbral_pubkey)).hexdigest().encode()
    assert fingerprint == umbral_fingerprint


def test_signing():
    umbral_privkey = UmbralPrivateKey.gen_key()
    sig_keypair = keypairs.SigningKeypair(umbral_privkey)

    msg = b'attack at dawn'
    signature = sig_keypair.sign(msg)
    assert signature.verify(msg, sig_keypair.pubkey) == True

    bad_msg = b'bad message'
    assert signature.verify(bad_msg, sig_keypair.pubkey) == False


# TODO: Add test for EncryptingKeypair.decrypt
