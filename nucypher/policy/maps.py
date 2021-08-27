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


from typing import Optional, Callable, Union, Sequence, Dict

from bytestring_splitter import (
    BytestringSplitter,
    VariableLengthBytestring,
    BytestringSplittingError,
)
from constant_sorrow.constants import NO_DECRYPTION_PERFORMED, NOT_SIGNED
from eth_utils.address import to_checksum_address, to_canonical_address
from eth_typing.evm import ChecksumAddress

from nucypher.blockchain.eth.constants import ETH_ADDRESS_BYTE_LENGTH
from nucypher.characters.base import Character
from nucypher.crypto.constants import EIP712_MESSAGE_SIGNATURE_SIZE
from nucypher.crypto.kits import UmbralMessageKit
from nucypher.crypto.powers import DecryptingPower, SigningPower
from nucypher.crypto.signing import SignatureStamp
from nucypher.crypto.splitters import signature_splitter, kfrag_splitter
from nucypher.crypto.umbral_adapter import KeyFrag, VerifiedKeyFrag, PublicKey, Signature
from nucypher.crypto.utils import keccak_digest, encrypt_and_sign, verify_eip_191
from nucypher.network.middleware import RestMiddleware
from nucypher.policy.hrac import HRAC, hrac_splitter


class TreasureMap:

    class NowhereToBeFound(RestMiddleware.NotFound):
        """
        Called when no known nodes have it.
        """

    main_splitter = BytestringSplitter(
        (int, 1, {'byteorder': 'big'}),
        hrac_splitter,
    )

    ursula_and_kfrag_payload_splitter = BytestringSplitter(
        (to_checksum_address, ETH_ADDRESS_BYTE_LENGTH),
        (UmbralMessageKit, VariableLengthBytestring),
    )

    @classmethod
    def construct_by_publisher(cls,
                               hrac: HRAC,
                               publisher: 'Alice',
                               ursulas: Sequence['Ursula'],
                               verified_kfrags: Sequence[VerifiedKeyFrag],
                               threshold: int,
                               ) -> 'TreasureMap':
        """Create a new treasure map for a collection of ursulas and kfrags."""

        if threshold < 1 or threshold > 255:
            raise ValueError("The threshold must be between 1 and 255.")

        if len(ursulas) < threshold:
            raise ValueError(
                f"The number of destinations ({len(ursulas)}) "
                f"must be equal or greater than the threshold ({threshold})")

        # Encrypt each kfrag for an Ursula.
        destinations = {}
        for ursula, verified_kfrag in zip(ursulas, verified_kfrags):
            kfrag_payload = bytes(AuthorizedKeyFrag.construct_by_publisher(hrac=hrac,
                                                                           verified_kfrag=verified_kfrag,
                                                                           publisher_stamp=publisher.stamp))
            encrypted_kfrag, _signature = encrypt_and_sign(recipient_pubkey_enc=ursula.public_keys(DecryptingPower),
                                                           plaintext=kfrag_payload,
                                                           signer=publisher.stamp)

            destinations[ursula.checksum_address] = encrypted_kfrag

        return cls(threshold=threshold, hrac=hrac, destinations=destinations)

    def __init__(self,
                 threshold: int,
                 hrac: HRAC,
                 destinations: Dict[ChecksumAddress, bytes],
                 ):
        self.threshold = threshold
        self.destinations = destinations
        self.hrac = hrac

    def encrypt(self,
                publisher: 'Alice',
                bob: 'Bob',
                blockchain_signer: Optional[Callable[[bytes], bytes]] = None,
                ) -> 'EncryptedTreasureMap':
        return EncryptedTreasureMap.construct_by_publisher(treasure_map=self,
                                                           publisher=publisher,
                                                           bob=bob,
                                                           blockchain_signer=blockchain_signer)

    def _nodes_as_bytes(self) -> bytes:
        nodes_as_bytes = b""
        for ursula_address, encrypted_kfrag in self.destinations.items():
            node_id = to_canonical_address(ursula_address)
            kfrag = bytes(VariableLengthBytestring(encrypted_kfrag.to_bytes()))
            nodes_as_bytes += (node_id + kfrag)
        return nodes_as_bytes

    def __bytes__(self):
        return self.threshold.to_bytes(1, "big") + bytes(self.hrac) + self._nodes_as_bytes()

    @classmethod
    def from_bytes(cls, data: bytes):
        try:
            threshold, hrac, remainder = cls.main_splitter(data, return_remainder=True)
            ursula_and_kfrags = cls.ursula_and_kfrag_payload_splitter.repeat(remainder)
        except BytestringSplittingError as e:
            raise ValueError('Invalid treasure map contents.') from e
        destinations = {u: k for u, k in ursula_and_kfrags}
        return cls(threshold, hrac, destinations)

    def __iter__(self):
        return iter(self.destinations.items())

    def __len__(self):
        return len(self.destinations)


class AuthorizedKeyFrag:

    _WRIT_CHECKSUM_SIZE = 32

    # The size of a serialized message kit encrypting an AuthorizedKeyFrag.
    # Depends on encryption parameters in Umbral, has to be hardcoded.
    ENCRYPTED_SIZE = 619

    _splitter = BytestringSplitter(
        hrac_splitter, # HRAC
        (bytes, _WRIT_CHECKSUM_SIZE), # kfrag checksum
        signature_splitter, # Publisher's signature
        kfrag_splitter,
        )

    @staticmethod
    def _kfrag_checksum(kfrag: KeyFrag) -> bytes:
        return keccak_digest(bytes(kfrag))[:AuthorizedKeyFrag._WRIT_CHECKSUM_SIZE]

    @classmethod
    def construct_by_publisher(cls,
                               hrac: HRAC,
                               verified_kfrag: VerifiedKeyFrag,
                               publisher_stamp: SignatureStamp,
                               ) -> 'AuthorizedKeyFrag':

        # "un-verify" kfrag to keep further logic streamlined
        kfrag = KeyFrag.from_bytes(bytes(verified_kfrag))

        # Alice makes plain to Ursula that, upon decrypting this message,
        # this particular KFrag is authorized for use in the policy identified by this HRAC.
        kfrag_checksum = cls._kfrag_checksum(kfrag)
        writ = bytes(hrac) + kfrag_checksum
        writ_signature = publisher_stamp(writ)

        # The writ and the KFrag together represent a complete kfrag kit: the entirety of
        # the material needed for Ursula to assuredly service this policy.
        return cls(hrac, kfrag_checksum, writ_signature, kfrag)

    def __init__(self, hrac: HRAC, kfrag_checksum: bytes, writ_signature: Signature, kfrag: KeyFrag):
        self.hrac = hrac
        self.kfrag_checksum = kfrag_checksum
        self.writ = bytes(hrac) + kfrag_checksum
        self.writ_signature = writ_signature
        self.kfrag = kfrag

    def __bytes__(self):
        return self.writ + bytes(self.writ_signature) + bytes(self.kfrag)

    @classmethod
    def from_bytes(cls, data: bytes):
        # TODO: should we check the signature right away here?
        hrac, kfrag_checksum, writ_signature, kfrag = cls._splitter(data)

        # Check integrity
        calculated_checksum = cls._kfrag_checksum(kfrag)
        if calculated_checksum != kfrag_checksum:
            raise ValueError("Incorrect KeyFrag checksum in the serialized data")

        return cls(hrac, kfrag_checksum, writ_signature, kfrag)


class EncryptedTreasureMap:

    _splitter = BytestringSplitter(
        signature_splitter, # public signature
        hrac_splitter, # HRAC
        (UmbralMessageKit, VariableLengthBytestring), # encrypted TreasureMap
        (bytes, EIP712_MESSAGE_SIGNATURE_SIZE)) # blockchain signature

    _EMPTY_BLOCKCHAIN_SIGNATURE = b'\x00' * EIP712_MESSAGE_SIGNATURE_SIZE

    from nucypher.crypto.signing import \
        InvalidSignature  # Raised when the public signature (typically intended for Ursula) is not valid.

    @staticmethod
    def _sign(blockchain_signer: Callable[[bytes], bytes],
              public_signature: Signature,
              hrac: HRAC,
              encrypted_tmap: UmbralMessageKit,
              ) -> bytes:
        # This method exists mainly to link this scheme to the corresponding test
        payload = bytes(public_signature) + bytes(hrac) + encrypted_tmap.to_bytes()
        return blockchain_signer(payload)

    @classmethod
    def construct_by_publisher(cls,
                               treasure_map: TreasureMap,
                               publisher: 'Alice',
                               bob: 'Bob',
                               blockchain_signer: Optional[Callable[[bytes], bytes]] = None,
                               ) -> 'EncryptedTreasureMap':
        # TODO: `publisher` here can be different from the one in TreasureMap, it seems.
        # Do we ever cross-check them? Do we want to enforce them to be the same?

        bob_encrypting_key = bob.public_keys(DecryptingPower)

        encrypted_tmap, _signature_for_bob = encrypt_and_sign(bob_encrypting_key,
                                                              plaintext=bytes(treasure_map),
                                                              signer=publisher.stamp)
        public_signature = publisher.stamp(bytes(publisher.stamp) + bytes(treasure_map.hrac))

        if blockchain_signer is not None:
            blockchain_signature = EncryptedTreasureMap._sign(blockchain_signer=blockchain_signer,
                                                              public_signature=public_signature,
                                                              hrac=treasure_map.hrac,
                                                              encrypted_tmap=encrypted_tmap)
        else:
            blockchain_signature = None

        return cls(treasure_map.hrac, public_signature, encrypted_tmap, blockchain_signature=blockchain_signature)

    def __init__(self,
                 hrac: HRAC,
                 public_signature: Signature,
                 encrypted_tmap: UmbralMessageKit,
                 blockchain_signature: Optional[bytes] = None,
                 ):

        self.hrac = hrac
        self._public_signature = public_signature
        self._verifying_key = encrypted_tmap.sender_verifying_key
        self._encrypted_tmap = encrypted_tmap
        self._blockchain_signature = blockchain_signature

    def decrypt(self, decryptor: Callable[[bytes], bytes]) -> TreasureMap:
        """
        When Bob receives the TreasureMap, he'll pass a decryptor (a callable which can verify and decrypt the
        payload message kit).
        """
        try:
            map_in_the_clear = decryptor(self._encrypted_tmap)
        except Character.InvalidSignature:
            raise self.InvalidSignature("This TreasureMap does not contain the correct signature "
                                        "from the publisher to Bob.")

        return TreasureMap.from_bytes(map_in_the_clear)

    def __bytes__(self):
        if self._blockchain_signature:
            signature = self._blockchain_signature
        else:
            signature = self._EMPTY_BLOCKCHAIN_SIGNATURE
        return (bytes(self._public_signature) +
                bytes(self.hrac) +
                bytes(VariableLengthBytestring(self._encrypted_tmap.to_bytes())) +
                signature
                )

    def verify_blockchain_signature(self, checksum_address: ChecksumAddress) -> bool:
        if self._blockchain_signature is None:
            raise ValueError("This EncryptedTreasureMap is not blockchain-signed")
        payload = bytes(self._public_signature) + bytes(self.hrac) + self._encrypted_tmap.to_bytes()
        return verify_eip_191(message=payload,
                              signature=self._blockchain_signature,
                              address=checksum_address)

    def _public_verify(self):
        message = bytes(self._verifying_key) + bytes(self.hrac)
        if not self._public_signature.verify(self._verifying_key, message=message):
            raise self.InvalidSignature("This TreasureMap is not properly publicly signed by Alice.")

    @classmethod
    def from_bytes(cls, data: bytes):
        try:
            public_signature, hrac, message_kit, blockchain_signature = cls._splitter(data)
            if blockchain_signature == cls._EMPTY_BLOCKCHAIN_SIGNATURE:
                blockchain_signature = None
        except BytestringSplittingError as e:
            raise ValueError('Invalid encrypted treasure map contents.') from e

        result = cls(hrac, public_signature, message_kit, blockchain_signature=blockchain_signature)
        result._public_verify()
        return result
