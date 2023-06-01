from pathlib import Path
from typing import Optional, Union

from constant_sorrow import constants
from cryptography.hazmat.primitives.asymmetric import ec
from hendrix.deploy.tls import HendrixDeployTLS
from hendrix.facilities.services import ExistingKeyTLSContextFactory
from nucypher_core import (
    HRAC,
    EncryptedKeyFrag,
    EncryptedTreasureMap,
    MessageKit,
    TreasureMap,
)
from nucypher_core.ferveo import Keypair as FerveoKeypair
from nucypher_core.umbral import (
    PublicKey,
    SecretKey,
    Signature,
    Signer,
    VerifiedKeyFrag,
)
from OpenSSL.crypto import X509
from OpenSSL.SSL import TLSv1_2_METHOD

from nucypher.config.constants import MAX_UPLOAD_CONTENT_LENGTH
from nucypher.crypto.signing import SignatureStamp, StrangerStamp
from nucypher.crypto.tls import (
    _TLS_CURVE,
    _read_tls_certificate,
    generate_self_signed_certificate,
)
from nucypher.crypto.utils import keccak_digest
from nucypher.network.resources import get_static_resources


class Keypair(object):
    """
    A parent Keypair class for all types of Keypairs.
    """

    _private_key_source = SecretKey.random
    _public_key_method = "public_key"

    def __init__(self,
                 private_key=None,
                 public_key=None,
                 generate_keys_if_needed=True) -> None:
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

    def fingerprint(self):
        """
        Hashes the key using keccak-256 and returns the hexdigest in bytes.

        :return: Hexdigest fingerprint of key (keccak-256) in bytes
        """
        return keccak_digest(self.pubkey.to_compressed_bytes()).hex().encode()


class DecryptingKeypair(Keypair):
    """
    A keypair for Umbral
    """

    class DecryptionFailed(Exception):
        """Raised when decryption fails."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

    def decrypt_message_kit(self, message_kit: MessageKit) -> bytes:
        """
        Decrypt data encrypted with Umbral.

        :return: bytes
        """
        try:
            return message_kit.decrypt(self._privkey)
        except ValueError as e:
            raise self.DecryptionFailed() from e

    def decrypt_kfrag(self, ekfrag: EncryptedKeyFrag, hrac: HRAC, publisher_verifying_key: PublicKey) -> VerifiedKeyFrag:
        return ekfrag.decrypt(self._privkey, hrac, publisher_verifying_key)

    def decrypt_treasure_map(self, etmap: EncryptedTreasureMap, publisher_verifying_key: PublicKey) -> TreasureMap:
        return etmap.decrypt(self._privkey, publisher_verifying_key)


class RitualisticKeypair(Keypair):
    """A keypair for Ferveo DKG"""

    _private_key_source = FerveoKeypair.random
    _public_key_method = "public_key"

    @classmethod
    def from_secure_randomness(cls, randomness: bytes) -> 'RitualisticKeypair':
        """Create a keypair from a precomputed secure source of randomness"""
        size = FerveoKeypair.secure_randomness_size()
        if len(randomness) != size:
            raise ValueError(f"precomputed randomness must be {size} bytes long")
        keypair = FerveoKeypair.from_secure_randomness(randomness)
        return cls(private_key=keypair)


class SigningKeypair(Keypair):
    """
    A SigningKeypair that uses ECDSA.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

    def sign(self, message: bytes) -> Signature:
        """
        Signs the given message and returns a signature.

        :param message: The message to sign

        :return: Signature
        """
        return Signer(self._privkey).sign(message)

    def get_signature_stamp(self):
        if self._privkey is constants.PUBLIC_ONLY:
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

    def __init__(self,
                 host: str,
                 checksum_address: str = None,
                 private_key: Union[SecretKey, PublicKey] = None,
                 certificate=None,
                 certificate_filepath: Optional[Path] = None,
                 generate_certificate=False,
                 ) -> None:

        if private_key:
            if certificate_filepath:
                certificate = _read_tls_certificate(filepath=certificate_filepath)
            super().__init__(private_key=private_key)

        elif certificate:
            super().__init__(public_key=certificate.public_key())

        elif certificate_filepath:
            certificate = _read_tls_certificate(filepath=certificate_filepath)
            super().__init__(public_key=certificate.public_key())

        elif generate_certificate:
            if not host and checksum_address:
                message = "If you don't supply a TLS certificate, one will be generated for you." \
                          "But for that, you need to pass a host and checksum address."
                raise TypeError(message)
            certificate, private_key = generate_self_signed_certificate(host=host)
            super().__init__(private_key=private_key)

        else:
            raise TypeError("You didn't provide a cert, but also told us not to generate keys.  Not sure what to do.")

        if not certificate_filepath:
            certificate_filepath = constants.CERTIFICATE_NOT_SAVED

        self.certificate = certificate
        self.certificate_filepath = certificate_filepath

    def get_deployer(self, rest_app, port):
        return HendrixDeployTLS("start",
                                key=self._privkey,
                                cert=X509.from_cryptography(self.certificate),
                                context_factory=ExistingKeyTLSContextFactory,
                                context_factory_kwargs={"curve_name": _TLS_CURVE.name, "sslmethod": TLSv1_2_METHOD},
                                options={
                                    "wsgi": rest_app,
                                    "https_port": port,
                                    "max_upload_bytes": MAX_UPLOAD_CONTENT_LENGTH,
                                    'resources': get_static_resources(),
                                })
