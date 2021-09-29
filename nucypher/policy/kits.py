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


from typing import Dict, Iterable, Set, Union, Tuple

from eth_typing import ChecksumAddress
from eth_utils import to_checksum_address, to_canonical_address

from nucypher.core import MessageKit

from nucypher.crypto.splitters import (
    capsule_splitter,
    checksum_address_splitter,
)
from nucypher.crypto.umbral_adapter import PublicKey, VerifiedCapsuleFrag, Capsule, SecretKey
from nucypher.utilities.versioning import Versioned


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


class PolicyMessageKit:

    @classmethod
    def from_message_kit(cls,
                         message_kit: MessageKit,
                         policy_key: PublicKey,
                         threshold: int
                         ) -> 'PolicyMessageKit':
        return cls(policy_key, threshold, RetrievalResult.empty(), message_kit)

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

    def as_retrieval_kit(self) -> RetrievalKit:
        return RetrievalKit(self.capsule, self._result.addresses())

    def decrypt(self, sk: SecretKey) -> bytes:
        return self.message_kit.decrypt_reencrypted(sk, self.policy_key, self._cfrags)

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


# TODO: a better name?
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
