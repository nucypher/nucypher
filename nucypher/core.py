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

from typing import Optional, Sequence, Dict, Tuple, List, Iterable, Mapping, NamedTuple, Callable

from bytestring_splitter import (
    BytestringSplitter,
    VariableLengthBytestring,
    BytestringKwargifier,
    BytestringSplittingError,
)
from eth_typing.evm import ChecksumAddress
from eth_utils.address import to_checksum_address, to_canonical_address

from nucypher.utilities.versioning import Versioned

from nucypher.blockchain.eth.constants import LENGTH_ECDSA_SIGNATURE_WITH_RECOVERY
from nucypher.crypto.utils import keccak_digest
from nucypher.crypto.signing import InvalidSignature
import nucypher.crypto.umbral_adapter as umbral # need it to mock `umbral.encrypt`
from nucypher.crypto.umbral_adapter import (
    SecretKey,
    PublicKey,
    Signer,
    Capsule,
    Signature,
    CapsuleFrag,
    VerifiedCapsuleFrag,
    KeyFrag,
    VerifiedKeyFrag,
    VerificationError,
    decrypt_original,
    decrypt_reencrypted,
    )


ETH_ADDRESS_BYTE_LENGTH = 20

key_splitter = BytestringSplitter((PublicKey, PublicKey.serialized_size()))
signature_splitter = BytestringSplitter((Signature, Signature.serialized_size()))
capsule_splitter = BytestringSplitter((Capsule, Capsule.serialized_size()))
cfrag_splitter = BytestringSplitter((CapsuleFrag, CapsuleFrag.serialized_size()))
kfrag_splitter = BytestringSplitter((KeyFrag, KeyFrag.serialized_size()))
checksum_address_splitter = BytestringSplitter((to_checksum_address, ETH_ADDRESS_BYTE_LENGTH)) # TODO: is there a pre-defined constant?
variable_length_splitter = BytestringSplitter(VariableLengthBytestring)


_OPTIONAL_NONE = b'\x00'
_OPTIONAL_SOME = b'\x01'


def serialize_optional(value: Optional) -> bytes:
    if value is None:
        return _OPTIONAL_NONE
    else:
        return _OPTIONAL_SOME + bytes(value)


def take_optional(take_obj: Callable[[bytes], Tuple[object, bytes]], data: bytes):
    optional_flag = data[0:1]
    remainder = data[1:]

    if optional_flag == _OPTIONAL_NONE:
        return None, remainder
    elif optional_flag == _OPTIONAL_SOME:
        obj, remainder = take_obj(remainder)
        return obj, remainder
    else:
        raise ValueError(f"Incorrect optional flag: {optional_flag}")


def take_decentralized_identity_evidence(data):
    expected_length = LENGTH_ECDSA_SIGNATURE_WITH_RECOVERY
    if len(data) < LENGTH_ECDSA_SIGNATURE_WITH_RECOVERY:
        raise ValueError(f"Not enough bytes to fit a decentralized_identity_evidence ({len(data)})")
    return data[:expected_length], data[expected_length:]


class MessageKit(Versioned):
    """
    A message encrypted for re-encryption
    """

    @classmethod
    def author(cls, policy_encrypting_key: PublicKey, plaintext: bytes) -> 'MessageKit':
        capsule, ciphertext = umbral.encrypt(policy_encrypting_key, plaintext)
        return cls(capsule=capsule, ciphertext=ciphertext)

    def __init__(self, capsule: Capsule, ciphertext: bytes):
        self.ciphertext = ciphertext
        self.capsule = capsule

    def __eq__(self, other):
        return (self.ciphertext == other.ciphertext and
                self.capsule == other.capsule)

    def decrypt(self, sk: SecretKey) -> bytes:
        return decrypt_original(sk, self.capsule, self.ciphertext)

    def decrypt_reencrypted(self,
                            sk: SecretKey,
                            policy_encrypting_key: PublicKey,
                            cfrags: Sequence[VerifiedCapsuleFrag],
                            ) -> bytes:
        return decrypt_reencrypted(sk, policy_encrypting_key, self.capsule, cfrags, self.ciphertext)

    def __str__(self):
        return f"{self.__class__.__name__}({self.capsule})"

    def _payload(self) -> bytes:
        return bytes(self.capsule) + VariableLengthBytestring(self.ciphertext)

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
        splitter = BytestringSplitter(capsule_splitter, VariableLengthBytestring)
        capsule, ciphertext, remainder = splitter(data, return_remainder=True)
        return cls(capsule, ciphertext), remainder


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


class AuthorizedKeyFrag(Versioned):

    def __init__(self, signature: Signature, kfrag: KeyFrag):
        self.signature = signature
        self.kfrag = kfrag

    @classmethod
    def construct_by_publisher(cls,
                               signer: Signer,
                               hrac: HRAC,
                               verified_kfrag: VerifiedKeyFrag,
                               ) -> 'AuthorizedKeyFrag':

        # "un-verify" kfrag to keep further logic streamlined
        kfrag = KeyFrag.from_bytes(bytes(verified_kfrag))

        # Publisher makes plain to Ursula that, upon decrypting this message,
        # this particular KFrag is authorized for use in the policy identified by this HRAC.
        signature = signer.sign(bytes(hrac) + bytes(kfrag))

        return cls(signature, kfrag)

    def _payload(self) -> bytes:
        """Returns the unversioned bytes serialized representation of this instance."""
        return bytes(self.signature) + bytes(self.kfrag)

    @classmethod
    def _brand(cls) -> bytes:
        return b'AKFr'

    @classmethod
    def _version(cls) -> Tuple[int, int]:
        return 1, 0

    @classmethod
    def _old_version_handlers(cls) -> Dict:
        return {}

    @classmethod
    def _from_bytes_current(cls, data):
        splitter = BytestringSplitter(signature_splitter, kfrag_splitter)
        signature, kfrag, remainder = splitter(data, return_remainder=True)
        return cls(signature, kfrag), remainder

    def verify(self,
               hrac: HRAC,
               publisher_verifying_key: PublicKey,
               ) -> VerifiedKeyFrag:

        signed_message = bytes(hrac) + bytes(self.kfrag)

        if not self.signature.verify(message=signed_message, verifying_pk=publisher_verifying_key):
            raise InvalidSignature("HRAC + KeyFrag are not signed by the provided publisher")

        # Ursula has no side channel to get the KeyFrag author's key,
        # so verifying the keyfrag is useless.
        # TODO: assuming here that VerifiedKeyFrag and KeyFrag have the same byte representation;
        # would it be more clear if `kfrag` had some method like `force_verify()`?
        verified_kfrag = VerifiedKeyFrag.from_verified_bytes(bytes(self.kfrag))

        return verified_kfrag


class EncryptedKeyFrag:

    _splitter = BytestringSplitter(capsule_splitter, VariableLengthBytestring)

    @classmethod
    def author(cls, recipient_key: PublicKey, authorized_kfrag: AuthorizedKeyFrag):
        # TODO: using Umbral for encryption to avoid introducing more crypto primitives.
        # Most probably it is an overkill, unless it can be used somehow
        # for Ursula-to-Ursula "baton passing".
        capsule, ciphertext = umbral.encrypt(recipient_key, bytes(authorized_kfrag))
        return cls(capsule, ciphertext)

    def __init__(self, capsule: Capsule, ciphertext: bytes):
        self.capsule = capsule
        self.ciphertext = ciphertext

    def decrypt(self, sk: SecretKey) -> AuthorizedKeyFrag:
        cleartext = decrypt_original(sk, self.capsule, self.ciphertext)
        return AuthorizedKeyFrag.from_bytes(cleartext)

    def __bytes__(self):
        return bytes(self.capsule) + bytes(VariableLengthBytestring(self.ciphertext))

    # Ideally we would define a splitter here that would deserialize into an EKF,
    # but due to BSS limitations it cannot be nested (since it doesn't have a definite size).
    # So we have to define this helper method and use that instead.
    @classmethod
    def take(cls, data):
        capsule, ciphertext, remainder = cls._splitter(data, return_remainder=True)
        return cls(capsule, ciphertext), remainder

    def __eq__(self, other):
        return self.capsule == other.capsule and self.ciphertext == other.ciphertext


class TreasureMap(Versioned):

    def __init__(self,
                 threshold: int,
                 hrac: HRAC,
                 policy_encrypting_key: PublicKey,
                 publisher_verifying_key: PublicKey,
                 destinations: Dict[ChecksumAddress, EncryptedKeyFrag]):
        self.threshold = threshold
        self.destinations = destinations
        self.hrac = hrac
        self.policy_encrypting_key = policy_encrypting_key
        self.publisher_verifying_key = publisher_verifying_key

    def __iter__(self):
        return iter(self.destinations.items())

    def __len__(self):
        return len(self.destinations)

    def __eq__(self, other):
        if not isinstance(other, TreasureMap):
            return False

        return (self.threshold == other.threshold and
                self.hrac == other.hrac and
                self.destinations == other.destinations)

    @classmethod
    def construct_by_publisher(cls,
                               signer: Signer,
                               hrac: HRAC,
                               policy_encrypting_key: PublicKey,
                               assigned_kfrags: Mapping[ChecksumAddress, Tuple[PublicKey, VerifiedKeyFrag]],
                               threshold: int,
                               ) -> 'TreasureMap':
        """Create a new treasure map for a collection of ursulas and kfrags."""

        if threshold < 1 or threshold > 255:
            raise ValueError("The threshold must be between 1 and 255.")

        if len(assigned_kfrags) < threshold:
            raise ValueError(
                f"The number of destinations ({len(assigned_kfrags)}) "
                f"must be equal or greater than the threshold ({threshold})")

        # Encrypt each kfrag for an Ursula.
        destinations = {}
        for ursula_address, key_and_kfrag in assigned_kfrags.items():
            ursula_key, verified_kfrag = key_and_kfrag
            authorized_kfrag = AuthorizedKeyFrag.construct_by_publisher(signer=signer,
                                                                        hrac=hrac,
                                                                        verified_kfrag=verified_kfrag,
                                                                        )
            encrypted_kfrag = EncryptedKeyFrag.author(recipient_key=ursula_key,
                                                      authorized_kfrag=authorized_kfrag)

            destinations[ursula_address] = encrypted_kfrag

        return cls(threshold=threshold,
                   hrac=hrac,
                   policy_encrypting_key=policy_encrypting_key,
                   publisher_verifying_key=signer.verifying_key(),
                   destinations=destinations)

    @classmethod
    def _brand(cls) -> bytes:
        return b'TMap'

    @classmethod
    def _version(cls) -> Tuple[int, int]:
        return 1, 0

    @classmethod
    def _old_version_handlers(cls) -> Dict:
        return {}

    def _payload(self) -> bytes:
        """Returns the unversioned bytes serialized representation of this instance."""
        assigned_kfrags = b''.join(
            to_canonical_address(ursula_address) + bytes(encrypted_kfrag)
            for ursula_address, encrypted_kfrag in self.destinations.items()
            )

        return (self.threshold.to_bytes(1, "big") +
                bytes(self.hrac) +
                bytes(self.policy_encrypting_key) +
                bytes(self.publisher_verifying_key) +
                bytes(VariableLengthBytestring(assigned_kfrags)))

    @classmethod
    def _from_bytes_current(cls, data):

        main_splitter = BytestringSplitter(
            (int, 1, {'byteorder': 'big'}),
            hrac_splitter,
            key_splitter,
            key_splitter,
            VariableLengthBytestring,
        )

        threshold, hrac, policy_encrypting_key, publisher_verifying_key, assigned_kfrags_bytes, remainder = main_splitter(data, return_remainder=True)

        destinations = {}
        while assigned_kfrags_bytes:
            ursula_address, assigned_kfrags_bytes = checksum_address_splitter(assigned_kfrags_bytes, return_remainder=True)
            ekf, assigned_kfrags_bytes = EncryptedKeyFrag.take(assigned_kfrags_bytes)
            destinations[ursula_address] = ekf

        return cls(threshold, hrac, policy_encrypting_key, publisher_verifying_key, destinations), remainder

    def encrypt(self,
                signer: Signer,
                recipient_key: PublicKey,
                ) -> 'EncryptedTreasureMap':
        return EncryptedTreasureMap.construct_by_publisher(signer=signer,
                                                           recipient_key=recipient_key,
                                                           treasure_map=self)


class AuthorizedTreasureMap(Versioned):

    @classmethod
    def construct_by_publisher(cls,
                               signer: Signer,
                               recipient_key: PublicKey,
                               treasure_map: TreasureMap
                               ) -> 'AuthorizedTreasureMap':
        payload = bytes(recipient_key) + bytes(treasure_map)
        signature = signer.sign(payload)
        return cls(signature, treasure_map)

    def __init__(self, signature: Signature, treasure_map: TreasureMap):
        self.signature = signature
        self.treasure_map = treasure_map

    @classmethod
    def _brand(cls) -> bytes:
        return b'AMap'

    @classmethod
    def _version(cls) -> Tuple[int, int]:
        return 1, 0

    @classmethod
    def _old_version_handlers(cls) -> Dict:
        return {}

    def _payload(self) -> bytes:
        """Returns the unversioned bytes serialized representation of this instance."""
        return (bytes(self.signature) +
                bytes(self.treasure_map))

    @classmethod
    def _from_bytes_current(cls, data):
        signature, remainder = signature_splitter(data, return_remainder=True)
        treasure_map, remainder = TreasureMap.take(remainder)
        return cls(signature, treasure_map), remainder

    def verify(self, recipient_key: PublicKey, publisher_verifying_key: PublicKey) -> TreasureMap:
        payload = bytes(recipient_key) + bytes(self.treasure_map)
        if not self.signature.verify(message=payload, verifying_pk=publisher_verifying_key):
            raise InvalidSignature("This TreasureMap does not contain the correct signature "
                                   "from the publisher.")
        return self.treasure_map


class EncryptedTreasureMap(Versioned):

    def __init__(self, capsule: Capsule, ciphertext: bytes):
        self.capsule = capsule
        self.ciphertext = ciphertext

    @classmethod
    def construct_by_publisher(cls,
                               signer: Signer,
                               recipient_key: PublicKey,
                               treasure_map: TreasureMap,
                               ) -> 'EncryptedTreasureMap':

        # TODO: using Umbral for encryption to avoid introducing more crypto primitives.
        # Most probably it is an overkill, unless it can be used somehow
        # for Ursula-to-Ursula "baton passing".

        # TODO: `signer` here can be different from the one in TreasureMap, it seems.
        # Do we ever cross-check them? Do we want to enforce them to be the same?
        payload = AuthorizedTreasureMap.construct_by_publisher(signer=signer,
                                                               recipient_key=recipient_key,
                                                               treasure_map=treasure_map)

        capsule, ciphertext = umbral.encrypt(recipient_key, bytes(payload))
        return cls(capsule, ciphertext)

    def decrypt(self, sk: SecretKey) -> AuthorizedTreasureMap:
        payload_bytes = decrypt_original(sk, self.capsule, self.ciphertext)
        return AuthorizedTreasureMap.from_bytes(payload_bytes)

    def _payload(self) -> bytes:
        return bytes(self.capsule) + bytes(VariableLengthBytestring(self.ciphertext))

    @classmethod
    def _brand(cls) -> bytes:
        return b'EMap'

    @classmethod
    def _version(cls) -> Tuple[int, int]:
        return 1, 0

    @classmethod
    def _old_version_handlers(cls) -> Dict:
        return {}

    @classmethod
    def _from_bytes_current(cls, data):
        splitter = BytestringSplitter(capsule_splitter, VariableLengthBytestring)
        capsule, ciphertext, remainder = splitter(data, return_remainder=True)
        return cls(capsule, ciphertext), remainder

    def __eq__(self, other):
        return bytes(self) == bytes(other)

    def __hash__(self):
        return hash((self.__class__, bytes(self)))


class ReencryptionRequest(Versioned):
    """
    A request for an Ursula to reencrypt for several capsules.
    """

    @classmethod
    def from_treasure_map(cls,
                          ursula_address: ChecksumAddress,
                          capsules: Sequence[Capsule],
                          treasure_map: TreasureMap,
                          bob_verifying_key: PublicKey,
                          ) -> 'ReencryptionRequest':
        return cls(hrac=treasure_map.hrac,
                   publisher_verifying_key=treasure_map.publisher_verifying_key,
                   bob_verifying_key=bob_verifying_key,
                   encrypted_kfrag=treasure_map.destinations[ursula_address],
                   capsules=capsules,
                   )

    def __init__(self,
                 hrac: HRAC,
                 publisher_verifying_key: PublicKey,
                 bob_verifying_key: PublicKey,
                 encrypted_kfrag: EncryptedKeyFrag,
                 capsules: List[Capsule]):

        self.hrac = hrac
        self.publisher_verifying_key = publisher_verifying_key
        self.bob_verifying_key = bob_verifying_key
        self.encrypted_kfrag = encrypted_kfrag
        self.capsules = capsules

    def _payload(self) -> bytes:
        return (bytes(self.hrac) +
                bytes(self.publisher_verifying_key) +
                bytes(self.bob_verifying_key) +
                bytes(self.encrypted_kfrag) +
                bytes(VariableLengthBytestring(b''.join(bytes(capsule) for capsule in self.capsules)))
                )

    @classmethod
    def _brand(cls) -> bytes:
        return b'ReRq'

    @classmethod
    def _version(cls) -> Tuple[int, int]:
        return 1, 0

    @classmethod
    def _old_version_handlers(cls) -> Dict:
        return {}

    @classmethod
    def _from_bytes_current(cls, data):
        splitter = (hrac_splitter +
                    key_splitter +
                    key_splitter)

        hrac, publisher_vk, bob_vk, remainder = splitter(data, return_remainder=True)
        ekfrag, remainder = EncryptedKeyFrag.take(remainder)
        capsule_bytes, remainder = variable_length_splitter(remainder, return_remainder=True)
        capsules = capsule_splitter.repeat(capsule_bytes)
        return cls(hrac, publisher_vk, bob_vk, ekfrag, capsules), remainder


class ReencryptionResponse(Versioned):
    """
    A response from Ursula with reencrypted capsule frags.
    """

    @classmethod
    def construct_by_ursula(cls,
                            signer: Signer,
                            capsules: List[Capsule],
                            cfrags: List[VerifiedCapsuleFrag],
                            ) -> 'ReencryptionResponse':

        # un-verify
        cfrags = [CapsuleFrag.from_bytes(bytes(cfrag)) for cfrag in cfrags]

        capsules_bytes = b''.join(bytes(capsule) for capsule in capsules)
        cfrags_bytes = b''.join(bytes(cfrag) for cfrag in cfrags)
        signature = signer.sign(capsules_bytes + cfrags_bytes)
        return cls(cfrags, signature)

    def __init__(self, cfrags: List[CapsuleFrag], signature: Signature):
        self.cfrags = cfrags
        self.signature = signature

    def _payload(self) -> bytes:
        """Returns the unversioned bytes serialized representation of this instance."""
        return bytes(self.signature) + bytes(VariableLengthBytestring(b''.join(bytes(cfrag) for cfrag in self.cfrags)))

    @classmethod
    def _brand(cls) -> bytes:
        return b'ReRs'

    @classmethod
    def _version(cls) -> Tuple[int, int]:
        return 1, 0

    @classmethod
    def _old_version_handlers(cls) -> Dict:
        return {}

    @classmethod
    def _from_bytes_current(cls, data):
        splitter = BytestringSplitter(signature_splitter, VariableLengthBytestring)
        signature, cfrags_bytes, remainder = splitter(data, return_remainder=True)

        # We would never send a request with no capsules, so there should be cfrags.
        # The splitter would fail anyway, this just makes the error message more clear.
        if not cfrags_bytes:
            raise ValueError(f"{cls.__name__} contains no cfrags")

        cfrags = cfrag_splitter.repeat(cfrags_bytes)
        return cls(cfrags, signature), remainder

    def verify(self,
               capsules: Sequence[Capsule],
               alice_verifying_key: PublicKey,
               ursula_verifying_key: PublicKey,
               policy_encrypting_key: PublicKey,
               bob_encrypting_key: PublicKey,
               ) -> List[VerifiedCapsuleFrag]:

        if len(capsules) != len(self.cfrags):
            raise ValueError("Mismatched number of capsules and cfrags")

        capsules_bytes = b''.join(bytes(capsule) for capsule in capsules)
        cfrags_bytes = b''.join(bytes(cfrag) for cfrag in self.cfrags)

        # Validate re-encryption signature
        if not self.signature.verify(ursula_verifying_key, capsules_bytes + cfrags_bytes):
            message = (f"{capsules} and {self.cfrags} "
                        "are not properly signed by Ursula.")
            raise InvalidSignature(message)

        verified_cfrags = {}
        for capsule, cfrag in zip(capsules, self.cfrags):
            verified_cfrags[capsule] = cfrag.verify(capsule,
                                                    verifying_pk=alice_verifying_key,
                                                    delegating_pk=policy_encrypting_key,
                                                    receiving_pk=bob_encrypting_key)

        return verified_cfrags


class RetrievalKit(Versioned):
    """
    An object encapsulating the information necessary for retrieval of cfrags from Ursulas.
    Contains the capsule and the checksum addresses of Ursulas from which the requester
    already received cfrags.
    """

    @classmethod
    def from_message_kit(cls, message_kit: MessageKit) -> 'RetrievalKit':
        return cls(message_kit.capsule, set())

    def __init__(self, capsule: Capsule, queried_addresses: Iterable[ChecksumAddress]):
        self.capsule = capsule
        # Can store cfrags too, if we're worried about Ursulas supplying duplicate ones.
        self.queried_addresses = set(queried_addresses)

    def _payload(self) -> bytes:
        return (bytes(self.capsule) +
                bytes(VariableLengthBytestring(b''.join(to_canonical_address(address) for address in self.queried_addresses))))

    @classmethod
    def _brand(cls) -> bytes:
        return b'RKit'

    @classmethod
    def _version(cls) -> Tuple[int, int]:
        return 1, 0

    @classmethod
    def _old_version_handlers(cls) -> Dict:
        return {}

    @classmethod
    def _from_bytes_current(cls, data):
        splitter = BytestringSplitter(capsule_splitter, VariableLengthBytestring)
        capsule, addresses_bytes, remainder = splitter(data, return_remainder=True)
        if addresses_bytes:
            addresses = checksum_address_splitter.repeat(addresses_bytes)
        else:
            addresses = ()
        return cls(capsule, addresses), remainder


class RevocationOrder(Versioned):
    """
    Represents a string used by characters to perform a revocation on a specific Ursula.
    """

    @classmethod
    def author(cls,
               signer: Signer,
               ursula_address: ChecksumAddress,
               encrypted_kfrag: EncryptedKeyFrag,
               ) -> 'RevocationOrder':
            return cls(ursula_address=ursula_address,
                       encrypted_kfrag=encrypted_kfrag,
                       signature=signer.sign(cls._signed_payload(ursula_address, encrypted_kfrag)))

    def __init__(self, ursula_address: ChecksumAddress, encrypted_kfrag: EncryptedKeyFrag, signature: Signature):
        self.ursula_address = ursula_address
        self.encrypted_kfrag = encrypted_kfrag
        self.signature = signature

    def __repr__(self):
        return bytes(self)

    def __len__(self):
        return len(bytes(self))

    def __eq__(self, other):
        return bytes(self) == bytes(other)

    @staticmethod
    def _signed_payload(ursula_address, encrypted_kfrag):
        return to_canonical_address(ursula_address) + bytes(encrypted_kfrag)

    def verify_signature(self, alice_verifying_key: PublicKey) -> bool:
        """
        Verifies the revocation was from the provided pubkey.
        """
        # TODO: raise an exception instead of returning `bool`?
        payload = self._signed_payload(self.ursula_address, self.encrypted_kfrag)
        if not self.signature.verify(payload, alice_verifying_key):
            raise InvalidSignature(f"Revocation has an invalid signature: {self.signature}")
        return True

    @classmethod
    def _brand(cls) -> bytes:
        return b'Revo'

    @classmethod
    def _version(cls) -> Tuple[int, int]:
        return 1, 0

    @classmethod
    def _old_version_handlers(cls) -> Dict:
        return {}

    def _payload(self) -> bytes:
        return bytes(self.signature) + self._signed_payload(self.ursula_address, self.encrypted_kfrag)

    @classmethod
    def _from_bytes_current(cls, data):
        splitter = BytestringSplitter(
            signature_splitter,
            checksum_address_splitter,  # ursula canonical address
        )
        signature, ursula_address, remainder = splitter(data, return_remainder=True)
        ekfrag, remainder = EncryptedKeyFrag.take(remainder)
        obj = cls(ursula_address=ursula_address,
                  encrypted_kfrag=ekfrag,
                  signature=signature)
        return obj, remainder


class NodeMetadataPayload(NamedTuple):

    public_address: bytes
    domain: str
    timestamp_epoch: int
    verifying_key: PublicKey
    encrypting_key: PublicKey
    certificate_bytes: bytes # serialized `cryptography.x509.Certificate`
    host: str
    port: int
    decentralized_identity_evidence: Optional[bytes] # TODO: make its own type?

    _splitter = BytestringSplitter(
        (bytes, ETH_ADDRESS_BYTE_LENGTH), # public_address
        VariableLengthBytestring, # domain_bytes
        (int, 4, {'byteorder': 'big'}), # timestamp_epoch
        key_splitter, # verifying_key
        key_splitter, # encrypting_key
        VariableLengthBytestring, # certificate_bytes
        VariableLengthBytestring, # host_bytes
        (int, 2, {'byteorder': 'big'}), # port
        )

    def __bytes__(self):
        as_bytes = bytes().join((self.public_address,
                                 bytes(VariableLengthBytestring(self.domain.encode('utf-8'))),
                                 self.timestamp_epoch.to_bytes(4, 'big'),
                                 bytes(self.verifying_key),
                                 bytes(self.encrypting_key),
                                 bytes(VariableLengthBytestring(self.certificate_bytes)),
                                 bytes(VariableLengthBytestring(self.host.encode('utf-8'))),
                                 self.port.to_bytes(2, 'big'),
                                 serialize_optional(self.decentralized_identity_evidence),
                                ))
        return as_bytes

    @classmethod
    def take(cls, data):
        *fields, remainder = cls._splitter(data, return_remainder=True)

        (public_address,
         domain,
         timestamp_epoch,
         verifying_key,
         encrypting_key,
         certificate_bytes,
         host,
         port,
         ) = fields

        decentralized_identity_evidence, remainder = take_optional(take_decentralized_identity_evidence, remainder)

        obj = cls(public_address=public_address,
                  domain=domain.decode('utf-8'),
                  timestamp_epoch=timestamp_epoch,
                  verifying_key=verifying_key,
                  encrypting_key=encrypting_key,
                  certificate_bytes=certificate_bytes,
                  host=host.decode('utf-8'),
                  port=port,
                  decentralized_identity_evidence=decentralized_identity_evidence,
                  )

        return obj, remainder

    @classmethod
    def from_bytes(cls, data):
        obj, remainder = cls.take(data)
        if remainder:
            raise ValueError(f"{len(remainder)} bytes remaining after deserializing {cls}")
        return obj


class NodeMetadata(Versioned):

    @classmethod
    def author(cls, signer: Signer, **kwds):
        payload = NodeMetadataPayload(**kwds)
        signature = signer.sign(bytes(payload))
        # TODO: we can cache payload bytes here, for later use in serialization/verification
        return cls(signature=signature, payload=payload)

    def __init__(self, signature: Signature, payload: NodeMetadataPayload):
        self.signature = signature
        self._metadata_payload = payload
        for name, value in payload._asdict().items():
            setattr(self, name, value)

    def verify(self) -> bool:
        # Note: in order for this to make sense, `verifying_key` must be checked independently.
        # Currently it is done in `validate_worker()` (using `decentralized_identity_evidence`)
        # TODO: do this on deserialization?
        return self.signature.verify(message=bytes(self._metadata_payload), verifying_pk=self.verifying_key)

    @classmethod
    def _brand(cls) -> bytes:
        return b'NdMd'

    @classmethod
    def _version(cls) -> Tuple[int, int]:
        return 1, 0

    @classmethod
    def _old_version_handlers(cls) -> Dict:
        return {}

    def _payload(self):
        return bytes(self.signature) + bytes(self._metadata_payload)

    @classmethod
    def _from_bytes_current(cls, data: bytes):
        signature, remainder = signature_splitter(data, return_remainder=True)
        payload, remainder = NodeMetadataPayload.take(remainder)
        return cls(signature=signature, payload=payload), remainder

    @classmethod
    def _batch_from_bytes(cls, data: bytes):
        nodes = []
        while data:
            node, data = cls.take(data)
            nodes.append(node)
        return nodes


class MetadataRequest(Versioned):

    _fleet_state_checksum_splitter = BytestringSplitter((bytes, 32))

    def __init__(self,
                 fleet_state_checksum: str,
                 announce_nodes: Optional[Iterable[NodeMetadata]] = None,
                 ):

        self.fleet_state_checksum = fleet_state_checksum
        self.announce_nodes = announce_nodes

    @classmethod
    def _brand(cls) -> bytes:
        return b'MdRq'

    @classmethod
    def _version(cls) -> Tuple[int, int]:
        return 1, 0

    @classmethod
    def _old_version_handlers(cls) -> Dict:
        return {}

    def _payload(self):
        if self.announce_nodes:
            nodes_bytes = b''.join(bytes(n) for n in self.announce_nodes)
        else:
            nodes_bytes = b''
        return bytes.fromhex(self.fleet_state_checksum) + bytes(VariableLengthBytestring(nodes_bytes))

    @classmethod
    def _from_bytes_current(cls, data):
        splitter = BytestringSplitter(
            (bytes, 32), # fleet state checksum
            VariableLengthBytestring,
            )
        fleet_state_checksum_bytes, nodes_bytes, remainder = splitter(data, return_remainder=True)
        if nodes_bytes:
            nodes = NodeMetadata._batch_from_bytes(nodes_bytes)
        else:
            nodes = None
        obj = cls(fleet_state_checksum=fleet_state_checksum_bytes.hex(),
                  announce_nodes=nodes)
        return obj, remainder


class MetadataResponse(Versioned):

    @classmethod
    def author(cls,
               signer: Signer,
               timestamp_epoch: int,
               this_node: Optional[NodeMetadata] = None,
               other_nodes: Optional[Iterable[NodeMetadata]] = None,
               ):
        payload = cls._signed_payload(timestamp_epoch, this_node, other_nodes)
        signature = signer.sign(payload)
        return cls(signature=signature,
                   timestamp_epoch=timestamp_epoch,
                   this_node=this_node,
                   other_nodes=other_nodes)

    @staticmethod
    def _signed_payload(timestamp_epoch, this_node, other_nodes):
        timestamp = timestamp_epoch.to_bytes(4, byteorder="big")
        nodes_payload = b''.join(bytes(node) for node in other_nodes) if other_nodes else b''
        return (
            timestamp +
            serialize_optional(this_node) +
            bytes(VariableLengthBytestring(nodes_payload))
            )

    def __init__(self,
                 signature: Signature,
                 timestamp_epoch: int,
                 this_node: Optional[NodeMetadata] = None,
                 other_nodes: Optional[List[NodeMetadata]] = None,
                 ):
        self.signature = signature
        self.timestamp_epoch = timestamp_epoch
        self.this_node = this_node
        self.other_nodes = other_nodes

    def verify(self, verifying_pk: PublicKey):
        payload = self._signed_payload(self.timestamp_epoch, self.this_node, self.other_nodes)
        if not self.signature.verify(verifying_pk=verifying_pk, message=payload):
            raise InvalidSignature("Incorrect payload signature for MetadataResponse")

    @classmethod
    def _brand(cls) -> bytes:
        return b'MdRs'

    @classmethod
    def _version(cls) -> Tuple[int, int]:
        return 1, 0

    @classmethod
    def _old_version_handlers(cls) -> Dict:
        return {}

    def _payload(self):
        payload = self._signed_payload(self.timestamp_epoch, self.this_node, self.other_nodes)
        return bytes(self.signature) + payload

    @classmethod
    def _from_bytes_current(cls, data: bytes):

        splitter = BytestringSplitter(
                signature_splitter,
                (int, 4, {'byteorder': 'big'}),
                )

        signature, timestamp_epoch, remainder = splitter(data, return_remainder=True)
        this_node, remainder = take_optional(NodeMetadata.take, remainder)
        maybe_other_nodes, remainder = variable_length_splitter(remainder, return_remainder=True)
        other_nodes = NodeMetadata._batch_from_bytes(maybe_other_nodes) if maybe_other_nodes else None
        obj = cls(signature=signature,
                  timestamp_epoch=timestamp_epoch,
                  this_node=this_node,
                  other_nodes=other_nodes)
        return obj, remainder
