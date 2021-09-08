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


from typing import Dict, NamedTuple, Optional, Tuple, List, Iterable

from bytestring_splitter import BytestringSplitter, BytestringKwargifier, VariableLengthBytestring
from constant_sorrow.constants import (
    NOT_SIGNED,
    UNKNOWN_SENDER,
    DO_NOT_SIGN,
    SIGNATURE_TO_FOLLOW,
    SIGNATURE_IS_ON_CIPHERTEXT,
    NOT_SIGNED,
    )
from eth_typing import ChecksumAddress
from eth_utils import to_checksum_address, to_canonical_address

from nucypher.crypto.splitters import capsule_splitter, key_splitter, signature_splitter, checksum_address_splitter
import nucypher.crypto.umbral_adapter as umbral # need it to mock `umbral.encrypt`
from nucypher.crypto.umbral_adapter import PublicKey, VerifiedCapsuleFrag, Capsule, Signature


class MessageKit:
    """
    All the components needed to transmit and verify an encrypted message.
    """

    @classmethod
    def author(cls,
               recipient_key: PublicKey,
               plaintext: bytes,
               signer: 'SignatureStamp',
               sign_plaintext: bool = True
               ) -> 'MessageKit':
        if signer is not DO_NOT_SIGN:
            # The caller didn't expressly tell us not to sign; we'll sign.
            if sign_plaintext:
                # Sign first, encrypt second.
                sig_header = SIGNATURE_TO_FOLLOW
                signature = signer(plaintext)
                capsule, ciphertext = umbral.encrypt(recipient_key, sig_header + bytes(signature) + plaintext)
                signature_in_kit = None
            else:
                # Encrypt first, sign second.
                sig_header = SIGNATURE_IS_ON_CIPHERTEXT
                capsule, ciphertext = umbral.encrypt(recipient_key, sig_header + plaintext)
                signature = signer(ciphertext)
                signature_in_kit = signature
            message_kit = cls(ciphertext=ciphertext,
                              capsule=capsule,
                              sender_verifying_key=signer.as_umbral_pubkey(),
                              signature=signature_in_kit)
        else:
            # Don't sign.
            sig_header = NOT_SIGNED
            capsule, ciphertext = umbral.encrypt(recipient_key, sig_header + plaintext)
            message_kit = cls(ciphertext=ciphertext, capsule=capsule)

        return message_kit

    def __init__(self,
                 capsule: Capsule,
                 ciphertext: bytes,
                 sender_verifying_key: Optional[PublicKey] = None,
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

    def __str__(self):
        return f"{self.__class__.__name__}({self.capsule})"

    def __bytes__(self):
        return (bytes(self.capsule) +
                (b'\x00' if self.signature is None else (b'\x01' + bytes(self.signature))) +
                (b'\x00' if self.sender_verifying_key is None else (b'\x01' + bytes(self.sender_verifying_key))) +
                VariableLengthBytestring(self.ciphertext))

    @classmethod
    def from_bytes(cls, data: bytes):
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
            (bytes, 1))

        key_flag, remainder = splitter(remainder, return_remainder=True)

        if key_flag == b'\x00':
            sender_verifying_key = None
        elif key_flag == b'\x01':
            sender_verifying_key, remainder = key_splitter(remainder, return_remainder=True)
        else:
            raise ValueError("Incorrect format of the sender's key flag")

        ciphertext, = BytestringSplitter(VariableLengthBytestring)(remainder)

        return cls(capsule, ciphertext, signature=signature, sender_verifying_key=sender_verifying_key)

    def as_policy_kit(self, policy_key: PublicKey, threshold: int) -> 'PolicyMessageKit':
        return PolicyMessageKit.from_message_kit(self, policy_key, threshold)

    def as_retrieval_kit(self) -> 'RetrievalKit':
        return RetrievalKit(self.capsule, set())


class RetrievalKit:
    """
    An object encapsulating the information necessary for retrieval of cfrags from Ursulas.
    Contains the capsule and the checksum addresses of Ursulas from which the requester
    already received cfrags.
    """

    def __init__(self, capsule: Capsule, queried_addresses: Iterable[ChecksumAddress]):
        self.capsule = capsule
        # Can store cfrags too, if we're worried about Ursulas supplying duplicate ones.
        self.queried_addresses = set(queried_addresses)

    def __bytes__(self):
        return (bytes(self.capsule) +
                b''.join(to_canonical_address(address) for address in self.queried_addresses))

    @classmethod
    def from_bytes(cls, data: bytes):
        capsule, remainder = capsule_splitter(data, return_remainder=True)
        if remainder:
            addresses_as_bytes = checksum_address_splitter.repeat(remainder)
        else:
            addresses_as_bytes = ()
        return cls(capsule, set(to_checksum_address(address) for address in addresses_as_bytes))


class PolicyMessageKit:

    @classmethod
    def from_message_kit(cls,
                         message_kit: MessageKit,
                         policy_key: PublicKey,
                         threshold: int
                         ) -> 'PolicyMessageKit':
        # TODO: can we get rid of circular dependency?
        from nucypher.policy.orders import RetrievalResult
        return cls(policy_key, threshold, RetrievalResult.empty(), message_kit)

    def as_retrieval_kit(self) -> RetrievalKit:
        return RetrievalKit(self.capsule, self._result.addresses())

    def __init__(self,
                 policy_key: PublicKey,
                 threshold: int,
                 result: 'RetrievalResult',
                 message_kit: MessageKit,
                 ):
        self.message_kit = message_kit
        self.policy_key = policy_key
        self.threshold = threshold
        self._result = result

        # FIXME: temporarily, for compatibility with decrypt()
        self._cfrags = set(self._result.cfrags.values())

    # FIXME: temporary exposing message kit info to help `verify_from()`

    @property
    def capsule(self) -> Capsule:
        return self.message_kit.capsule

    @property
    def ciphertext(self) -> bytes:
        return self.message_kit.ciphertext

    @property
    def sender_verifying_key(self) -> PublicKey:
        return self.message_kit.sender_verifying_key

    def is_decryptable_by_receiver(self) -> bool:
        return len(self._result.cfrags) >= self.threshold

    def with_result(self, result: 'RetrievalResult') -> 'PolicyMessageKit':
        return PolicyMessageKit(policy_key=self.policy_key,
                                threshold=self.threshold,
                                result=self._result.with_result(result),
                                message_kit=self.message_kit)


class RevocationKit:

    def __init__(self, treasure_map, signer: 'SignatureStamp'):
        from nucypher.policy.orders import Revocation
        self.revocations = dict()
        for node_id, encrypted_kfrag in treasure_map:
            self.revocations[node_id] = Revocation(ursula_checksum_address=node_id,
                                                   encrypted_kfrag=encrypted_kfrag,
                                                   signer=signer)

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
