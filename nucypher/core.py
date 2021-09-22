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

from typing import Optional, Sequence, Tuple, Dict

from bytestring_splitter import BytestringSplitter, VariableLengthBytestring

from nucypher.utilities.versioning import Versioned

from nucypher.crypto.utils import keccak_digest
from nucypher.crypto.splitters import signature_splitter, capsule_splitter, key_splitter, kfrag_splitter
from nucypher.crypto.signing import InvalidSignature
import nucypher.crypto.umbral_adapter as umbral # need it to mock `umbral.encrypt`
from nucypher.crypto.umbral_adapter import (
    SecretKey,
    PublicKey,
    Signer,
    Capsule,
    Signature,
    VerifiedCapsuleFrag,
    KeyFrag,
    VerifiedKeyFrag,
    VerificationError,
    decrypt_original,
    decrypt_reencrypted,
    )


class MessageKit(Versioned):
    """
    All the components needed to transmit and verify an encrypted message.
    """

    _SIGNATURE_TO_FOLLOW = b'\x00'
    _SIGNATURE_IS_ON_CIPHERTEXT = b'\x01'

    @classmethod
    def author(cls,
               recipient_key: PublicKey,
               plaintext: bytes,
               signer: Signer,
               sign_plaintext: bool = True
               ) -> 'MessageKit':

        # The caller didn't expressly tell us not to sign; we'll sign.
        if sign_plaintext:
            # Sign first, encrypt second.

            # TODO (#2743): may rethink it or remove completely
            sig_header = cls._SIGNATURE_TO_FOLLOW

            signature = signer.sign(plaintext)
            capsule, ciphertext = umbral.encrypt(recipient_key, sig_header + bytes(signature) + plaintext)
            signature_in_kit = None
        else:
            # Encrypt first, sign second.

            # TODO (#2743): may rethink it or remove completely
            sig_header = cls._SIGNATURE_IS_ON_CIPHERTEXT

            capsule, ciphertext = umbral.encrypt(recipient_key, sig_header + plaintext)
            signature = signer.sign(ciphertext)
            signature_in_kit = signature

        return cls(ciphertext=ciphertext,
                   capsule=capsule,
                   sender_verifying_key=signer.verifying_key(),
                   signature=signature_in_kit)

    def __init__(self,
                 capsule: Capsule,
                 ciphertext: bytes,
                 sender_verifying_key: PublicKey,
                 signature: Optional[Signature] = None,
                 ):
        self.ciphertext = ciphertext
        self.capsule = capsule
        self.sender_verifying_key = sender_verifying_key
        self.signature = signature

    def __eq__(self, other):
        return (self.ciphertext == other.ciphertext and
                self.capsule == other.capsule and
                self.sender_verifying_key == other.sender_verifying_key and
                self.signature == other.signature)

    def decrypt(self, sk: SecretKey) -> bytes:
        cleartext = decrypt_original(sk, self.capsule, self.ciphertext)
        return self._verify_cleartext(cleartext)

    def decrypt_reencrypted(self, sk: SecretKey, policy_key: PublicKey, cfrags: Sequence[VerifiedCapsuleFrag]) -> bytes:
        cleartext = decrypt_reencrypted(sk, policy_key, self.capsule, cfrags, self.ciphertext)
        return self._verify_cleartext(cleartext)

    def _verify_cleartext(self, cleartext_with_sig_header: bytes) -> bytes:

        sig_header = cleartext_with_sig_header[0:1]
        cleartext = cleartext_with_sig_header[1:]

        if sig_header == self._SIGNATURE_IS_ON_CIPHERTEXT:
            # The ciphertext is what is signed - note that for later.
            if not self.signature:
                raise ValueError("Cipherext is supposed to be signed, but the signature is missing.")
            message = self.ciphertext
            signature = self.signature

        elif sig_header == self._SIGNATURE_TO_FOLLOW:
            # The signature follows in this cleartext - split it off.
            signature, cleartext = signature_splitter(cleartext, return_remainder=True)
            message = cleartext

        else:
            raise ValueError("Incorrect signature header:", sig_header)

        if not signature.verify(message=message, verifying_pk=self.sender_verifying_key):
            raise InvalidSignature(f"Unable to verify message from: {self.sender_verifying_key}")

        return cleartext

    def __str__(self):
        return f"{self.__class__.__name__}({self.capsule})"

    def _payload(self) -> bytes:
        # TODO (#2743): this logic may not be necessary depending on the resolution.
        # If it is, it is better moved to BytestringSplitter.
        return (bytes(self.capsule) +
                (b'\x00' if self.signature is None else (b'\x01' + bytes(self.signature))) +
                bytes(self.sender_verifying_key) +
                VariableLengthBytestring(self.ciphertext))

    @classmethod
    def _brand(cls) -> bytes:
        return b'MKit'

    @classmethod
    def _version(cls) -> Tuple[int, int]:
        return 1, 0

    @classmethod
    def _old_version_handlers(cls) -> Dict:
        return {}

    @classmethod
    def _from_bytes_current(cls, data):
        splitter = BytestringSplitter(
            capsule_splitter,
            (bytes, 1))

        capsule, signature_flag, remainder = splitter(data, return_remainder=True)

        if signature_flag == b'\x00':
            signature = None
        elif signature_flag == b'\x01':
            signature, remainder = signature_splitter(remainder, return_remainder=True)
        else:
            raise ValueError("Incorrect format for the signature flag")

        splitter = BytestringSplitter(
            key_splitter,
            VariableLengthBytestring)

        sender_verifying_key, ciphertext = splitter(remainder)

        return cls(capsule, ciphertext, signature=signature, sender_verifying_key=sender_verifying_key)


class HRAC:
    """
    "hashed resource access code".

    A hash of:
    * Publisher's verifying key
    * Bob's verifying key
    * the label

    Publisher and Bob have all the information they need to construct this.
    Ursula does not, so we share it with her.

    This way, Bob can generate it and use it to find the TreasureMap.
    """

    # Note: this corresponds to the hardcoded size in the contracts
    # (which use `byte16` for this variable).
    SIZE = 16

    @classmethod
    def derive(cls, publisher_verifying_key: PublicKey, bob_verifying_key: PublicKey, label: bytes) -> 'HRAC':
        return cls(keccak_digest(bytes(publisher_verifying_key) + bytes(bob_verifying_key) + label)[:cls.SIZE])

    def __init__(self, hrac_bytes: bytes):
        self._hrac_bytes = hrac_bytes

    def __bytes__(self):
        return self._hrac_bytes

    @classmethod
    def from_bytes(cls, data: bytes) -> 'HRAC':
        if len(data) != cls.SIZE:
            raise ValueError(f"Incorrect HRAC size: expected {cls.SIZE}, got {len(data)}")
        return cls(data)

    def __eq__(self, other):
        return self._hrac_bytes == other._hrac_bytes

    def __hash__(self):
        return hash(self._hrac_bytes)

    def __str__(self):
        return f"HRAC({self._hrac_bytes.hex()})"


hrac_splitter = BytestringSplitter((HRAC, HRAC.SIZE))


class UnauthorizedKeyFragError(Exception):
    pass


class AuthorizedKeyFrag(Versioned):

    _WRIT_CHECKSUM_SIZE = 32

    # The size of a serialized message kit encrypting an AuthorizedKeyFrag.
    # Depends on encryption parameters in Umbral, has to be hardcoded.
    ENCRYPTED_SIZE = 613
    SERIALIZED_SIZE = Versioned._HEADER_SIZE + ENCRYPTED_SIZE

    def __init__(self, hrac: HRAC, kfrag_checksum: bytes, writ_signature: Signature, kfrag: KeyFrag):
        self.hrac = hrac
        self.kfrag_checksum = kfrag_checksum
        self.writ = bytes(hrac) + kfrag_checksum
        self.writ_signature = writ_signature
        self.kfrag = kfrag

    @classmethod
    def construct_by_publisher(cls,
                               hrac: HRAC,
                               verified_kfrag: VerifiedKeyFrag,
                               signer: Signer,
                               ) -> 'AuthorizedKeyFrag':

        # "un-verify" kfrag to keep further logic streamlined
        kfrag = KeyFrag.from_bytes(bytes(verified_kfrag))

        # Alice makes plain to Ursula that, upon decrypting this message,
        # this particular KFrag is authorized for use in the policy identified by this HRAC.
        kfrag_checksum = cls._kfrag_checksum(kfrag)
        writ = bytes(hrac) + kfrag_checksum
        writ_signature = signer.sign(writ)

        # The writ and the KFrag together represent a complete kfrag kit: the entirety of
        # the material needed for Ursula to assuredly service this policy.
        return cls(hrac, kfrag_checksum, writ_signature, kfrag)

    @staticmethod
    def _kfrag_checksum(kfrag: KeyFrag) -> bytes:
        return keccak_digest(bytes(kfrag))[:AuthorizedKeyFrag._WRIT_CHECKSUM_SIZE]

    def _payload(self) -> bytes:
        """Returns the unversioned bytes serialized representation of this instance."""
        return self.writ + bytes(self.writ_signature) + bytes(self.kfrag)

    @classmethod
    def _brand(cls) -> bytes:
        return b'AKF_'

    @classmethod
    def _version(cls) -> Tuple[int, int]:
        return 1, 0

    @classmethod
    def _old_version_handlers(cls) -> Dict:
        return {}

    @classmethod
    def _from_bytes_current(cls, data):
        # TODO: should we check the signature right away here?

        splitter = BytestringSplitter(
            hrac_splitter,  # HRAC
            (bytes, cls._WRIT_CHECKSUM_SIZE),  # kfrag checksum
            signature_splitter,  # Publisher's signature
            kfrag_splitter,
        )

        hrac, kfrag_checksum, writ_signature, kfrag = splitter(data)

        # Check integrity
        calculated_checksum = cls._kfrag_checksum(kfrag)
        if calculated_checksum != kfrag_checksum:
            raise ValueError("Incorrect KeyFrag checksum in the serialized data")

        return cls(hrac, kfrag_checksum, writ_signature, kfrag)

    def verify(self,
               hrac: HRAC,
               author_verifying_key: PublicKey,
               publisher_verifying_key: PublicKey,
               ) -> VerifiedKeyFrag:

        if not self.writ_signature.verify(message=self.writ, verifying_pk=publisher_verifying_key):
            raise UnauthorizedKeyFragError("Writ is not signed by the provided publisher")

        # TODO: should we keep HRAC in this object at all?
        if self.hrac != hrac:  # Funky request
            raise UnauthorizedKeyFragError("Incorrect HRAC")

        try:
            verified_kfrag = self.kfrag.verify(verifying_pk=author_verifying_key)
        except VerificationError:
            raise UnauthorizedKeyFragError("KeyFrag is not signed by the provided author")

        return verified_kfrag
