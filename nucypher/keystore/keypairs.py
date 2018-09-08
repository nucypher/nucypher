from typing import Union

import sha3
from OpenSSL.SSL import TLSv1_2_METHOD
from OpenSSL.crypto import X509
from constant_sorrow import constants
from cryptography.hazmat.primitives.asymmetric import ec
from hendrix.deploy.tls import HendrixDeployTLS
from hendrix.facilities.services import ExistingKeyTLSContextFactory
from umbral import pre
from umbral.config import default_curve
from umbral.keys import UmbralPrivateKey, UmbralPublicKey
from umbral.signing import Signature, Signer

from nucypher.crypto import api as API
from nucypher.crypto.api import generate_self_signed_certificate, _save_tls_certificate
from nucypher.crypto.kits import MessageKit
from nucypher.crypto.signing import SignatureStamp, StrangerStamp


class Keypair(object):
    """
    A parent Keypair class for all types of Keypairs.
    """

    _private_key_source = UmbralPrivateKey.gen_key
    _public_key_method = "get_pubkey"

    def __init__(self,
                 private_key=None,
                 public_key=None,
                 generate_keys_if_needed=True):
        """
        Initalizes a Keypair object with an Umbral key object.
        :param generate_keys_if_needed: Generate keys or not?
        """
        if private_key and public_key:
            raise ValueError("Pass either private_key or public_key - not both.")
        elif private_key:
            self.pubkey = getattr(private_key, self._public_key_method)()
            self._privkey = private_key
        elif public_key:
            self.pubkey = public_key
            self._privkey = constants.PUBLIC_ONLY
        elif generate_keys_if_needed:
            self._privkey = self._private_key_source()
            self.pubkey = getattr(self._privkey, self._public_key_method)()
        else:
            raise ValueError(
                "Either pass a valid key or, if you want to generate keys, set generate_keys_if_needed to True.")

    def serialize_pubkey(self, as_b64=False) -> bytes:
        """
        Serializes the pubkey for storage/transport in either urlsafe base64
        or as a bytestring.

        :param as_bytes: Return the pubkey as bytes?
        :return: The serialized pubkey in bytes
        """
        if as_b64:
            return self.pubkey.to_bytes()
        return bytes(self.pubkey)

    def fingerprint(self):
        """
        Hashes the key using keccak-256 and returns the hexdigest in bytes.

        :return: Hexdigest fingerprint of key (keccak-256) in bytes
        """
        return sha3.keccak_256(bytes(self.pubkey)).hexdigest().encode()


class EncryptingKeypair(Keypair):
    """
    A keypair for Umbral
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def decrypt(self, message_kit: MessageKit, verifying_key: UmbralPublicKey = None) -> bytes:
        """
        Decrypt data encrypted with Umbral.

        :return: bytes
        """
        cleartext = pre.decrypt(ciphertext=message_kit.ciphertext,
                                capsule=message_kit.capsule,
                                decrypting_key=self._privkey,
                                )

        return cleartext


class SigningKeypair(Keypair):
    """
    A SigningKeypair that uses ECDSA.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def sign(self, message: bytes) -> bytes:
        """
        Signs a hashed message and returns a signature.

        :param message: The message to sign

        :return: Signature in bytes
        """
        signature_der_bytes = API.ecdsa_sign(message, self._privkey)
        return Signature.from_bytes(signature_der_bytes, der_encoded=True)

    def get_signature_stamp(self):
        if self._privkey == constants.PUBLIC_ONLY:
            return StrangerStamp(verifying_key=self.pubkey)
        else:
            signer = Signer(self._privkey)
            return SignatureStamp(verifying_key=self.pubkey, signer=signer)


class HostingKeypair(Keypair):
    """
    A keypair for TLS'ing.
    """
    _private_key_source = ec.generate_private_key
    _public_key_method = "public_key"

    _DEFAULT_CURVE = ec.SECP384R1

    def __init__(self,
                 common_name=None,
                 host=None,
                 private_key: Union[UmbralPrivateKey, UmbralPublicKey] = None,
                 certificate=None,
                 curve=None,
                 generate_keys_if_needed=True,
                 ):

        self.curve = curve or self._DEFAULT_CURVE

        if private_key:
            super().__init__(private_key=private_key)

        elif certificate:
            self.certificate_filepath = _save_tls_certificate(certificate,
                                                              common_name=common_name,
                                                              is_me=False,
                                                              force=False)
            self.certificate = certificate
            super().__init__(public_key=certificate.public_key())

        elif generate_keys_if_needed:
            if not all((common_name, host)):
                message = "If you don't supply the certificate, one will be generated for you." \
                          "But for that, you need to pass both host and common_name.."
                raise TypeError(message)
            self.certificate, private_key, self.tls_certificate_filepath = generate_self_signed_certificate(common_name=common_name,
                                                                                                            private_key=private_key,
                                                                                                            curve=self.curve,
                                                                                                            host=host)
            super().__init__(private_key=private_key)
        else:
            raise TypeError("You didn't provide a cert, but also told us not to generate keys.  Not sure what to do.")

    def generate_self_signed_cert(self, common_name):
        cryptography_key = self._privkey.to_cryptography_privkey()
        return generate_self_signed_certificate(common_name, default_curve(), cryptography_key)

    def get_deployer(self, rest_app, port):
        return HendrixDeployTLS("start",
                                key=self._privkey,
                                cert=X509.from_cryptography(self.certificate),
                                context_factory=ExistingKeyTLSContextFactory,
                                context_factory_kwargs={"curve_name": self.curve.name,
                                                        "sslmethod": TLSv1_2_METHOD},
                                options={"wsgi": rest_app, "https_port": port})
