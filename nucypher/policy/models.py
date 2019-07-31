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
import binascii
from abc import abstractmethod
from collections import OrderedDict

import maya
import msgpack
from bytestring_splitter import BytestringSplitter, VariableLengthBytestring
from constant_sorrow.constants import UNKNOWN_KFRAG, NO_DECRYPTION_PERFORMED, NOT_SIGNED
from cryptography.hazmat.backends.openssl import backend
from cryptography.hazmat.primitives import hashes
from eth_utils import to_canonical_address, to_checksum_address
from typing import Generator, List, Set, Optional, Tuple

from umbral.cfrags import CapsuleFrag
from umbral.config import default_params
from umbral.curvebn import CurveBN
from umbral.keys import UmbralPublicKey
from umbral.kfrags import KFrag
from umbral.pre import Capsule

from nucypher.characters.lawful import Alice, Bob, Ursula, Character
from nucypher.crypto.api import keccak_digest, encrypt_and_sign, secure_random
from nucypher.crypto.constants import PUBLIC_ADDRESS_LENGTH, KECCAK_DIGEST_LENGTH, PUBLIC_KEY_LENGTH
from nucypher.crypto.kits import UmbralMessageKit, RevocationKit
from nucypher.crypto.powers import SigningPower, DecryptingPower
from nucypher.crypto.signing import Signature, InvalidSignature, signature_splitter
from nucypher.crypto.splitters import key_splitter, capsule_splitter
from nucypher.crypto.utils import (canonical_address_from_umbral_key,
                                   construct_policy_id,
                                   get_coordinates_as_bytes,
                                   get_signature_recovery_value)
from nucypher.network.exceptions import NodeSeemsToBeDown
from nucypher.network.middleware import RestMiddleware, NotFound


class Arrangement:
    """
    A Policy must be implemented by arrangements with n Ursulas.  This class tracks the status of that implementation.
    """
    federated = True
    ID_LENGTH = 32

    splitter = BytestringSplitter((UmbralPublicKey, PUBLIC_KEY_LENGTH),  # alice.stamp
                                  (bytes, ID_LENGTH),  # arrangement_ID
                                  (bytes, VariableLengthBytestring))  # expiration

    def __init__(self,
                 alice: Alice,
                 expiration: maya.MayaDT,
                 value: int = None,
                 ursula: Ursula = None,
                 arrangement_id: bytes = None,
                 kfrag: KFrag = UNKNOWN_KFRAG
                 ) -> None:
        """
        :param value: Funds which will pay for the timeframe  of this Arrangement (not the actual re-encryptions);
                      a portion will be locked for each Ursula that accepts.
        :param expiration: The moment which Alice wants the Arrangement to end.

        Other params are hopefully self-evident.
        """
        if arrangement_id:
            if len(arrangement_id) != self.ID_LENGTH:
                raise ValueError(f"Arrangement ID must be of length {self.ID_LENGTH}.")
            self.id = arrangement_id
        else:
            self.id = secure_random(self.ID_LENGTH)
        self.expiration = expiration
        self.alice = alice
        self.value = value

        """
        These will normally not be set if Alice is drawing up this arrangement - she hasn't assigned a kfrag yet
        (because she doesn't know if this Arrangement will be accepted).  She doesn't have an Ursula, for the same reason.
        """
        self.kfrag = kfrag
        self.ursula = ursula

    def __bytes__(self):
        return bytes(self.alice.stamp) + self.id + bytes(VariableLengthBytestring(self.expiration.iso8601().encode()))

    @classmethod
    def from_bytes(cls, arrangement_as_bytes):
        alice_verifying_key, arrangement_id, expiration_bytes = cls.splitter(arrangement_as_bytes)
        expiration = maya.MayaDT.from_iso8601(iso8601_string=expiration_bytes.decode())
        alice = Alice.from_public_keys(verifying_key=alice_verifying_key)
        return cls(alice=alice, arrangement_id=arrangement_id, expiration=expiration)

    def encrypt_payload_for_ursula(self):
        """Craft an offer to send to Ursula."""
        # We don't need the signature separately.
        return self.alice.encrypt_for(self.ursula, self.payload())[0]

    def payload(self):
        # TODO #127 - Ship the expiration again?
        # Or some other way of alerting Ursula to
        # recall her previous dialogue regarding this Arrangement.
        # Update: We'll probably have her store the Arrangement by hrac.  See #127.
        return bytes(self.kfrag)

    @abstractmethod
    def revoke(self):
        """
        Revoke arrangement.
        """
        raise NotImplementedError


class Policy:
    """
    An edict by Alice, arranged with n Ursulas, to perform re-encryption for a specific Bob
    for a specific path.

    Once Alice is ready to enact a Policy, she generates KFrags, which become part of the Policy.

    Each Ursula is offered a Arrangement (see above) for a given Policy by Alice.

    Once Alice has secured agreement with n Ursulas to enact a Policy, she sends each a KFrag,
    and generates a TreasureMap for the Policy, recording which Ursulas got a KFrag.
    """

    POLICY_ID_LENGTH = 16

    def __init__(self,
                 alice,
                 label,
                 bob=None,
                 kfrags=(UNKNOWN_KFRAG,),
                 public_key=None,
                 m: int = None,
                 alice_signature=NOT_SIGNED) -> None:

        """
        :param kfrags:  A list of KFrags to distribute per this Policy.
        :param label: The identity of the resource to which Bob is granted access.
        """
        self.alice = alice                     # type: Alice
        self.label = label                     # type: bytes
        self.bob = bob                         # type: Bob
        self.kfrags = kfrags                   # type: List[KFrag]
        self.public_key = public_key
        self.treasure_map = TreasureMap(m=m)

        # Keep track of this stuff
        self._accepted_arrangements = set()    # type: set
        self._rejected_arrangements = set()    # type: set

        self._enacted_arrangements = OrderedDict()    # type: OrderedDict
        self._published_arrangements = OrderedDict()  # type: OrderedDict

        self.alice_signature = alice_signature  # TODO: This is unused / To Be Implemented?

    class MoreKFragsThanArrangements(TypeError):
        """
        Raised when a Policy has been used to generate Arrangements with Ursulas insufficient number
        such that we don't have enough KFrags to give to each Ursula.
        """

    @property
    def n(self) -> int:
        return len(self.kfrags)

    @property
    def id(self) -> bytes:
        return construct_policy_id(self.label, bytes(self.bob.stamp))

    def hrac(self) -> bytes:
        """
        # TODO: #180 - This function is hanging on for dear life.  After 180 is closed, it can be completely deprecated.

        The "hashed resource authentication code".

        A hash of:
        * Alice's public key
        * Bob's public key
        * the label

        Alice and Bob have all the information they need to construct this.
        Ursula does not, so we share it with her.
        """
        return keccak_digest(bytes(self.alice.stamp) + bytes(self.bob.stamp) + self.label)

    def publish_treasure_map(self, network_middleware: RestMiddleware) -> dict:
        self.treasure_map.prepare_for_publication(self.bob.public_keys(DecryptingPower),
                                                  self.bob.public_keys(SigningPower),
                                                  self.alice.stamp,
                                                  self.label)
        if not self.alice.known_nodes:
            # TODO: Optionally, block.
            raise RuntimeError("Alice hasn't learned of any nodes.  Thus, she can't push the TreasureMap.")

        responses = dict()
        for node in self.alice.known_nodes:
            # TODO: # 342 - It's way overkill to push this to every node we know about.  Come up with a system.

            try:
                treasure_map_id = self.treasure_map.public_id()

                # TODO: Certificate filepath needs to be looked up and passed here
                response = network_middleware.put_treasure_map_on_node(node=node,
                                                                       map_id=treasure_map_id,
                                                                       map_payload=bytes(self.treasure_map))
            except NodeSeemsToBeDown:
                # TODO: Introduce good failure mode here if too few nodes receive the map.
                continue

            if response.status_code == 202:
                # TODO: #341 - Handle response wherein node already had a copy of this TreasureMap.
                responses[node] = response

            else:
                # TODO: Do something useful here.
                raise RuntimeError

        return responses

    def publish(self, network_middleware: RestMiddleware) -> dict:
        """
        Spread word of this Policy far and wide.

        Base publication method for spreading news of the policy.
        If this is a blockchain policy, this includes writing to
        PolicyManager contract storage.
        """
        return self.publish_treasure_map(network_middleware=network_middleware)

    def __assign_kfrags(self) -> Generator[Arrangement, None, None]:

        if len(self._accepted_arrangements) < self.n:
            raise self.MoreKFragsThanArrangements("Not enough candidate arrangements. "
                                                  "Call make_arrangements to make more.")

        for kfrag in self.kfrags:
            for arrangement in self._accepted_arrangements:
                if not arrangement in self._enacted_arrangements.values():
                    arrangement.kfrag = kfrag
                    self._enacted_arrangements[kfrag] = arrangement
                    yield arrangement
                    break  # This KFrag is now assigned; break the inner loop and go back to assign other kfrags.
            else:
                # We didn't assign that KFrag.  Trouble.
                # This is ideally an impossible situation, because we don't typically
                # enter this method unless we've already had n or more Arrangements accepted.
                raise self.MoreKFragsThanArrangements("Not enough accepted arrangements to assign all KFrags.")
        return

    def enact(self, network_middleware, publish=True) -> dict:
        """
        Assign kfrags to ursulas_on_network, and distribute them via REST,
        populating enacted_arrangements
        """
        for arrangement in self.__assign_kfrags():
            policy_message_kit = arrangement.encrypt_payload_for_ursula()

            response = network_middleware.enact_policy(arrangement.ursula,
                                                       arrangement.id,
                                                       policy_message_kit.to_bytes())

            if not response:
                pass  # TODO: Parse response for confirmation.

            # Assuming response is what we hope for.
            self.treasure_map.add_arrangement(arrangement)

        else:  # ...After *all* the policies are enacted
            # Create Alice's revocation kit
            self.revocation_kit = RevocationKit(self, self.alice.stamp)
            self.alice.add_active_policy(self)

            if publish is True:
                return self.publish(network_middleware=network_middleware)

    def consider_arrangement(self, network_middleware, ursula, arrangement) -> bool:
        try:
            ursula.verify_node(network_middleware,
                               accept_federated_only=arrangement.federated)
        except ursula.InvalidNode:
            # TODO: What do we actually do here?  Report this at least (355)?
            # Maybe also have another bucket for invalid nodes?
            # It's possible that nothing sordid is happening here;
            # this node may be updating its interface info or rotating a signing key
            # and we learned about a previous one.
            raise

        negotiation_response = network_middleware.consider_arrangement(arrangement=arrangement)

        # TODO: check out the response: need to assess the result and see if we're actually good to go.
        arrangement_is_accepted = negotiation_response.status_code == 200

        bucket = self._accepted_arrangements if arrangement_is_accepted else self._rejected_arrangements
        bucket.add(arrangement)

        return arrangement_is_accepted

    @abstractmethod
    def make_arrangements(self,
                          network_middleware: RestMiddleware,
                          deposit: int,
                          expiration: maya.MayaDT,
                          ursulas: Set[Ursula] = None) -> None:
        """
        Create and consider n Arrangement objects.
        """
        raise NotImplementedError

    def _consider_arrangements(self,
                               network_middleware: RestMiddleware,
                               candidate_ursulas: Set[Ursula],
                               value: int,
                               expiration: maya.MayaDT):

        for selected_ursula in candidate_ursulas:
            arrangement = self._arrangement_class(alice=self.alice,
                                                  ursula=selected_ursula,
                                                  value=value,
                                                  expiration=expiration)
            try:
                is_accepted = self.consider_arrangement(ursula=selected_ursula,
                                                        arrangement=arrangement,
                                                        network_middleware=network_middleware)

            except NodeSeemsToBeDown:  # TODO: #355 Also catch InvalidNode here?
                # This arrangement won't be added to the accepted bucket.
                # If too many nodes are down, it will fail in make_arrangements.
                continue

            else:

                # Bucket the arrangements
                if is_accepted:
                    self._accepted_arrangements.add(arrangement)
                else:
                    self._rejected_arrangements.add(arrangement)

        return self._accepted_arrangements, self._rejected_arrangements


class FederatedPolicy(Policy):
    _arrangement_class = Arrangement

    def __init__(self, ursulas: Set[Ursula], *args, **kwargs) -> None:
        self.ursulas = ursulas
        super().__init__(*args, **kwargs)

    def make_arrangements(self,
                          network_middleware: RestMiddleware,
                          value: int,
                          expiration: maya.MayaDT,
                          handpicked_ursulas: Set[Ursula] = None) -> None:

        if handpicked_ursulas is None:
            ursulas = set()  # type: set
        else:
            ursulas = handpicked_ursulas
        ursulas.update(self.ursulas)

        if len(ursulas) < self.n:
            raise ValueError(
                "To make a Policy in federated mode, you need to designate *all* '  \
                 the Ursulas you need (in this case, {}); there's no other way to ' \
                 know which nodes to use.  Either pass them here or when you make ' \
                 the Policy.".format(self.n))

        # TODO: One of these layers needs to add concurrency.

        self._consider_arrangements(network_middleware,
                                    candidate_ursulas=ursulas,
                                    value=value,
                                    expiration=expiration)

        if len(self._accepted_arrangements) < self.n:
            raise self.MoreKFragsThanArrangements


class TreasureMap:
    splitter = BytestringSplitter(Signature,
                                  (bytes, KECCAK_DIGEST_LENGTH),  # hrac
                                  (UmbralMessageKit, VariableLengthBytestring)
                                  )

    class NowhereToBeFound(NotFound):
        """
        Called when no known nodes have it.
        """

    node_id_splitter = BytestringSplitter((to_checksum_address, int(PUBLIC_ADDRESS_LENGTH)), Arrangement.ID_LENGTH)

    from nucypher.crypto.signing import InvalidSignature  # Raised when the public signature (typically intended for Ursula) is not valid.

    def __init__(self,
                 m: int = None,
                 destinations=None,
                 message_kit: UmbralMessageKit = None,
                 public_signature: Signature = None,
                 hrac: Optional[bytes] = None) -> None:

        if m is not None:
            if m > 255:
                raise ValueError("Largest allowed value for m is 255.")
            self._m = m

            self._destinations = destinations or {}
        else:
            self._m = NO_DECRYPTION_PERFORMED
            self._destinations = NO_DECRYPTION_PERFORMED

        self.message_kit = message_kit
        self._public_signature = public_signature
        self._hrac = hrac
        self._payload = None

    def prepare_for_publication(self,
                                bob_encrypting_key,
                                bob_verifying_key,
                                alice_stamp,
                                label):

        plaintext = self._m.to_bytes(1, "big") + self.nodes_as_bytes()

        self.message_kit, _signature_for_bob = encrypt_and_sign(bob_encrypting_key,
                                                                plaintext=plaintext,
                                                                signer=alice_stamp,
                                                                )
        """
        Here's our "hashed resource access code".

        A hash of:
        * Alice's public key
        * Bob's public key
        * the label

        Alice and Bob have all the information they need to construct this.
        Ursula does not, so we share it with her.

        This way, Bob can generate it and use it to find the TreasureMap.
        """
        self._hrac = keccak_digest(bytes(alice_stamp) + bytes(bob_verifying_key) + label)
        self._public_signature = alice_stamp(bytes(alice_stamp) + self._hrac)
        self._set_payload()

    def _set_payload(self):
        self._payload = self._public_signature + self._hrac + bytes(
            VariableLengthBytestring(self.message_kit.to_bytes()))

    def __bytes__(self):
        if self._payload is None:
            self._set_payload()

        return self._payload

    @property
    def _verifying_key(self):
        return self.message_kit.sender_verifying_key

    @property
    def m(self):
        if self._m == NO_DECRYPTION_PERFORMED:
            raise TypeError("The TreasureMap is probably encrypted. You must decrypt it first.")
        return self._m

    @property
    def destinations(self):
        if self._destinations == NO_DECRYPTION_PERFORMED:
            raise TypeError("The TreasureMap is probably encrypted. You must decrypt it first.")
        return self._destinations

    def nodes_as_bytes(self):
        if self.destinations == NO_DECRYPTION_PERFORMED:
            return NO_DECRYPTION_PERFORMED
        else:
            nodes_as_bytes = b""
            for ursula_id, arrangement_id in self.destinations.items():
                nodes_as_bytes += to_canonical_address(ursula_id) + arrangement_id
            return nodes_as_bytes

    def add_arrangement(self, arrangement):
        if self.destinations == NO_DECRYPTION_PERFORMED:
            raise TypeError("This TreasureMap is encrypted.  You can't add another node without decrypting it.")
        self.destinations[arrangement.ursula.checksum_address] = arrangement.id

    def public_id(self):
        """
        We need an ID that Bob can glean from knowledge he already has *and* which Ursula can verify came from Alice.
        Ursula will refuse to propagate this if it she can't prove the payload is signed by Alice's public key,
        which is included in it,
        """
        _id = keccak_digest(bytes(self._verifying_key) + bytes(self._hrac)).hex()
        return _id

    @classmethod
    def from_bytes(cls, bytes_representation, verify=True):
        signature, hrac, tmap_message_kit = cls.splitter(bytes_representation)

        treasure_map = cls(
            message_kit=tmap_message_kit,
            public_signature=signature,
            hrac=hrac,
        )

        if verify:
            treasure_map.public_verify()

        return treasure_map

    def public_verify(self):
        message = bytes(self._verifying_key) + self._hrac
        verified = self._public_signature.verify(message, self._verifying_key)

        if verified:
            return True
        else:
            raise self.InvalidSignature("This TreasureMap is not properly publicly signed by Alice.")

    def orient(self, compass):
        """
        When Bob receives the TreasureMap, he'll pass a compass (a callable which can verify and decrypt the
        payload message kit).
        """
        try:
            map_in_the_clear = compass(message_kit=self.message_kit)
        except Character.InvalidSignature:
            raise self.InvalidSignature(
                "This TreasureMap does not contain the correct signature from Alice to Bob.")
        else:
            self._m = map_in_the_clear[0]
            self._destinations = dict(self.node_id_splitter.repeat(map_in_the_clear[1:]))

    def __eq__(self, other):
        return bytes(self) == bytes(other)

    def __iter__(self):
        return iter(self.destinations.items())

    def __len__(self):
        return len(self.destinations)


class WorkOrder:

    class Task:
        def __init__(self, capsule, signature, cfrag=None, cfrag_signature=None):
            self.capsule = capsule
            self.signature = signature
            self.cfrag = cfrag  # TODO: we need to store them in case of Ursula misbehavior
            self.cfrag_signature = cfrag_signature

        def get_specification(self, ursula_pubkey, alice_address, blockhash, ursula_identity_evidence=b''):
            task_specification = (bytes(self.capsule),
                                  bytes(ursula_pubkey),
                                  bytes(ursula_identity_evidence),
                                  alice_address,
                                  blockhash)
            return b''.join(task_specification)

        def __bytes__(self):
            data = bytes(self.capsule) + bytes(self.signature)
            if self.cfrag and self.cfrag_signature:
                data += bytes(self.cfrag) + bytes(self.cfrag_signature)
            return data

        @classmethod
        def from_bytes(cls, data: bytes):
            item_splitter = capsule_splitter + signature_splitter
            capsule, signature, remainder = item_splitter(data, return_remainder=True)
            if remainder:
                remainder_splitter = BytestringSplitter((CapsuleFrag, VariableLengthBytestring), Signature)
                cfrag, reencryption_signature = remainder_splitter(remainder)
                return cls(capsule=capsule, signature=signature,
                           cfrag=cfrag, reencryption_signature=reencryption_signature)
            else:
                return cls(capsule=capsule, signature=signature)

        def attach_work_result(self, cfrag, reencryption_signature):
            self.cfrag = cfrag
            self.cfrag_signature = reencryption_signature

    def __init__(self,
                 bob: Bob,
                 arrangement_id,
                 alice_address: bytes,
                 tasks: List,
                 receipt_signature,
                 ursula=None,
                 blockhash=None
                 ) -> None:
        self.bob = bob
        self.arrangement_id = arrangement_id
        self.alice_address = alice_address
        self.tasks = tasks
        self.receipt_signature = receipt_signature
        self.ursula = ursula  # TODO: We may still need a more elegant system for ID'ing Ursula.  See #136.
        self.blockhash = blockhash or b'\x00' * 32  # TODO: #259
        self.completed = False

    def __repr__(self):
        return "WorkOrder for hrac {hrac}: (capsules: {capsule_bytes}) for Ursula: {node}".format(
            hrac=self.arrangement_id.hex()[:6],
            capsule_bytes=[binascii.hexlify(bytes(item.capsule))[:6] for item in self.tasks],
            node=binascii.hexlify(bytes(self.ursula.stamp))[:6])

    def __eq__(self, other):
        return self.receipt_signature == other.receipt_signature

    def __len__(self):
        return len(self.tasks)

    @classmethod
    def construct_by_bob(cls, arrangement_id, capsules, ursula, bob):
        alice_verifying_key = capsules[0].get_correctness_keys()["verifying"]
        alice_address = canonical_address_from_umbral_key(alice_verifying_key)

        # TODO: Bob's input to prove freshness for this work order
        blockhash = b'\x00' * 32

        ursula_identity_evidence = b''
        if ursula._stamp_has_valid_signature_by_worker():
            ursula_identity_evidence = ursula.decentralized_identity_evidence

        tasks, tasks_bytes = [], []
        for capsule in capsules:
            if alice_verifying_key != capsule.get_correctness_keys()["verifying"]:
                raise ValueError("Capsules in this work order are inconsistent.")

            task = cls.Task(capsule, signature=None)
            specification = task.get_specification(ursula.stamp, alice_address, blockhash, ursula_identity_evidence)
            task.signature = bob.stamp(specification)
            tasks.append(task)
            tasks_bytes.append(bytes(task))

        # TODO: What's the goal of the receipt? Should it include only the capsules?
        receipt_bytes = b"wo:" + bytes(ursula.stamp) + msgpack.dumps(tasks_bytes)
        receipt_signature = bob.stamp(receipt_bytes)

        return cls(bob=bob, arrangement_id=arrangement_id, tasks=tasks,
                   receipt_signature=receipt_signature,
                   alice_address=alice_address,
                   ursula=ursula, blockhash=blockhash)

    @classmethod
    def from_rest_payload(cls, arrangement_id, rest_payload, ursula, alice_address):

        payload_splitter = BytestringSplitter(Signature) + key_splitter
        payload_elements = payload_splitter(rest_payload, msgpack_remainder=True)

        signature, bob_verifying_key, (tasks_bytes, blockhash) = payload_elements

        # TODO: check freshness of blockhash?

        # Check receipt
        receipt_bytes = b"wo:" + bytes(ursula.stamp) + msgpack.dumps(tasks_bytes)
        if not signature.verify(receipt_bytes, bob_verifying_key):
            raise InvalidSignature()

        ursula_identity_evidence = b''
        if ursula._stamp_has_valid_signature_by_worker():
            ursula_identity_evidence = ursula.decentralized_identity_evidence

        tasks = []
        for task_bytes in tasks_bytes:
            task = cls.Task.from_bytes(task_bytes)
            tasks.append(task)

            # Each task signature has to match the original specification
            specification = task.get_specification(ursula.stamp,
                                                   alice_address,
                                                   blockhash,
                                                   ursula_identity_evidence)

            if not task.signature.verify(specification, bob_verifying_key):
                raise InvalidSignature()

        bob = Bob.from_public_keys(verifying_key=bob_verifying_key)
        return cls(bob=bob,
                   ursula=ursula,
                   arrangement_id=arrangement_id,
                   tasks=tasks,
                   alice_address=alice_address,
                   blockhash=blockhash,
                   receipt_signature=signature)

    def payload(self):
        tasks_bytes = [bytes(item) for item in self.tasks]
        payload_elements = msgpack.dumps((tasks_bytes, self.blockhash))
        return bytes(self.receipt_signature) + self.bob.stamp + payload_elements

    def complete(self, cfrags_and_signatures):
        good_cfrags = []
        if not len(self) == len(cfrags_and_signatures):
            raise ValueError("Ursula gave back the wrong number of cfrags.  "
                             "She's up to something.")

        ursula_verifying_key = self.ursula.stamp.as_umbral_pubkey()

        for task, (cfrag, cfrag_signature) in zip(self.tasks, cfrags_and_signatures):
            # Validate re-encryption metadata
            metadata_input = bytes(task.signature)
            metadata_as_signature = Signature.from_bytes(cfrag.proof.metadata)
            if not metadata_as_signature.verify(metadata_input, ursula_verifying_key):
                raise InvalidSignature(f"Invalid metadata for {cfrag}.")
                # TODO: Instead of raising, we should do something (#957)

            # Validate re-encryption signatures
            if cfrag_signature.verify(bytes(cfrag), ursula_verifying_key):
                good_cfrags.append(cfrag)
            else:
                raise InvalidSignature(f"{cfrag} is not properly signed by Ursula.")
                # TODO: Instead of raising, we should do something (#957)

        for task, (cfrag, cfrag_signature) in zip(self.tasks, cfrags_and_signatures):
            task.attach_work_result(cfrag, cfrag_signature)

        self.completed = maya.now()
        return good_cfrags


class WorkOrderHistory:

    def __init__(self) -> None:
        self.by_ursula = {}  # type: dict

    def __contains__(self, item):
        assert False

    def __getitem__(self, item):
        return self.by_ursula.setdefault(item, {})

    def __setitem__(self, key, value):
        assert False

    def __len__(self):
        return sum(len(work_orders) for work_orders in self.by_ursula.values())

    @property
    def ursulas(self):
        return self.by_ursula.keys()

    def by_capsule(self, capsule: Capsule):
        ursulas_by_capsules = {}  # type: dict
        for ursula, capsules in self.by_ursula.items():
            for saved_capsule, work_order in capsules.items():
                if saved_capsule == capsule:
                    ursulas_by_capsules[ursula] = work_order
        return ursulas_by_capsules


class Revocation:
    """
    Represents a string used by characters to perform a revocation on a specific
    Ursula. It's a bytestring made of the following format:
    REVOKE-<arrangement id to revoke><signature of the previous string>
    This is sent as a payload in a DELETE method to the /KFrag/ endpoint.
    """
    revocation_splitter = BytestringSplitter((bytes, 7), (bytes, 32), Signature)

    def __init__(self, arrangement_id: bytes,
                       signer: 'SignatureStamp' = None,
                       signature: Signature = None):

        self.prefix = b'REVOKE-'
        self.arrangement_id = arrangement_id

        if not (bool(signer) ^ bool(signature)):
            raise ValueError("Either pass a signer or a signature; not both.")
        elif signer:
            self.signature = signer(self.prefix + self.arrangement_id)
        elif signature:
            self.signature = signature

    def __bytes__(self):
        return self.prefix + self.arrangement_id + bytes(self.signature)

    def __repr__(self):
        return bytes(self)

    def __len__(self):
        return len(bytes(self))

    def __eq__(self, other):
        return bytes(self) == bytes(other)

    @classmethod
    def from_bytes(cls, revocation_bytes):
        _, arrangement_id, signature = cls.revocation_splitter(revocation_bytes)
        return cls(arrangement_id, signature=signature)

    def verify_signature(self, alice_pubkey: 'UmbralPublicKey'):
        """
        Verifies the revocation was from the provided pubkey.
        """
        if not self.signature.verify(self.prefix + self.arrangement_id, alice_pubkey):
            raise InvalidSignature(
                "Revocation has an invalid signature: {}".format(self.signature))
        return True


# TODO: Change name to EvaluationEvidence
class IndisputableEvidence:

    def __init__(self,
                 task: 'WorkOrder.Task',
                 work_order: 'WorkOrder',
                 delegating_pubkey: UmbralPublicKey = None,
                 receiving_pubkey: UmbralPublicKey = None,
                 verifying_pubkey: UmbralPublicKey = None,
                 ) -> None:

        self.task = task
        self.ursula_pubkey = work_order.ursula.stamp.as_umbral_pubkey()
        self.ursula_identity_evidence = work_order.ursula.decentralized_identity_evidence
        self.bob_verifying_key = work_order.bob.stamp.as_umbral_pubkey()
        self.blockhash = work_order.blockhash
        self.alice_address = work_order.alice_address

        keys = self.task.capsule.get_correctness_keys()
        key_types = ("delegating", "receiving", "verifying")
        if all(keys[key_type] for key_type in key_types):
            self.delegating_pubkey = keys["delegating"]
            self.receiving_pubkey = keys["receiving"]
            self.verifying_pubkey = keys["verifying"]
        elif all((delegating_pubkey, receiving_pubkey, verifying_pubkey)):
            self.delegating_pubkey = delegating_pubkey
            self.receiving_pubkey = receiving_pubkey
            self.verifying_pubkey = verifying_pubkey
        else:
            raise ValueError("All correctness keys are required to compute evidence.  "
                             "Either pass them as arguments or in the capsule.")

        # TODO: check that the metadata is correct.

    def get_proof_challenge_scalar(self) -> CurveBN:
        capsule = self.task.capsule
        cfrag = self.task.cfrag

        umbral_params = default_params()
        e, v, _ = capsule.components()

        e1 = cfrag.point_e1
        v1 = cfrag.point_v1
        e2 = cfrag.proof.point_e2
        v2 = cfrag.proof.point_v2
        u = umbral_params.u
        u1 = cfrag.proof.point_kfrag_commitment
        u2 = cfrag.proof.point_kfrag_pok
        metadata = cfrag.proof.metadata

        from umbral.random_oracles import hash_to_curvebn, ExtendedKeccak

        hash_input = (e, e1, e2, v, v1, v2, u, u1, u2, metadata)

        h = hash_to_curvebn(*hash_input, params=umbral_params, hash_class=ExtendedKeccak)
        return h

    def precompute_values(self) -> bytes:
        capsule = self.task.capsule
        cfrag = self.task.cfrag

        umbral_params = default_params()
        e, v, _ = capsule.components()

        e1 = cfrag.point_e1
        v1 = cfrag.point_v1
        e2 = cfrag.proof.point_e2
        v2 = cfrag.proof.point_v2
        u = umbral_params.u
        u1 = cfrag.proof.point_kfrag_commitment
        u2 = cfrag.proof.point_kfrag_pok
        metadata = cfrag.proof.metadata

        h = self.get_proof_challenge_scalar()

        e1h = h * e1
        v1h = h * v1
        u1h = h * u1

        z = cfrag.proof.bn_sig
        ez = z * e
        vz = z * v
        uz = z * u

        only_y_coord = dict(x_coord=False, y_coord=True)
        # E points
        e_y = get_coordinates_as_bytes(e, **only_y_coord)
        ez_xy = get_coordinates_as_bytes(ez)
        e1_y = get_coordinates_as_bytes(e1, **only_y_coord)
        e1h_xy = get_coordinates_as_bytes(e1h)
        e2_y = get_coordinates_as_bytes(e2, **only_y_coord)
        # V points
        v_y = get_coordinates_as_bytes(v, **only_y_coord)
        vz_xy = get_coordinates_as_bytes(vz)
        v1_y = get_coordinates_as_bytes(v1, **only_y_coord)
        v1h_xy = get_coordinates_as_bytes(v1h)
        v2_y = get_coordinates_as_bytes(v2, **only_y_coord)
        # U points
        uz_xy = get_coordinates_as_bytes(uz)
        u1_y = get_coordinates_as_bytes(u1, **only_y_coord)
        u1h_xy = get_coordinates_as_bytes(u1h)
        u2_y = get_coordinates_as_bytes(u2, **only_y_coord)

        # Get hashed KFrag validity message
        hash_function = hashes.Hash(hashes.SHA256(), backend=backend)

        kfrag_id = cfrag.kfrag_id
        precursor = cfrag.point_precursor
        delegating_pubkey = self.delegating_pubkey
        receiving_pubkey = self.receiving_pubkey

        validity_input = (kfrag_id, delegating_pubkey, receiving_pubkey, u1, precursor)
        kfrag_validity_message = bytes().join(bytes(item) for item in validity_input)
        hash_function.update(kfrag_validity_message)
        hashed_kfrag_validity_message = hash_function.finalize()

        # Get KFrag signature's v value
        kfrag_signature_v = get_signature_recovery_value(message=hashed_kfrag_validity_message,
                                                         signature=cfrag.proof.kfrag_signature,
                                                         public_key=self.verifying_pubkey,
                                                         is_prehashed=True)

        cfrag_signature_v = get_signature_recovery_value(message=bytes(cfrag),
                                                         signature=self.task.cfrag_signature,
                                                         public_key=self.ursula_pubkey)

        metadata_signature_v = get_signature_recovery_value(message=self.task.signature,
                                                            signature=metadata,
                                                            public_key=self.ursula_pubkey)

        specification = self.task.get_specification(ursula_pubkey=self.ursula_pubkey,
                                                    alice_address=self.alice_address,
                                                    blockhash=self.blockhash,
                                                    ursula_identity_evidence=self.ursula_identity_evidence)

        specification_signature_v = get_signature_recovery_value(message=specification,
                                                                 signature=self.task.signature,
                                                                 public_key=self.bob_verifying_key)

        ursula_pubkey_prefix_byte = bytes(self.ursula_pubkey)[0:1]

        # Bundle everything together
        pieces = (
            e_y, ez_xy, e1_y, e1h_xy, e2_y,
            v_y, vz_xy, v1_y, v1h_xy, v2_y,
            uz_xy, u1_y, u1h_xy, u2_y,
            hashed_kfrag_validity_message,
            self.alice_address,
            # The following single-byte values are interpreted as a single bytes5 variable by the Solidity contract
            kfrag_signature_v,
            cfrag_signature_v,
            metadata_signature_v,
            specification_signature_v,
            ursula_pubkey_prefix_byte,
        )
        return b''.join(pieces)

    def evaluation_arguments(self) -> Tuple:
        return (bytes(self.task.capsule),
                bytes(self.task.cfrag),
                bytes(self.task.cfrag_signature),
                bytes(self.task.signature),
                get_coordinates_as_bytes(self.bob_verifying_key),
                get_coordinates_as_bytes(self.ursula_pubkey),
                bytes(self.ursula_identity_evidence),
                self.precompute_values()
                )
