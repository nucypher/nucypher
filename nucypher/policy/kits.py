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


from typing import Dict, Set, Union

from eth_typing import ChecksumAddress

from nucypher.core import MessageKit, RetrievalKit

from nucypher.crypto.umbral_adapter import PublicKey, VerifiedCapsuleFrag, SecretKey


class PolicyMessageKit:

    @classmethod
    def from_message_kit(cls,
                         message_kit: MessageKit,
                         policy_encrypting_key: PublicKey,
                         threshold: int
                         ) -> 'PolicyMessageKit':
        return cls(policy_encrypting_key, threshold, RetrievalResult.empty(), message_kit)

    def __init__(self,
                 policy_encrypting_key: PublicKey,
                 threshold: int,
                 result: 'RetrievalResult',
                 message_kit: MessageKit,
                 ):
        self.message_kit = message_kit
        self.policy_encrypting_key = policy_encrypting_key
        self.threshold = threshold
        self._result = result

    def as_retrieval_kit(self) -> RetrievalKit:
        return RetrievalKit(self.message_kit.capsule, self._result.addresses())

    def decrypt(self, sk: SecretKey) -> bytes:
        return self.message_kit.decrypt_reencrypted(sk, self.policy_encrypting_key, self._result.cfrags.values())

    def is_decryptable_by_receiver(self) -> bool:
        return len(self._result.cfrags) >= self.threshold

    def with_result(self, result: 'RetrievalResult') -> 'PolicyMessageKit':
        return PolicyMessageKit(policy_encrypting_key=self.policy_encrypting_key,
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
