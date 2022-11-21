from typing import Dict, Set

from eth_typing import ChecksumAddress
from eth_utils import to_canonical_address
from nucypher_core import Address, Conditions, MessageKit, RetrievalKit
from nucypher_core.umbral import PublicKey, SecretKey, VerifiedCapsuleFrag


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
        return RetrievalKit(
            capsule=self.message_kit.capsule,
            queried_addresses=self._result.canonical_addresses(),
            conditions=self.message_kit.conditions,
        )

    def decrypt(self, sk: SecretKey) -> bytes:
        return self.message_kit.decrypt_reencrypted(sk,
                                                    self.policy_encrypting_key,
                                                    list(self._result.cfrags.values()))

    def is_decryptable_by_receiver(self) -> bool:
        return len(self._result.cfrags) >= self.threshold

    def with_result(self, result: 'RetrievalResult') -> 'PolicyMessageKit':
        return PolicyMessageKit(policy_encrypting_key=self.policy_encrypting_key,
                                threshold=self.threshold,
                                result=self._result.with_result(result),
                                message_kit=self.message_kit)

    @property
    def conditions(self) -> Conditions:
        return self.message_kit.conditions


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

    def canonical_addresses(self) -> Set[Address]:
        # TODO (#1995): propagate this to use canonical addresses everywhere
        return set([Address(to_canonical_address(address)) for address in self.cfrags])

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
