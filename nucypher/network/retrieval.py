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

from collections import defaultdict
import random
from typing import Dict, Sequence, List, Tuple

from eth_typing.evm import ChecksumAddress
from twisted.logger import Logger

from nucypher.core import (
    TreasureMap,
    ReencryptionResponse,
    ReencryptionRequest,
    RetrievalKit,
    )

from nucypher.crypto.signing import InvalidSignature
from nucypher.crypto.umbral_adapter import (
    Capsule,
    PublicKey,
    VerifiedCapsuleFrag,
    VerificationError,
)
from nucypher.network.exceptions import NodeSeemsToBeDown
from nucypher.network.nodes import Learner
from nucypher.policy.kits import RetrievalResult


class RetrievalPlan:
    """
    An emphemeral object providing a service of selecting Ursulas for reencryption requests
    during retrieval.
    """

    def __init__(self, treasure_map: TreasureMap, retrieval_kits: Sequence[RetrievalKit]):

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


class RetrievalWorkOrder:
    """
    A work order issued by a retrieval plan to request reencryption from an Ursula
    """

    def __init__(self, ursula_address: ChecksumAddress, capsules: List[Capsule]):
        self.ursula_address = ursula_address
        self.capsules = capsules


class RetrievalClient:
    """
    Capsule frag retrieval machinery shared between Bob and Porter.
    """

    def __init__(self, learner: Learner):
        self._learner = learner
        self.log = Logger(self.__class__.__name__)

    def _ensure_ursula_availability(self, treasure_map: TreasureMap, timeout=10):
        """
        Make sure we know enough nodes from the treasure map to decrypt;
        otherwise block and wait for them to come online.
        """

        # OK, so we're going to need to do some network activity for this retrieval.
        # Let's make sure we've seeded.
        if not self._learner.done_seeding:
            self._learner.learn_from_teacher_node()

        ursulas_in_map = treasure_map.destinations.keys()
        all_known_ursulas = self._learner.known_nodes.addresses()

        # Push all unknown Ursulas from the map in the queue for learning
        unknown_ursulas = ursulas_in_map - all_known_ursulas

        # If we know enough to decrypt, we can proceed.
        known_ursulas = ursulas_in_map & all_known_ursulas
        if len(known_ursulas) >= treasure_map.threshold:
            return

        # | <--- shares                                            ---> |
        # | <--- threshold               ---> | <--- allow_missing ---> |
        # | <--- known_ursulas ---> | <--- unknown_ursulas         ---> |
        allow_missing = len(treasure_map.destinations) - treasure_map.threshold
        self._learner.block_until_specific_nodes_are_known(unknown_ursulas,
                                                           timeout=timeout,
                                                           allow_missing=allow_missing,
                                                           learn_on_this_thread=True)

    def _request_reencryption(self,
                              ursula: 'Ursula',
                              reencryption_request: ReencryptionRequest,
                              delegating_key: PublicKey,
                              receiving_key: PublicKey,
                              ) -> Dict['Capsule', 'VerifiedCapsuleFrag']:
        """
        Sends a reencryption request to a single Ursula and processes the results.

        Returns reencrypted capsule frags matched to corresponding capsules.
        """

        middleware = self._learner.network_middleware

        try:
            response = middleware.reencrypt(ursula, bytes(reencryption_request))
        except NodeSeemsToBeDown as e:
            # TODO: What to do here?  Ursula isn't supposed to be down.  NRN
            message = (f"Ursula ({ursula}) seems to be down "
                       f"while trying to complete ReencryptionRequest: {reencryption_request}")
            self.log.info(message)
            raise RuntimeError(message) from e
        except middleware.NotFound as e:
            # This Ursula claims not to have a matching KFrag.  Maybe this has been revoked?
            # TODO: What's the thing to do here?
            # Do we want to track these Ursulas in some way in case they're lying?  #567
            message = (f"Ursula ({ursula}) claims not to not know of the policy {reencryption_request.hrac}. "
                       f"Has access been revoked?")
            self.log.warn(message)
            raise RuntimeError(message) from e
        except middleware.UnexpectedResponse:
            raise # TODO: Handle this

        try:
            reencryption_response = ReencryptionResponse.from_bytes(response.content)
        except Exception as e:
            message = f"Ursula ({ursula}) returned an invalid response: {e}."
            self.log.warn(message)
            raise RuntimeError(message)

        if len(reencryption_request.capsules) != len(reencryption_response.cfrags):
            message = (f"Ursula ({ursula}) gave back the wrong number of cfrags. "
                       "She's up to something.")
            self.log.warn(message)
            raise RuntimeError(message)

        ursula_verifying_key = ursula.stamp.as_umbral_pubkey()
        capsules_bytes = b''.join(bytes(capsule) for capsule in reencryption_request.capsules)
        cfrags_bytes = b''.join(bytes(cfrag) for cfrag in reencryption_response.cfrags)

        # Validate re-encryption signature
        if not reencryption_response.signature.verify(ursula_verifying_key, capsules_bytes + cfrags_bytes):
            message = (f"{reencryption_request.capsules} and {reencryption_response.cfrags} "
                        "are not properly signed by Ursula.")
            self.log.warn(message)
            # TODO: Instead of raising, we should do something (#957)
            raise InvalidSignature(message)

        verified_cfrags = {}

        for capsule, cfrag in zip(reencryption_request.capsules, reencryption_response.cfrags):

            # TODO: should we allow partially valid responses?

            # Verify cfrags
            try:
                verified_cfrag = cfrag.verify(capsule,
                                              verifying_pk=reencryption_request.alice_verifying_key,
                                              delegating_pk=delegating_key,
                                              receiving_pk=receiving_key)
            except VerificationError:
                # In future we may want to remember this Ursula and do something about it
                raise

            verified_cfrags[capsule] = verified_cfrag

        return verified_cfrags

    def retrieve_cfrags(
            self,
            treasure_map: TreasureMap,
            retrieval_kits: Sequence[RetrievalKit],
            alice_verifying_key: PublicKey, # KeyFrag signer's key
            bob_encrypting_key: PublicKey, # User's public key (reencryption target)
            bob_verifying_key: PublicKey,
            ) -> List[RetrievalResult]:

        self._ensure_ursula_availability(treasure_map)

        retrieval_plan = RetrievalPlan(treasure_map=treasure_map, retrieval_kits=retrieval_kits)

        while not retrieval_plan.is_complete():
            # TODO (#2789): Currently we'll only query one Ursula once during the retrieval.
            # Alternatively we may re-query Ursulas that were offline until the timeout expires.

            work_order = retrieval_plan.get_work_order()

            if work_order.ursula_address not in self._learner.known_nodes:
                continue

            ursula = self._learner.known_nodes[work_order.ursula_address]
            reencryption_request = ReencryptionRequest.from_treasure_map(
                ursula_address=work_order.ursula_address,
                capsules=work_order.capsules,
                treasure_map=treasure_map,
                alice_verifying_key=alice_verifying_key,
                bob_verifying_key=bob_verifying_key)

            try:
                cfrags = self._request_reencryption(ursula=ursula,
                                                    reencryption_request=reencryption_request,
                                                    delegating_key=treasure_map.policy_encrypting_key,
                                                    receiving_key=bob_encrypting_key)
            except Exception as e:
                # TODO (#2789): at this point we can separate the exceptions to "acceptable"
                # (Ursula is not reachable) and "unacceptable" (Ursula provided bad results).
                self.log.warn(f"Ursula {ursula} failed to reencrypt: {e}")
                continue

            retrieval_plan.update(work_order, cfrags)

        return retrieval_plan.results()
