
import json
import random
from collections import defaultdict
from typing import Dict, List, Sequence, Tuple

from eth_typing.evm import ChecksumAddress
from eth_utils import to_checksum_address
from nucypher_core import (
    Address,
    Conditions,
    Context,
    ReencryptionRequest,
    ReencryptionResponse,
    RetrievalKit,
    TreasureMap,
)
from nucypher_core.umbral import (
    Capsule,
    PublicKey,
    VerificationError,
    VerifiedCapsuleFrag,
)

from nucypher.characters import lawful
from nucypher.crypto.signing import InvalidSignature
from nucypher.network.client import ThresholdAccessControlClient
from nucypher.network.exceptions import NodeSeemsToBeDown
from nucypher.policy.conditions.exceptions import InvalidConditionContext
from nucypher.policy.kits import RetrievalResult


class RetrievalError:
    def __init__(self, errors: Dict[ChecksumAddress, str]):
        self.errors = errors


class RetrievalPlan:
    """
    An ephemeral object providing a service of selecting Ursulas for re-encryption requests
    during retrieval.
    """

    def __init__(self, treasure_map: TreasureMap, retrieval_kits: Sequence[RetrievalKit]):

        self._retrieval_kits = retrieval_kits
        self._threshold = treasure_map.threshold

        # Records the retrieval results, indexed by capsule
        self._results = {
            rk.capsule: {} for rk in retrieval_kits
        }  # {capsule: {ursula_address: cfrag}}

        # Records the retrieval result errors, indexed by capsule
        self._errors = {
            retrieval_kit.capsule: {} for retrieval_kit in retrieval_kits
        }  # {capsule: {ursula_address: error}}

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
            retrieval_kits: List[RetrievalKit] = list()
            for rk in self._retrieval_kits:
                # Only request reencryption for capsules that:
                # - haven't been processed by this Ursula
                processed = rk.capsule in self._processed_capsules.get(ursula_address, set())
                # - don't already have cfrags from `threshold` Ursulas
                enough = len(self._queried_addresses[rk.capsule]) >= self._threshold
                if (not processed) and (not enough):
                    retrieval_kits.append(rk)

            if len(retrieval_kits) > 0:
                return RetrievalWorkOrder(ursula_address=ursula_address, retrieval_kits=retrieval_kits)

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

    def update_errors(self,
                      work_order: "RetrievalWorkOrder",
                      ursula_address: ChecksumAddress,
                      error_message: str):
        for capsule in work_order.capsules:
            self._errors[capsule][ursula_address] = error_message

    def is_complete(self) -> bool:
        return (
            # there are no more Ursulas to query
            not bool(self._ursulas_pick_order) or
            # all the capsules have enough cfrags for decryption
            all(len(addresses) >= self._threshold for addresses in self._queried_addresses.values())
            )

    def results(self) -> Tuple[List["RetrievalResult"], List[RetrievalError]]:
        results = []
        errors = []
        # maintain the same order with both lists
        for rk in self._retrieval_kits:
            results.append(
                RetrievalResult(
                    {
                        to_checksum_address(bytes(address)): cfrag
                        for address, cfrag in self._results[rk.capsule].items()
                    }
                )
            )
            errors.append(RetrievalError(errors=self._errors[rk.capsule]))

        return results, errors


class RetrievalWorkOrder:
    """A work order issued by a retrieval plan to request reencryption from an Ursula"""

    def __init__(self, ursula_address: Address, retrieval_kits: List[RetrievalKit]):
        self.ursula_address = ursula_address
        self.__retrieval_kits = retrieval_kits

    @property
    def capsules(self) -> List[Capsule]:
        return [rk.capsule for rk in self.__retrieval_kits]

    @property
    def conditions(self) -> Conditions:
        _conditions_list = [rk.conditions for rk in self.__retrieval_kits]
        rust_conditions = self._serialize_rust_conditions(_conditions_list)
        return rust_conditions

    @staticmethod
    def _serialize_rust_conditions(conditions_list: List[Conditions]) -> Conditions:
        lingo_lists = list()
        for condition in conditions_list:
            lingo = condition
            if condition:
                lingo = json.loads((str(condition)))
            lingo_lists.append(lingo)
        rust_lingos = Conditions(json.dumps(lingo_lists))
        return rust_lingos


class PRERetrievalClient(ThresholdAccessControlClient):
    """
    Capsule frag retrieval machinery shared between Bob and Porter.
    """

    DEFAULT_RETRIEVAL_TIMEOUT = 10

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def _request_reencryption(
        self,
        ursula: "lawful.Ursula",
        reencryption_request: ReencryptionRequest,
        alice_verifying_key: PublicKey,
        policy_encrypting_key: PublicKey,
        bob_encrypting_key: PublicKey,
        timeout: int,
    ) -> Dict["Capsule", "VerifiedCapsuleFrag"]:
        """
        Sends a reencryption request to a single Ursula and processes the results.

        Returns reencrypted capsule frags matched to corresponding capsules.
        """

        middleware = self._learner.network_middleware

        try:
            response = middleware.reencrypt(
                ursula, bytes(reencryption_request), timeout=timeout
            )
        except NodeSeemsToBeDown as e:
            # TODO: What to do here?  Ursula isn't supposed to be down.  NRN
            message = (f"Ursula ({ursula}) seems to be down "
                       f"while trying to complete ReencryptionRequest: {reencryption_request}")
            self.log.info(message)
            raise RuntimeError(message) from e
        except middleware.NotFound as e:
            # This Ursula claims not to have a matching KFrag.
            # TODO: What's the thing to do here?
            # Do we want to track these Ursulas in some way in case they're lying?  #567
            message = f"Ursula ({ursula}) claims not to not know of the policy {reencryption_request.hrac}."
            self.log.warn(message)
            raise RuntimeError(message) from e
        except middleware.UnexpectedResponse:
            raise  # TODO: Handle this

        try:
            reencryption_response = ReencryptionResponse.from_bytes(response.content)
        except Exception as e:
            message = f"Ursula ({ursula}) returned an invalid response: {e}."
            self.log.warn(message)
            raise RuntimeError(message)

        ursula_verifying_key = ursula.stamp.as_umbral_pubkey()

        try:
            verified_cfrags = reencryption_response.verify(capsules=reencryption_request.capsules,
                                                           alice_verifying_key=alice_verifying_key,
                                                           ursula_verifying_key=ursula_verifying_key,
                                                           policy_encrypting_key=policy_encrypting_key,
                                                           bob_encrypting_key=bob_encrypting_key)
        except InvalidSignature as e:
            self.log.warn(f"Invalid signature for ReencryptionResponse: {e}")
            raise
        except VerificationError as e:
            # In future we may want to remember this Ursula and do something about it
            self.log.warn(
                f"Failed to verify capsule frags in the ReencryptionResponse: {e}"
            )
            raise
        except Exception as e:
            message = f"Failed to verify the ReencryptionResponse ({e.__class__.__name__}): {e}"
            self.log.warn(message)
            raise RuntimeError(message)

        return {capsule: vcfrag for capsule, vcfrag
                in zip(reencryption_request.capsules, verified_cfrags)}

    def retrieve_cfrags(
        self,
        treasure_map: TreasureMap,
        retrieval_kits: Sequence[RetrievalKit],
        alice_verifying_key: PublicKey,  # KeyFrag signer's key
        bob_encrypting_key: PublicKey,  # User's public key (reencryption target)
        bob_verifying_key: PublicKey,
        context: Dict,
        timeout: int = DEFAULT_RETRIEVAL_TIMEOUT,
    ) -> Tuple[List[RetrievalResult], List[RetrievalError]]:
        ursulas_in_map = treasure_map.destinations.keys()

        # TODO (#1995): when that issue is fixed, conversion is no longer needed
        ursulas_in_map = [
            to_checksum_address(bytes(address)) for address in ursulas_in_map
        ]

        self._ensure_ursula_availability(
            ursulas=ursulas_in_map, threshold=treasure_map.threshold, timeout=timeout
        )

        retrieval_plan = RetrievalPlan(treasure_map=treasure_map, retrieval_kits=retrieval_kits)

        while not retrieval_plan.is_complete():
            # TODO (#2789): Currently we'll only query one Ursula once during the retrieval.
            # Alternatively we may re-query Ursulas that were offline until the timeout expires.

            work_order = retrieval_plan.get_work_order()

            # TODO (#1995): when that issue is fixed, conversion is no longer needed
            ursula_checksum_address = to_checksum_address(bytes(work_order.ursula_address))

            if ursula_checksum_address not in self._learner.known_nodes:
                continue

            ursula = self._learner.known_nodes[ursula_checksum_address]

            try:
                request_context_string = json.dumps(context)
            except TypeError:
                raise InvalidConditionContext("'context' must be JSON serializable.")

            reencryption_request = ReencryptionRequest(
                capsules=work_order.capsules,
                conditions=work_order.conditions,
                context=Context(request_context_string),
                hrac=treasure_map.hrac,
                encrypted_kfrag=treasure_map.destinations[work_order.ursula_address],
                bob_verifying_key=bob_verifying_key,
                publisher_verifying_key=treasure_map.publisher_verifying_key
            )

            try:
                cfrags = self._request_reencryption(
                    ursula=ursula,
                    reencryption_request=reencryption_request,
                    alice_verifying_key=alice_verifying_key,
                    policy_encrypting_key=treasure_map.policy_encrypting_key,
                    bob_encrypting_key=bob_encrypting_key,
                    timeout=timeout,
                )
            except Exception as e:
                exception_message = f"{e.__class__.__name__}: {e}"
                retrieval_plan.update_errors(
                    work_order, ursula_checksum_address, exception_message
                )
                self.log.warn(
                    f"Ursula {ursula} failed to reencrypt; {exception_message}"
                )
                continue

            retrieval_plan.update(work_order, cfrags)

        return retrieval_plan.results()
