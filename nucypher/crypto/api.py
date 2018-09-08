import os

import datetime
from random import SystemRandom

from cryptography.hazmat.primitives.serialization import Encoding
from cryptography.x509 import Certificate
from typing import Union

import sha3
from constant_sorrow import constants
from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from nucypher.config.constants import DEFAULT_TLS_CERTIFICATE_FILEPATH, DEFAULT_KNOWN_CERTIFICATES_DIR
from nucypher.config.utils import NucypherConfigurationError
from umbral import pre
from umbral.keys import UmbralPrivateKey, UmbralPublicKey

from nucypher.crypto.constants import BLAKE2B
from nucypher.crypto.kits import UmbralMessageKit

SYSTEM_RAND = SystemRandom()


def secure_random(num_bytes: int) -> bytes:
    """
    Returns an amount `num_bytes` of data from the OS's random device.
    If a randomness source isn't found, returns a `NotImplementedError`.
    In this case, a secure random source most likely doesn't exist and
    randomness will have to found elsewhere.

    :param num_bytes: Number of bytes to return.

    :return: bytes
    """
    # TODO: Should we just use os.urandom or avoid the import w/ this?
    return SYSTEM_RAND.getrandbits(num_bytes * 8).to_bytes(num_bytes, byteorder='big')


def secure_random_range(min: int, max: int) -> int:
    """
    Returns a number from a secure random source betwee the range of
    `min` and `max` - 1.

    :param min: Minimum number in the range
    :param max: Maximum number in the range

    :return: int
    """
    return SYSTEM_RAND.randrange(min, max)


def keccak_digest(*messages: bytes) -> bytes:
    """
    Accepts an iterable containing bytes and digests it returning a
    Keccak digest of 32 bytes (keccak_256).

    Although we use BLAKE2b in many cases, we keep keccak handy in order
    to provide compatibility with the Ethereum blockchain.

    :param bytes *messages: Data to hash

    :rtype: bytes
    :return: bytestring of digested data
    """
    hash = sha3.keccak_256()
    for message in messages:
        hash.update(message)
    return hash.digest()


def ecdsa_sign(message: bytes, privkey: UmbralPrivateKey) -> bytes:
    """
    Accepts a hashed message and signs it with the private key given.

    :param message: Message to hash and sign
    :param privkey: Private key to sign with

    :return: signature
    """
    cryptography_priv_key = privkey.to_cryptography_privkey()
    signature_der_bytes = cryptography_priv_key.sign(message, ec.ECDSA(BLAKE2B))
    return signature_der_bytes


def ecdsa_verify(
        message: bytes,
        signature: bytes,
        pubkey: UmbralPublicKey
) -> bool:
    """
    Accepts a message and signature and verifies it with the
    provided public key.

    :param message: Message to verify
    :param signature: Signature to verify
    :param pubkey: UmbralPublicKey to verify signature with

    :return: True if valid, False if invalid.
    """
    cryptography_pub_key = pubkey.to_cryptography_pubkey()

    try:
        cryptography_pub_key.verify(
            signature,
            message,
            ec.ECDSA(BLAKE2B)
        )
    except InvalidSignature:
        return False
    return True


def _save_tls_certificate(certificate: Certificate,
                          common_name: str = None,
                          is_me: bool = False,
                          force: bool = True,
                          certificate_dir: str = DEFAULT_KNOWN_CERTIFICATES_DIR) -> str:

    if is_me is False and not common_name:
        raise NucypherConfigurationError('A common name must be passed to save another node\'s certificate.')

    if is_me is True:
        certificate_filepath = DEFAULT_TLS_CERTIFICATE_FILEPATH
    else:
        certificate_filepath = os.path.join(certificate_dir, '{}.pem'.format(common_name[:6]))

    if force is False and os.path.isfile(certificate_filepath):
        raise NucypherConfigurationError('A TLS certificate already exists at {}.'.format(certificate_filepath))

    with open(certificate_filepath, 'wb') as certificate_file:
        public_pem_bytes = certificate.public_bytes(Encoding.PEM)
        certificate_file.write(public_pem_bytes)

    return certificate_filepath


def load_tls_certificate(filepath):
    with open(filepath, 'r') as certificate_file:
        cert = x509.load_pem_x509_certificate(certificate_file.read(),
                                              backend=default_backend())
        return cert


def generate_self_signed_certificate(common_name,
                                     curve,
                                     host,
                                     private_key=None,
                                     days_valid=365,
                                     save_to_disk=True):

    if not private_key:
        private_key = ec.generate_private_key(curve, default_backend())

    public_key = private_key.public_key()

    now = datetime.datetime.utcnow()
    subject = issuer = x509.Name([
             x509.NameAttribute(NameOID.COMMON_NAME, common_name),
        ])
    cert = x509.CertificateBuilder().subject_name(subject)
    cert = cert.issuer_name(issuer)
    cert = cert.public_key(public_key)
    cert = cert.serial_number(x509.random_serial_number())
    cert = cert.not_valid_before(now)
    cert = cert.not_valid_after(now + datetime.timedelta(days=days_valid))
    # TODO: What are we going to do about domain name here? 179
    cert = cert.add_extension(x509.SubjectAlternativeName([x509.DNSName(host)]), critical=False)
    cert = cert.sign(private_key, hashes.SHA512(), default_backend())

    if save_to_disk is True:
        tls_certificate_filepath = _save_tls_certificate(cert, common_name)
    else:
        tls_certificate_filepath = constants.CERTIFICATE_NOT_SAVED

    return cert, private_key, tls_certificate_filepath


def encrypt_and_sign(recipient_pubkey_enc: UmbralPublicKey,
                    plaintext: bytes,
                    signer: Union["SignatureStamp", "_Constant"],
                    sign_plaintext=True,
                    ) -> tuple:

    if signer is not constants.DO_NOT_SIGN:
        # The caller didn't expressly tell us not to sign; we'll sign.
        if sign_plaintext:
            # Sign first, encrypt second.
            sig_header = constants.SIGNATURE_TO_FOLLOW
            signature = signer(plaintext)
            ciphertext, capsule = pre.encrypt(recipient_pubkey_enc, sig_header + signature + plaintext)
        else:
            # Encrypt first, sign second.
            sig_header = constants.SIGNATURE_IS_ON_CIPHERTEXT
            ciphertext, capsule = pre.encrypt(recipient_pubkey_enc, sig_header + plaintext)
            signature = signer(ciphertext)
        message_kit = UmbralMessageKit(ciphertext=ciphertext, capsule=capsule,
                                       sender_pubkey_sig=signer.as_umbral_pubkey(),
                                       signature=signature)
    else:
        # Don't sign.
        signature = sig_header = constants.NOT_SIGNED
        alice_pubkey = None
        ciphertext, capsule = pre.encrypt(recipient_pubkey_enc, sig_header + plaintext)
        message_kit = UmbralMessageKit(ciphertext=ciphertext, capsule=capsule)

    return message_kit, signature
