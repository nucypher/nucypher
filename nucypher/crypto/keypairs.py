"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""
from pathlib import Path
from typing import Optional, Union

import sha3
from OpenSSL.SSL import TLSv1_2_METHOD
from OpenSSL.crypto import X509
from constant_sorrow import constants
from cryptography.hazmat.primitives.asymmetric import ec
from hendrix.deploy.tls import HendrixDeployTLS
from hendrix.facilities.services import ExistingKeyTLSContextFactory

from nucypher.core import MessageKit, EncryptedTreasureMap, EncryptedKeyFrag

from nucypher.config.constants import MAX_UPLOAD_CONTENT_LENGTH
from nucypher.crypto.signing import SignatureStamp, StrangerStamp
from nucypher.crypto.tls import _read_tls_certificate, _TLS_CURVE, generate_self_signed_certificate
from nucypher.crypto.umbral_adapter import (
    SecretKey,
    PublicKey,
    Signature,
    Signer,
)
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
        return sha3.keccak_256(bytes(self.pubkey)).hexdigest().encode()


class DecryptingKeypair(Keypair):
    """
    A keypair for Umbral
    """

    class DecryptionFailed(Exception):
        """Raised when decryption fails."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

    def decrypt(self, message_kit: Union[MessageKit, EncryptedKeyFrag, EncryptedTreasureMap]) -> bytes:
        """
        Decrypt data encrypted with Umbral.

        :return: bytes
        """
        try:
            return message_kit.decrypt(self._privkey)
        except ValueError as e:
            raise self.DecryptionFailed() from e


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
            certificate, private_key = generate_self_signed_certificate(host=host, private_key=private_key)
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
