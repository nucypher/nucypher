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

import base64
from bytestring_splitter import BytestringSplitter
from constant_sorrow.constants import NOT_SIGNED

from nucypher.crypto.splitters import key_splitter, capsule_splitter, signature_splitter


KIT_NOT_SIGNED = b"\x00"
KIT_SIGNED_BUT_NO_SIGNATURE = b"\x01"  # includes verifying key
KIT_INCLUDES_SIGNATURE = b"\x02"  # includes verifying key


class UmbralMessageKit:

    base_splitter = BytestringSplitter((bytes, 1)) + capsule_splitter

    def __init__(self,
                 capsule,
                 sender_verifying_key=None,
                 ciphertext=None,
                 signature=NOT_SIGNED) -> None:

        if not sender_verifying_key and signature is not NOT_SIGNED:
            raise ValueError("You can't pass a signature without it's verifying key.")

        self.ciphertext = ciphertext
        self.capsule = capsule
        self.sender_verifying_key = sender_verifying_key
        self._signature = signature

    @property
    def signature(self):
        return self._signature

    def to_bytes(self, include_sender_verifying_key=True, include_signature=False):
        if include_signature and self.signature is NOT_SIGNED:
            raise ValueError("Cannot include a signature because this MessageKit is not signed.")

        if include_sender_verifying_key and self.sender_verifying_key is None:
            raise ValueError("Cannot include a verifying key. None was included in the MessageKit.")

        if include_sender_verifying_key:
            header = KIT_INCLUDES_SIGNATURE if include_signature else KIT_SIGNED_BUT_NO_SIGNATURE
        else:
            header = KIT_NOT_SIGNED

        # We include the header first, next the capsule.
        as_bytes = header + bytes(self.capsule)

        # Then, before the ciphertext, we see if we're including the sender's public key.
        # We want to put that first because it's typically of known length.
        if include_sender_verifying_key:
            as_bytes += bytes(self.sender_verifying_key)

        if include_signature:
            as_bytes += bytes(self.signature)

        as_bytes += self.ciphertext

        return as_bytes

    def __bytes__(self):
        it_has_a_key = self.sender_verifying_key is not None
        return self.to_bytes(include_sender_verifying_key=it_has_a_key,
                             include_signature=False)

    def to_base64(self):
        return base64.b64encode(bytes(self)).decode("utf-8")

    @classmethod
    def from_bytes(cls, some_bytes: bytes):
        header, capsule, remainder = cls.base_splitter(some_bytes, return_remainder=True)
        if header == KIT_NOT_SIGNED:
            sender_verifying_key = None
            signature = NOT_SIGNED
            ciphertext = remainder
        elif header == KIT_SIGNED_BUT_NO_SIGNATURE:
            sender_verifying_key, ciphertext = key_splitter(remainder, return_remainder=True)
            signature = NOT_SIGNED
        elif header == KIT_INCLUDES_SIGNATURE:
            splitter = key_splitter + signature_splitter
            sender_verifying_key, signature, ciphertext = splitter(remainder, return_remainder=True)

        message_kit = cls(capsule=capsule,
                          sender_verifying_key=sender_verifying_key,
                          ciphertext=ciphertext,
                          signature=signature)
        return message_kit

    @classmethod
    def from_base64(cls, some_b64_str: str):
        some_bytes = base64.b64decode(some_b64_str)
        message_kit = cls.from_bytes(some_bytes)
        return message_kit

    def __eq__(self, other):
        eq_conditions = (self.ciphertext == other.ciphertext,
                         self.capsule == other.capsule,
                         self.sender_verifying_key == other.sender_verifying_key)
        return all(eq_conditions)

    def __hash__(self):
        return hash(bytes(self))

    def __repr__(self):
        return f'{self.__class__.__name__}:{hex(hash(self) & 0xFFFFFFFF)[2:]}'


class RevocationKit:

    def __init__(self, policy: 'Policy', signer: 'SignatureStamp'):
        from nucypher.policy.collections import Revocation
        self.revocations = dict()
        for node_id, arrangement_id in policy.treasure_map:
            self.revocations[node_id] = Revocation(arrangement_id, signer=signer)

    def __iter__(self):
        return iter(self.revocations.values())

    def __getitem__(self, node_id):
        return self.revocations[node_id]

    def __len__(self):
        return len(self.revocations)

    def __eq__(self, other):
        return self.revocations == other.revocations

    @property
    def revokable_addresses(self):
        """
        Returns a Set of revokable addresses in the checksum address formatting
        """
        return set(self.revocations.keys())

    def add_confirmation(self, node_id, signed_receipt):
        """
        Adds a signed confirmation of Ursula's ability to revoke the arrangement.
        """
        # TODO: Verify Ursula's signature
        # TODO: Implement receipts
        raise NotImplementedError
