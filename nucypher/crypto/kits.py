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


from bytestring_splitter import BytestringSplitter
from constant_sorrow import constants

from nucypher.crypto.splitters import key_splitter, capsule_splitter


class CryptoKit:
    splitter = None

    @classmethod
    def split_bytes(cls, some_bytes):
        if not cls.splitter:
            raise TypeError("This kit doesn't have a splitter defined.")

        return cls.splitter(some_bytes,
                            return_remainder=cls.return_remainder_when_splitting)

    @classmethod
    def from_bytes(cls, some_bytes):
        constituents = cls.split_bytes(some_bytes)
        return cls(*constituents)


class MessageKit(CryptoKit):

    def __init__(self,
                 capsule,
                 sender_verifying_key=None,
                 ciphertext=None,
                 signature=constants.NOT_SIGNED) -> None:

        self.ciphertext = ciphertext
        self.capsule = capsule
        self.sender_verifying_key = sender_verifying_key
        self._signature = signature

    def to_bytes(self, include_alice_pubkey=True):
        # We include the capsule first.
        as_bytes = bytes(self.capsule)

        # Then, before the ciphertext, we see if we're including alice's public key.
        # We want to put that first because it's typically of known length.
        if include_alice_pubkey and self.sender_verifying_key:
            as_bytes += bytes(self.sender_verifying_key)

        as_bytes += self.ciphertext
        return as_bytes

    @property
    def signature(self):
        return self._signature

    def __bytes__(self):
        return bytes(self.capsule) + self.ciphertext


class UmbralMessageKit(MessageKit):

    return_remainder_when_splitting = True
    splitter = capsule_splitter + key_splitter

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.policy_pubkey = None

    @classmethod
    def from_bytes(cls, some_bytes):
        capsule, sender_verifying_key, ciphertext = cls.split_bytes(some_bytes)
        return cls(capsule=capsule, sender_verifying_key=sender_verifying_key, ciphertext=ciphertext)


class RevocationKit:

    def __init__(self, policy: 'Policy', signer: 'SignatureStamp'):
        from nucypher.policy.models import Revocation
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
