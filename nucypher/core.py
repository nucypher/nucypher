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
from nucypher.crypto.splitters import signature_splitter, capsule_splitter, key_splitter
from nucypher.crypto.signing import InvalidSignature
import nucypher.crypto.umbral_adapter as umbral # need it to mock `umbral.encrypt`
from nucypher.crypto.umbral_adapter import (
    SecretKey,
    PublicKey,
    Signer,
    Capsule,
    Signature,
    VerifiedCapsuleFrag,
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
