import json
import os
from base64 import urlsafe_b64encode

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from nacl.secret import SecretBox
from umbral.keys import UmbralPrivateKey


#from eth_account import Account

#from web3.auto import w3
#w3.eth.enable_unaudited_features()
#w3.eth.account


class KMSConfigurationError(RuntimeError):
    pass


def validate_passphrase(passphrase) -> str:
    """Validate a passphrase and return it or raise"""

    rules = (
        (len(passphrase) >= 16, 'Passphrase is too short, must be >= 16 chars.'),
    )

    for rule, failure_message in rules:
        if not rule:
            raise KMSConfigurationError(failure_message)
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


def _encrypt_umbral_key(wrapping_key: bytes, umbral_key: UmbralPrivateKey) -> dict:
    """
    Encrypts a key with nacl's XSalsa20-Poly1305 algorithm (SecretBox).
    Returns an encrypted key as bytes with the nonce appended.
    """
    nonce = os.urandom(24)
    enc_key = SecretBox(wrapping_key).encrypt(umbral_key.to_bytes(), nonce)

    crypto_data = {
        'nonce': urlsafe_b64encode(nonce).decode(),
        'enc_key': urlsafe_b64encode(enc_key).decode()
    }

    return crypto_data


# TODO: Handle decryption failures
def _decrypt_key(wrapping_key: bytes, nonce: bytes, enc_key_material: bytes) -> UmbralPrivateKey:
    """
    Decrypts an encrypted key with nacl's XSalsa20-Poly1305 algorithm (SecretBox).
    Returns a decrypted key as an UmbralPrivateKey.
    """
    dec_key = SecretBox(wrapping_key).encrypt(enc_key_material, nonce)
    umbral_key = UmbralPrivateKey.from_bytes(dec_key)

    return umbral_key


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


def _parse_keyfile(keypath: str):
    """Parses a keyfile and returns key metadata as a dict."""
    from nkms.config.config import KMSConfig
    with open(keypath, 'r') as keyfile:
        try:
            key_metadata = json.loads(keyfile)
        except json.JSONDecodeError:
            raise KMSConfigurationError("Invalid data in keyfile {}".format(keypath))
        else:
            return key_metadata


def _save_keyfile(keypath: str, key_data: dict) -> None:
    """Saves key data to a file"""
    from nkms.config.config import KMSConfig
    with open(keypath, 'w+') as keyfile:

        # Check_if the file is empty
        keyfile.seek(0)
        check_byte = keyfile.read(1)

        if len(check_byte) != 0:
            message = "{} is not empty. Check your key path.".format(keypath)
            raise KMSConfigurationError(message)

        # Write the keydata to the file
        keyfile.seek(0)
        keyfile.write(json.dumps(key_data))


def _bootstrap_config():
    """
    """
    enc_key, _ = _generate_encryption_keys()
    sig_key, _ = _generate_signing_keys()

    der_master_key = _derive_master_key_from_passphrase(b'test', 'test')
    der_wrap_key = _derive_wrapping_key_from_master_key(b'test', der_master_key)

    enc_json = _encrypt_umbral_key(der_wrap_key, enc_key)
    sig_json = _encrypt_umbral_key(der_wrap_key, sig_key)

    enc_json['master_salt'] = urlsafe_b64encode(b'test').decode()
    sig_json['master_salt'] = urlsafe_b64encode(b'test').decode()

    enc_json['wrap_salt'] = urlsafe_b64encode(b'test').decode()
    sig_json['wrap_salt'] = urlsafe_b64encode(b'test').decode()

    _save_keyfile('root_key.priv', enc_json)
    _save_keyfile('signing_key.priv', sig_json)


#def create_eth_wallet(passphrase: str) -> dict:
#    """Create a new wallet address from the provided passphrase"""
#
#    entropy = os.urandom(32)   # max out entropy for keccak256
#    account = Account.create(extra_entropy=entropy)
#    encrypted_wallet_data = Account.encrypt(private_key=account.privateKey, password=passphrase)
#
#    return encrypted_wallet_data
