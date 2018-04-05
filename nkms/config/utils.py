import os

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from nacl.secret import SecretBox
from umbral.keys import UmbralPrivateKey

from nkms.config.config import KMSConfig


def validate_passphrase(passphrase) -> str:
    """Validate a passphrase and return it or raise"""

    rules = (
        (len(passphrase) >= 16, 'Too short'),
    )

    for rule, failure_message in rules:
        if not rule:
            raise KMSConfig.KMSConfigurationError(failure_message)
    else:
        return passphrase


def _derive_master_key_from_passphrase(salt: bytes, passphrase: str) -> bytes:
    """
    Uses Scrypt derivation to derive a master key for encrypting key material.
    See RFC 7914 for n, r, and p value selections.
    This takes around ~5 seconds to perform.
    """
    master_key = Scrypt(
        salt=salt,
        length=32,
        n=2**20,
        r=8,
        p=1,
        backend=default_backend()
    ).derive(passphrase.encode())

    return master_key


def _derive_wrapping_key_from_master_key(salt: bytes, master_key: bytes) -> bytes:
    """
    Uses HKDF to derive a 32 byte wrapping key to encrypt key material with.
    """
    wrapping_key = HKDF(
        algorithm=hashes.SHA512(),
        length=32,
        salt=salt,
        info=b'NuCypher-KMS-KeyWrap',
        backend=default_backend()
    ).derive(master_key)

    return wrapping_key


def _encrypt_key(wrapping_key: bytes, key_material: bytes) -> dict:
    """
    Encrypts a key with nacl's XSalsa20-Poly1305 algorithm (SecretBox).
    Returns an encrypted key as bytes with the nonce appended.
    """
    nonce = os.urandom(24)
    enc_key = SecretBox(wrapping_key).encrypt(key_material, nonce)

    crypto_data = {
        'nonce': nonce,
        'enc_key': enc_key
    }

    return crypto_data


# TODO: Handle decryption failures
def _decrypt_key(wrapping_key: bytes, nonce: bytes, enc_key_material: bytes) -> bytes:
    """
    Decrypts an encrypted key with nacl's XSalsa20-Poly1305 algorithm (SecretBox).
    Returns a decrypted key as bytes.
    """
    dec_key = SecretBox(wrapping_key).encrypt(enc_key_material, nonce)

    return dec_key


def _generate_encryption_keys() -> tuple:
    """Use pyUmbral keys to generate a new encrypting key pair"""

    privkey = UmbralPrivateKey.gen_key()
    pubkey = privkey.get_pubkey()

    return privkey, pubkey


# TODO: Do we really want to use Umbral keys for signing?
# TODO: Perhaps we can use Curve25519/EdDSA for signatures?
def _generate_signing_keys() -> tuple:
    privkey = UmbralPrivateKey.gen_key()
    pubkey = privkey.get_pubkey()

    return privkey, pubkey


