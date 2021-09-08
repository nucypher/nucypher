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


from collections import OrderedDict, defaultdict
import random
from typing import Optional, Dict, Sequence, Union, List, Set

import maya
from bytestring_splitter import BytestringSplitter, VariableLengthBytestring
from constant_sorrow.constants import CFRAG_NOT_RETAINED
from eth_typing.evm import ChecksumAddress
from eth_utils.address import to_canonical_address, to_checksum_address

from nucypher.crypto.signing import SignatureStamp, InvalidSignature
from nucypher.crypto.splitters import (
    key_splitter,
    capsule_splitter,
    cfrag_splitter,
    signature_splitter,
    kfrag_splitter
)
from nucypher.crypto.umbral_adapter import (
    Capsule,
    CapsuleFrag,
    PublicKey,
    Signature,
    VerifiedCapsuleFrag,
)
from nucypher.policy.hrac import HRAC, hrac_splitter
from nucypher.policy.kits import MessageKit
from nucypher.policy.maps import AuthorizedKeyFrag, TreasureMap


class RetrievalHistory:
    """
    A cache of retrieved cfrags.
    """

    def __init__(self):
        self._cache_by_capsule: Dict[Capsule, RetrievalResult] = {}

    def update(self, capsule: Capsule, result: 'RetrievalResult'):
        """
        Saves the results of retrieval into the cache.
        """
        self._cache_by_capsule[capsule] = self.by_capsule(capsule).with_result(result)

    def by_capsule(self, capsule: Capsule) -> 'RetrievalResult':
        """
        Returns all the cached retrieval resutls for a given capsule.
        """
        return self._cache_by_capsule.get(capsule, RetrievalResult.empty())


class RetrievalPlan:
    """
    An emphemeral object providing a service of selecting Ursulas for reencryption requests
    during retrieval.
    """

    def __init__(self, treasure_map: TreasureMap, retrieval_kits: Sequence['RetrievalKit']):

        # Record the retrieval kits order
        self._capsules = [retrieval_kit.capsule for retrieval_kit in retrieval_kits]

        self._threshold = treasure_map.threshold

        # Records the retrieval results, indexed by capsule
        self._results = {retrieval_kit.capsule: {}
                         for retrieval_kit in retrieval_kits} # {capsule: {ursula_address: cfrag}}

        # Records the addresses of Ursulas that were already queried, indexed by capsule.
        self._queried_addresses = {retrieval_kit.capsule: set(retrieval_kit.queried_addresses)
                                   for retrieval_kit in retrieval_kits}

        # Records the capsules already processed by a corresponding Ursula.
        # An inverse of `_queried_addresses`.
        self._processed_capsules = defaultdict(set) # {ursula_address: {capsule}}
        for retrieval_kit in retrieval_kits:
            for address in retrieval_kit.queried_addresses:
                self._processed_capsules[address].add(retrieval_kit.capsule)

        # If we've already retrieved from some addresses before, query them last.
        # In other words, we try to get the maximum amount of cfrags in our first queries,
        # to use the time more efficiently.
        ursulas_to_contact_last = set()
        for queried_addresses in self._queried_addresses.values():
            ursulas_to_contact_last |= queried_addresses

        # Randomize Ursulas' priorities
        ursulas_pick_order = list(treasure_map.destinations) # checksum addresses
        random.shuffle(ursulas_pick_order) # mutates list in-place

        ursulas_pick_order = [ursula for ursula in ursulas_pick_order
                              if ursula not in ursulas_to_contact_last]
        self._ursulas_pick_order = ursulas_pick_order + list(ursulas_to_contact_last)

    def get_work_order(self) -> 'RetrievalWorkOrder':
        """
        Returns a new retrieval work order based on the current plan state.
        """
        while self._ursulas_pick_order:
            ursula_address = self._ursulas_pick_order.pop(0)
            # Only request reencryption for capsules that:
            # - haven't been processed by this Ursula
            # - don't already have cfrags from `threshold` Ursulas
            capsules = [capsule for capsule in self._capsules
                        if (capsule not in self._processed_capsules.get(ursula_address, set())
                            and len(self._queried_addresses[capsule]) < self._threshold)]
            if len(capsules) > 0:
                return RetrievalWorkOrder(ursula_address=ursula_address,
                                          capsules=capsules)

        # Execution will not reach this point if `is_complete()` returned `False` before this call.
        raise RuntimeError("No Ursulas left")

    def update(self, work_order: 'RetrievalWorkOrder', cfrags: Dict[Capsule, VerifiedCapsuleFrag]):
        """
        Updates the plan state, recording the cfrags obtained for capsules during a query.
        """
        for capsule, cfrag in cfrags.items():
            self._queried_addresses[capsule].add(work_order.ursula_address)
            self._processed_capsules[work_order.ursula_address].add(capsule)
            self._results[capsule][work_order.ursula_address] = cfrag

    def is_complete(self) -> bool:
        return (
            # there are no more Ursulas to query
            not bool(self._ursulas_pick_order) or
            # all the capsules have enough cfrags for decryption
            all(len(addresses) >= self._threshold for addresses in self._queried_addresses.values())
            )

    def results(self) -> List['RetrievalResult']:
        return [RetrievalResult(self._results[capsule]) for capsule in self._capsules]


class RetrievalResult:
    """
    An object representing retrieval results for a single capsule.
    """

    @classmethod
    def empty(cls):
        return cls({})

    def __init__(self, cfrags: Dict[ChecksumAddress, VerifiedCapsuleFrag]):
        self.cfrags = cfrags

    def addresses(self) -> Set[ChecksumAddress]:
        return set(self.cfrags)

    def with_result(self, result: 'RetrievalResult') -> 'RetrievalResult':
        """
        Joins two RetrievalResult objects.

        If both objects contain cfrags from the same Ursula,
        the one from `result` will be kept.
        """
        # TODO: would `+` or `|` operator be more suitable here?

        # TODO: check for overlap?
        new_cfrags = dict(self.cfrags)
        new_cfrags.update(result.cfrags)
        return RetrievalResult(cfrags=new_cfrags)


class RetrievalWorkOrder:
    """
    A work order issued by a retrieval plan to request reencryption from an Ursula
    """

    def __init__(self, ursula_address: ChecksumAddress, capsules: List[Capsule]):
        self.ursula_address = ursula_address
        self.capsules = capsules


class ReencryptionRequest:
    """
    A request for an Ursula to reencrypt for several capsules.
    """

    _splitter = (hrac_splitter +
                 key_splitter +
                 key_splitter +
                 key_splitter +
                 BytestringSplitter((bytes, VariableLengthBytestring)))

    @classmethod
    def from_work_order(cls,
                        work_order: RetrievalWorkOrder,
                        treasure_map: TreasureMap,
                        alice_verifying_key: PublicKey,
                        bob_verifying_key: PublicKey,
                        publisher_verifying_key: PublicKey,
                        ) -> 'ReencryptionRequest':
        return cls(hrac=treasure_map.hrac,
                   alice_verifying_key=alice_verifying_key,
                   bob_verifying_key=bob_verifying_key,
                   publisher_verifying_key=publisher_verifying_key,
                   encrypted_kfrag=treasure_map.destinations[work_order.ursula_address],
                   capsules=work_order.capsules,
                   )

    def __init__(self,
                 hrac: HRAC,
                 alice_verifying_key: PublicKey,
                 bob_verifying_key: PublicKey,
                 publisher_verifying_key: PublicKey,
                 encrypted_kfrag: bytes,
                 capsules: List[Capsule]):

        self.hrac = hrac
        self._alice_verifying_key = alice_verifying_key
        self._bob_verifying_key = bob_verifying_key
        self._publisher_verifying_key = publisher_verifying_key
        self.encrypted_kfrag = encrypted_kfrag
        self.capsules = capsules

    def __bytes__(self):
        return (bytes(self.hrac) +
                bytes(self._alice_verifying_key) +
                bytes(self._bob_verifying_key) +
                bytes(self._publisher_verifying_key) +
                VariableLengthBytestring(self.encrypted_kfrag) +
                b''.join(bytes(capsule) for capsule in self.capsules)
                )

    @classmethod
    def from_bytes(cls, data: bytes):
        hrac, alice_vk, bob_vk, publisher_vk, ekfrag, remainder = cls._splitter(data, return_remainder=True)
        capsules = capsule_splitter.repeat(remainder)
        return cls(hrac, alice_vk, bob_vk, publisher_vk, ekfrag, capsules)

    def alice(self) -> 'Alice':
        from nucypher.characters.lawful import Alice
        return Alice.from_public_keys(verifying_key=self._alice_verifying_key)

    def bob(self) -> 'Bob':
        from nucypher.characters.lawful import Bob
        return Bob.from_public_keys(verifying_key=self._bob_verifying_key)

    def publisher(self) -> 'Alice':
        from nucypher.characters.lawful import Alice
        return Alice.from_public_keys(verifying_key=self._publisher_verifying_key)


class ReencryptionResponse:
    """
    A response from Ursula with reencrypted capsule frags.
    """

    @classmethod
    def construct_by_ursula(cls,
                            capsules: List[Capsule],
                            cfrags: List[VerifiedCapsuleFrag],
                            stamp: SignatureStamp,
                            ) -> 'ReencryptionResponse':

        # un-verify
        cfrags = [CapsuleFrag.from_bytes(bytes(cfrag)) for cfrag in cfrags]

        capsules_bytes = b''.join(bytes(capsule) for capsule in capsules)
        cfrags_bytes = b''.join(bytes(cfrag) for cfrag in cfrags)
        signature = stamp(capsules_bytes + cfrags_bytes)
        return cls(cfrags, signature)

    def __init__(self, cfrags: List[CapsuleFrag], signature: Signature):
        self.cfrags = cfrags
        self.signature = signature

    @classmethod
    def from_bytes(cls, data: bytes):
        signature, cfrags_bytes = signature_splitter(data, return_remainder=True)
        cfrags = cfrag_splitter.repeat(cfrags_bytes)
        return cls(cfrags, signature)

    def __bytes__(self):
        return bytes(self.signature) + b''.join(bytes(cfrag) for cfrag in self.cfrags)



class Revocation:
    """
    Represents a string used by characters to perform a revocation on a specific
    Ursula. It's a bytestring made of the following format:
    REVOKE-<arrangement id to revoke><signature of the previous string>
    This is sent as a payload in a DELETE method to the /KFrag/ endpoint.
    """

    PREFIX = b'REVOKE-'
    revocation_splitter = BytestringSplitter(
        (bytes, len(PREFIX)),
        (bytes, 20),   # ursula canonical address
        (bytes, AuthorizedKeyFrag.ENCRYPTED_SIZE),  # encrypted kfrag payload (includes writ)
        signature_splitter
    )

    def __init__(self,
                 ursula_checksum_address: ChecksumAddress,  # TODO: Use staker address instead (what if the staker rebonds)?
                 encrypted_kfrag: bytes,
                 signer: 'SignatureStamp' = None,
                 signature: Signature = None):

        self.ursula_checksum_address = ursula_checksum_address
        self.encrypted_kfrag = encrypted_kfrag

        if not (bool(signer) ^ bool(signature)):
            raise ValueError("Either pass a signer or a signature; not both.")
        elif signer:
            self.signature = signer(self.payload)
        elif signature:
            self.signature = signature

    def __bytes__(self):
        return self.payload + bytes(self.signature)

    def __repr__(self):
        return bytes(self)

    def __len__(self):
        return len(bytes(self))

    def __eq__(self, other):
        return bytes(self) == bytes(other)

    @property
    def payload(self):
        return self.PREFIX                                          \
               + to_canonical_address(self.ursula_checksum_address) \
               + bytes(self.encrypted_kfrag)                        \

    @classmethod
    def from_bytes(cls, revocation_bytes):
        prefix, ursula_canonical_address, ekfrag, signature = cls.revocation_splitter(revocation_bytes)
        ursula_checksum_address = to_checksum_address(ursula_canonical_address)
        return cls(ursula_checksum_address=ursula_checksum_address,
                   encrypted_kfrag=ekfrag,
                   signature=signature)

    def verify_signature(self, alice_verifying_key: 'PublicKey') -> bool:
        """
        Verifies the revocation was from the provided pubkey.
        """
        if not self.signature.verify(self.payload, alice_verifying_key):
            raise InvalidSignature(f"Revocation has an invalid signature: {self.signature}")
        return True
