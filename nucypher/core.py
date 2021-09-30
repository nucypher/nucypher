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

from typing import Optional, Sequence, Callable, Dict, Tuple, List, Iterable

from bytestring_splitter import (
    BytestringSplitter,
    VariableLengthBytestring,
    BytestringSplittingError,
)
from eth_typing.evm import ChecksumAddress
from eth_utils.address import to_checksum_address, to_canonical_address

from nucypher.utilities.versioning import Versioned

from nucypher.crypto.utils import keccak_digest
from nucypher.crypto.splitters import (
    signature_splitter,
    capsule_splitter,
    key_splitter,
    kfrag_splitter,
    cfrag_splitter,
    checksum_address_splitter,
    )
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


class TreasureMap(Versioned):

    def __init__(self,
                 threshold: int,
                 hrac: HRAC,
                 destinations: Dict[ChecksumAddress, MessageKit]):
        self.threshold = threshold
        self.destinations = destinations
        self.hrac = hrac

        # A little awkward, but saves us a key length in serialization
        self.publisher_verifying_key = list(destinations.values())[0].sender_verifying_key

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
                               hrac: HRAC,
                               signer: Signer,
                               # TODO: a better way to do it? A structure/namedtuple perhaps?
                               assigned_kfrags: Sequence[Tuple[ChecksumAddress, PublicKey, VerifiedKeyFrag]],
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
        for ursula_address, ursula_key, verified_kfrag in assigned_kfrags:
            # TODO: do we really need to sign the AuthorizedKeyFrag *and* the plaintext afterwards?
            kfrag_payload = bytes(AuthorizedKeyFrag.construct_by_publisher(hrac=hrac,
                                                                           verified_kfrag=verified_kfrag,
                                                                           signer=signer))
            encrypted_kfrag = MessageKit.author(recipient_key=ursula_key,
                                                plaintext=kfrag_payload,
                                                signer=signer)

            destinations[ursula_address] = encrypted_kfrag

        return cls(threshold=threshold, hrac=hrac, destinations=destinations)

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
        return self.threshold.to_bytes(1, "big") + bytes(self.hrac) + self._nodes_as_bytes()

    @classmethod
    def _from_bytes_current(cls, data):

        main_splitter = BytestringSplitter(
            (int, 1, {'byteorder': 'big'}),
            hrac_splitter,
        )

        ursula_and_kfrag_payload_splitter = BytestringSplitter(
            (to_checksum_address, ETH_ADDRESS_BYTE_LENGTH),
            (MessageKit, VariableLengthBytestring),
        )

        try:
            threshold, hrac, remainder = main_splitter(data, return_remainder=True)
            ursula_and_kfrags = ursula_and_kfrag_payload_splitter.repeat(remainder)
        except BytestringSplittingError as e:
            raise ValueError('Invalid treasure map contents.') from e
        destinations = {u: k for u, k in ursula_and_kfrags}
        return cls(threshold, hrac, destinations)

    def encrypt(self,
                signer: Signer,
                recipient_key: PublicKey,
                ) -> 'EncryptedTreasureMap':
        return EncryptedTreasureMap.construct_by_publisher(treasure_map=self,
                                                           signer=signer,
                                                           recipient_key=recipient_key)

    def _nodes_as_bytes(self) -> bytes:
        nodes_as_bytes = b""
        for ursula_address, encrypted_kfrag in self.destinations.items():
            node_id = to_canonical_address(ursula_address)
            kfrag = bytes(VariableLengthBytestring(bytes(encrypted_kfrag)))
            nodes_as_bytes += (node_id + kfrag)
        return nodes_as_bytes


class EncryptedTreasureMap(Versioned):

    def __init__(self,
                 hrac: HRAC,
                 public_signature: Signature,
                 encrypted_tmap: MessageKit,
                 ):

        self.hrac = hrac
        self._public_signature = public_signature
        self.publisher_verifying_key = encrypted_tmap.sender_verifying_key
        self._encrypted_tmap = encrypted_tmap

    @classmethod
    def construct_by_publisher(cls,
                               recipient_key: PublicKey,
                               treasure_map: TreasureMap,
                               signer: Signer,
                               ) -> 'EncryptedTreasureMap':
        # TODO: `signer` here can be different from the one in TreasureMap, it seems.
        # Do we ever cross-check them? Do we want to enforce them to be the same?
        encrypted_tmap = MessageKit.author(recipient_key=recipient_key,
                                           plaintext=bytes(treasure_map),
                                           signer=signer)

        # TODO: what does `public_signature` achieve if we already have the map signed in
        # `encrypted_tmap`?
        public_signature = signer.sign(bytes(signer.verifying_key()) + bytes(treasure_map.hrac))

        return cls(treasure_map.hrac, public_signature, encrypted_tmap)

    def decrypt(self, decryptor: Callable[[MessageKit], bytes]) -> TreasureMap:
        """
        When Bob receives the TreasureMap, he'll pass a decryptor (a callable which can verify and decrypt the
        payload message kit).
        """
        try:
            map_in_the_clear = decryptor(self._encrypted_tmap)
        except InvalidSignature as e:
            raise InvalidSignature("This TreasureMap does not contain the correct signature "
                                   "from the publisher to Bob.") from e

        return TreasureMap.from_bytes(map_in_the_clear)

    def _public_verify(self):
        message = bytes(self.publisher_verifying_key) + bytes(self.hrac)
        if not self._public_signature.verify(self.publisher_verifying_key, message=message):
            raise InvalidSignature("This TreasureMap is not properly publicly signed by the publisher.")

    def _payload(self) -> bytes:
        return (bytes(self._public_signature) +
                bytes(self.hrac) +
                bytes(VariableLengthBytestring(bytes(self._encrypted_tmap)))
                )

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

        splitter = BytestringSplitter(
            signature_splitter,  # public signature
            hrac_splitter,  # HRAC
            (MessageKit, VariableLengthBytestring),  # encrypted TreasureMap
            )

        try:
            public_signature, hrac, message_kit = splitter(data)
        except BytestringSplittingError as e:
            raise ValueError('Invalid encrypted treasure map contents.') from e

        result = cls(hrac, public_signature, message_kit)
        result._public_verify()
        return result

    def __eq__(self, other):
        return bytes(self) == bytes(other)


class ReencryptionRequest(Versioned):
    """
    A request for an Ursula to reencrypt for several capsules.
    """

    @classmethod
    def from_treasure_map(cls,
                          ursula_address: ChecksumAddress,
                          capsules: Sequence[Capsule],
                          treasure_map: TreasureMap,
                          alice_verifying_key: PublicKey,
                          bob_verifying_key: PublicKey,
                          ) -> 'ReencryptionRequest':
        return cls(hrac=treasure_map.hrac,
                   alice_verifying_key=alice_verifying_key,
                   bob_verifying_key=bob_verifying_key,
                   encrypted_kfrag=treasure_map.destinations[ursula_address],
                   capsules=capsules,
                   )

    def __init__(self,
                 hrac: HRAC,
                 alice_verifying_key: PublicKey,
                 bob_verifying_key: PublicKey,
                 encrypted_kfrag: MessageKit,
                 capsules: List[Capsule]):

        self.hrac = hrac
        self.alice_verifying_key = alice_verifying_key
        self.publisher_verifying_key = encrypted_kfrag.sender_verifying_key
        self.bob_verifying_key = bob_verifying_key
        self.encrypted_kfrag = encrypted_kfrag
        self.capsules = capsules

    def _payload(self) -> bytes:
        return (bytes(self.hrac) +
                bytes(self.alice_verifying_key) +
                bytes(self.bob_verifying_key) +
                VariableLengthBytestring(bytes(self.encrypted_kfrag)) +
                b''.join(bytes(capsule) for capsule in self.capsules)
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
                    key_splitter +
                    BytestringSplitter((MessageKit, VariableLengthBytestring)))

        hrac, alice_vk, bob_vk, ekfrag, remainder = splitter(data, return_remainder=True)
        capsules = capsule_splitter.repeat(remainder)
        return cls(hrac, alice_vk, bob_vk, ekfrag, capsules)


class ReencryptionResponse(Versioned):
    """
    A response from Ursula with reencrypted capsule frags.
    """

    @classmethod
    def construct_by_ursula(cls,
                            capsules: List[Capsule],
                            cfrags: List[VerifiedCapsuleFrag],
                            signer: Signer,
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
        return bytes(self.signature) + b''.join(bytes(cfrag) for cfrag in self.cfrags)

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
        signature, cfrags_bytes = signature_splitter(data, return_remainder=True)

        # We would never send a request with no capsules, so there should be cfrags.
        # The splitter would fail anyway, this just makes the error message more clear.
        if not cfrags_bytes:
            raise ValueError(f"{cls.__name__} contains no cfrags")

        cfrags = cfrag_splitter.repeat(cfrags_bytes)
        return cls(cfrags, signature)


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
                b''.join(to_canonical_address(address) for address in self.queried_addresses))

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
        capsule, remainder = capsule_splitter(data, return_remainder=True)
        if remainder:
            addresses_as_bytes = checksum_address_splitter.repeat(remainder)
        else:
            addresses_as_bytes = ()
        return cls(capsule, set(to_checksum_address(address) for address in addresses_as_bytes))


class Arrangement(Versioned):
    """A contract between Alice and a single Ursula."""

    def __init__(self, publisher_verifying_key: PublicKey, expiration_epoch: int):
        self.expiration_epoch = expiration_epoch
        self.publisher_verifying_key = publisher_verifying_key

    def __repr__(self):
        return f"Arrangement(publisher={self.publisher_verifying_key})"

    @classmethod
    def _brand(cls) -> bytes:
        return b'Arng'

    @classmethod
    def _version(cls) -> Tuple[int, int]:
        return 1, 0

    def _payload(self) -> bytes:
        """Returns the unversioned bytes serialized representation of this instance."""
        return bytes(self.publisher_verifying_key) + self.expiration_epoch.to_bytes(4, 'big')

    @classmethod
    def _old_version_handlers(cls) -> Dict:
        return {}

    @classmethod
    def _from_bytes_current(cls, data: bytes):
        splitter = BytestringSplitter(
            key_splitter,  # publisher_verifying_key
            (int, 4, {'byteorder': 'big'})  # expiration
        )
        publisher_verifying_key, expiration_epoch = splitter(data)
        return cls(publisher_verifying_key=publisher_verifying_key, expiration_epoch=expiration_epoch)


class ArrangementResponse(Versioned):
    """Ursula's response to an Arrangement."""

    @classmethod
    def for_arrangement(cls, arrangement: Arrangement, signer: Signer):
        return cls(signer.sign(bytes(arrangement)))

    def __init__(self, signature: Signature):
        self.signature = signature

    @classmethod
    def _brand(cls) -> bytes:
        return b'ArRs'

    @classmethod
    def _version(cls) -> Tuple[int, int]:
        return 1, 0

    def _payload(self) -> bytes:
        """Returns the unversioned bytes serialized representation of this instance."""
        return bytes(self.signature)

    @classmethod
    def _old_version_handlers(cls) -> Dict:
        return {}

    @classmethod
    def _from_bytes_current(cls, data: bytes):
        signature, = signature_splitter(data)
        return cls(signature=signature)
