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
import uuid
from bytestring_splitter import BytestringSplitter, VariableLengthBytestring
from constant_sorrow.constants import UNKNOWN_KFRAG, NO_DECRYPTION_PERFORMED, NOT_SIGNED
from cryptography.hazmat.backends.openssl import backend
from cryptography.hazmat.primitives import hashes
from eth_utils import to_canonical_address, to_checksum_address
from typing import Generator, List, Set, Optional

from umbral.cfrags import CapsuleFrag
from umbral.config import default_params
from umbral.curvebn import CurveBN
from umbral.keys import UmbralPublicKey
from umbral.kfrags import KFrag
from umbral.point import Point
from umbral.pre import Capsule

from nucypher.characters.lawful import Alice, Bob, Ursula, Character
from nucypher.crypto.api import keccak_digest, encrypt_and_sign, secure_random
from nucypher.crypto.constants import PUBLIC_ADDRESS_LENGTH, KECCAK_DIGEST_LENGTH
from nucypher.crypto.kits import UmbralMessageKit, RevocationKit
from nucypher.crypto.powers import SigningPower, DecryptingPower
from nucypher.crypto.signing import Signature, InvalidSignature
from nucypher.crypto.splitters import key_splitter
from nucypher.crypto.utils import canonical_address_from_umbral_key, recover_pubkey_from_signature
from nucypher.network.exceptions import NodeSeemsToBeDown
from nucypher.network.middleware import RestMiddleware, NotFound


class Arrangement:
    """
    A Policy must be implemented by arrangements with n Ursulas.  This class tracks the status of that implementation.
    """
    federated = True
    ID_LENGTH = 32

    splitter = key_splitter + BytestringSplitter((bytes, ID_LENGTH),
                                                 (bytes, 27))

    def __init__(self, alice, expiration, ursula=None, arrangement_id=None,
                 kfrag=UNKNOWN_KFRAG, value=None, alices_signature=None) -> None:
        """
        :param deposit: Funds which will pay for the timeframe  of this Arrangement (not the actual re-encryptions);
            a portion will be locked for each Ursula that accepts.
        :param expiration: The moment which Alice wants the Arrangement to end.

        Other params are hopefully self-evident.
        """
        self.id = arrangement_id or secure_random(self.ID_LENGTH)
        self.expiration = expiration
        self.alice = alice
        self.uuid = uuid.uuid4()
        self.value = None

        """
        These will normally not be set if Alice is drawing up this arrangement - she hasn't assigned a kfrag yet
        (because she doesn't know if this Arrangement will be accepted).  She doesn't have an Ursula, for the same reason.
        """
        self.kfrag = kfrag
        self.ursula = ursula

    def __bytes__(self):
        return bytes(self.alice.stamp) + self.id + self.expiration.iso8601().encode()

    @classmethod
    def from_bytes(cls, arrangement_as_bytes):
        # Still unclear how to arrive at the correct number of bytes to represent a deposit.  See #148.
        alice_pubkey_sig, arrangement_id, expiration_bytes = cls.splitter(arrangement_as_bytes)
        expiration = maya.parse(expiration_bytes.decode())
        alice = Alice.from_public_keys({SigningPower: alice_pubkey_sig})
        return cls(alice=alice, arrangement_id=arrangement_id, expiration=expiration)

    def encrypt_payload_for_ursula(self):
        """Craft an offer to send to Ursula."""
        # We don't need the signature separately.
        return self.alice.encrypt_for(self.ursula, self.payload())[0]

    def payload(self):
        # TODO: Ship the expiration again?
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

    def __init__(self,
                 alice,
                 label,
                 bob=None,
                 kfrags=(UNKNOWN_KFRAG,),
                 public_key=None,
                 m: int = None,
                 alices_signature=NOT_SIGNED) -> None:

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

        self.alices_signature = alices_signature

    class MoreKFragsThanArrangements(TypeError):
        """
        Raised when a Policy has been used to generate Arrangements with Ursulas insufficient number
        such that we don't have enough KFrags to give to each Ursula.
        """

    @property
    def n(self) -> int:
        return len(self.kfrags)

    def hrac(self) -> bytes:
        """
        This function is hanging on for dear life.  After 180 is closed, it can be completely deprecated.

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
                                                  self.label
                                                  )
        if not self.alice.known_nodes:
            # TODO: Optionally block.
            raise RuntimeError("Alice hasn't learned of any nodes.  Thus, she can't push the TreasureMap.")

        responses = dict()
        for node in self.alice.known_nodes:
            # TODO: It's way overkill to push this to every node we know about.  Come up with a system.  342
            try:
                treasure_map_id = self.treasure_map.public_id()
                response = network_middleware.put_treasure_map_on_node(node,
                                                                       treasure_map_id,
                                                                       bytes(self.treasure_map)
                                                                       )  # TODO: Certificate filepath needs to be looked up and passed here
            except NodeSeemsToBeDown:
                # TODO: Introduce good failure mode here if too few nodes receive the map.
                continue

            if response.status_code == 202:
                responses[node] = response
                # TODO: Handle response wherein node already had a copy of this TreasureMap.  341
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

        # TODO
        # if len(self._accepted_arrangements) < self.n:
        #     raise self.MoreKFragsThanArrangements("Not enough candidate arrangements. "
        #                                           "Call make_arrangements to make more.")

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
            self.alice.active_policies[bytes(self.public_key).hex()] = self

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

            except NodeSeemsToBeDown:  # TODO: Also catch InvalidNode here?  355
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
        return self.message_kit.sender_pubkey_sig

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
        self.destinations[arrangement.ursula.checksum_public_address] = arrangement.id

    def public_id(self):
        """
        We need an ID that Bob can glean from knowledge he already has *and* which Ursula can verify came from Alice.
        Ursula will refuse to propagate this if it she can't prove the payload is signed by Alice's public key,
        which is included in it,
        """
        return keccak_digest(bytes(self._verifying_key) + bytes(self._hrac)).hex()

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

    class NotFromBob(InvalidSignature):
        def __init__(self):
            super().__init__("This doesn't appear to be from Bob.")

    def __init__(self,
                 bob: Bob,
                 arrangement_id,
                 capsules: List[Capsule],
                 capsule_signatures: List[Signature],
                 alice_address: bytes,
                 alice_address_signature: bytes,
                 receipt_bytes: bytes,
                 receipt_signature,
                 ursula=None,
                 ) -> None:
        self.bob = bob
        self.arrangement_id = arrangement_id
        self.capsules = capsules
        self.capsule_signatures = capsule_signatures
        self.alice_address = alice_address
        self.alice_address_signature = alice_address_signature
        self.receipt_bytes = receipt_bytes
        self.receipt_signature = receipt_signature
        self.ursula = ursula  # TODO: We may still need a more elegant system for ID'ing Ursula.  See #136.
        self.completed = False

    def __repr__(self):
        return "WorkOrder for hrac {hrac}: (capsules: {capsule_bytes}) for Ursula: {node}".format(
            hrac=self.arrangement_id.hex()[:6],
            capsule_bytes=[binascii.hexlify(bytes(cap))[:6] for cap in self.capsules],
            node=binascii.hexlify(bytes(self.ursula.stamp))[:6])

    def __eq__(self, other):
        return (self.receipt_bytes, self.receipt_signature) == (
            other.receipt_bytes, other.receipt_signature)

    def __len__(self):
        return len(self.capsules)

    @classmethod
    def construct_by_bob(cls, arrangement_id, capsules, ursula, bob):
        alice_verifying_key = capsules[0].get_correctness_keys()["verifying"]

        capsules_bytes = []
        capsule_signatures = []
        for capsule in capsules:
            if alice_verifying_key != capsule.get_correctness_keys()["verifying"]:
                raise ValueError("Capsules in this work order are inconsistent.")
            capsule_bytes = bytes(capsule)
            capsules_bytes.append(capsule_bytes)
            capsule_signatures.append(bob.stamp(capsule_bytes))

        alice_address = canonical_address_from_umbral_key(alice_verifying_key)
        alice_address_signature = bytes(bob.stamp(alice_address))

        receipt_bytes = b"wo:" + ursula.canonical_public_address
        receipt_bytes += msgpack.dumps(capsules_bytes)
        receipt_signature = bob.stamp(receipt_bytes)

        return cls(bob, arrangement_id, capsules, capsule_signatures,
                   alice_address, alice_address_signature,
                   receipt_bytes, receipt_signature, ursula)

    @classmethod
    def from_rest_payload(cls, arrangement_id, rest_payload):

        # TODO: Use JSON instead? This is a mess.
        payload_splitter = BytestringSplitter(Signature) + key_splitter
        signature, bob_pubkey_sig, remainder = payload_splitter(rest_payload,
                                                                msgpack_remainder=True)

        receipt_bytes, *remainder = remainder
        packed_capsules, packed_signatures, *remainder = remainder
        alice_address, alice_address_signature = remainder
        alice_address_signature = Signature.from_bytes(alice_address_signature)
        if not alice_address_signature.verify(alice_address, bob_pubkey_sig):
            raise cls.NotFromBob()

        capsules, capsule_signatures = list(), list()
        for capsule_bytes, capsule_signature in zip(msgpack.loads(packed_capsules), msgpack.loads(packed_signatures)):
            capsules.append(Capsule.from_bytes(capsule_bytes, params=default_params()))
            capsule_signature = Signature.from_bytes(capsule_signature)
            capsule_signatures.append(capsule_signature)
            if not capsule_signature.verify(capsule_bytes, bob_pubkey_sig):
                raise cls.NotFromBob()

        verified = signature.verify(receipt_bytes, bob_pubkey_sig)
        if not verified:
            raise cls.NotFromBob()
        bob = Bob.from_public_keys({SigningPower: bob_pubkey_sig})
        return cls(bob, arrangement_id, capsules, capsule_signatures,
                   alice_address, alice_address_signature,
                   receipt_bytes, signature)

    def payload(self):
        capsules_as_bytes = [bytes(p) for p in self.capsules]
        capsule_signatures_as_bytes = [bytes(s) for s in self.capsule_signatures]
        packed_receipt_and_capsules = msgpack.dumps(
            (self.receipt_bytes,
             msgpack.dumps(capsules_as_bytes),
             msgpack.dumps(capsule_signatures_as_bytes),
             self.alice_address,
             self.alice_address_signature,
             )
        )
        return bytes(self.receipt_signature) + self.bob.stamp + packed_receipt_and_capsules

    def complete(self, cfrags_and_signatures):
        good_cfrags = []
        if not len(self) == len(cfrags_and_signatures):
            raise ValueError("Ursula gave back the wrong number of cfrags.  "
                             "She's up to something.")

        alice_address_signature = bytes(self.alice_address_signature)
        ursula_verifying_key = self.ursula.stamp.as_umbral_pubkey()

        for counter, capsule in enumerate(self.capsules):
            cfrag, signature = cfrags_and_signatures[counter]

            # Validate CFrag metadata
            capsule_signature = bytes(self.capsule_signatures[counter])
            metadata_input = capsule_signature + alice_address_signature
            metadata_as_signature = Signature.from_bytes(cfrag.proof.metadata)
            if not metadata_as_signature.verify(metadata_input, ursula_verifying_key):
                raise InvalidSignature("Invalid metadata for {}.".format(cfrag))

            # Validate work order response signatures
            if signature.verify(bytes(cfrag) + bytes(capsule), ursula_verifying_key):
                good_cfrags.append(cfrag)
            else:
                raise InvalidSignature("{} is not properly signed by Ursula.".format(cfrag))
        else:
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


class IndisputableEvidence:

    def __init__(self,
                 capsule: Capsule,
                 cfrag: CapsuleFrag,
                 ursula,
                 delegating_pubkey: UmbralPublicKey = None,
                 receiving_pubkey: UmbralPublicKey = None,
                 verifying_pubkey: UmbralPublicKey = None,
                 ) -> None:
        self.capsule = capsule
        self.cfrag = cfrag
        self.ursula = ursula

        keys = capsule.get_correctness_keys()
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

    def get_proof_challenge_scalar(self) -> CurveBN:
        umbral_params = default_params()
        e, v, _ = self.capsule.components()

        e1 = self.cfrag.point_e1
        v1 = self.cfrag.point_v1
        e2 = self.cfrag.proof.point_e2
        v2 = self.cfrag.proof.point_v2
        u = umbral_params.u
        u1 = self.cfrag.proof.point_kfrag_commitment
        u2 = self.cfrag.proof.point_kfrag_pok
        metadata = self.cfrag.proof.metadata

        from umbral.random_oracles import hash_to_curvebn, ExtendedKeccak

        hash_input = (e, e1, e2, v, v1, v2, u, u1, u2, metadata)

        h = hash_to_curvebn(*hash_input,
                            params=umbral_params,
                            hash_class=ExtendedKeccak)
        return h

    def precompute_values(self) -> bytes:

        umbral_params = default_params()
        e, v, _ = self.capsule.components()

        e1 = self.cfrag.point_e1
        v1 = self.cfrag.point_v1
        e2 = self.cfrag.proof.point_e2
        v2 = self.cfrag.proof.point_v2
        u = umbral_params.u
        u1 = self.cfrag.proof.point_kfrag_commitment
        u2 = self.cfrag.proof.point_kfrag_pok

        h = self.get_proof_challenge_scalar()

        e1h = h * e1
        v1h = h * v1
        u1h = h * u1

        z = self.cfrag.proof.bn_sig
        ez = z * e
        vz = z * v
        uz = z * u

        def raw_bytes_from_point(point: Point, only_y_coord=False) -> bytes:
            uncompressed_point_bytes = point.to_bytes(is_compressed=False)
            if only_y_coord:
                y_coord_start = (1 + Point.expected_bytes_length(is_compressed=False)) // 2
                return uncompressed_point_bytes[y_coord_start:]
            else:
                return uncompressed_point_bytes[1:]

        # E points
        e_y = raw_bytes_from_point(e, only_y_coord=True)
        ez_xy = raw_bytes_from_point(ez)
        e1_y = raw_bytes_from_point(e1, only_y_coord=True)
        e1h_xy = raw_bytes_from_point(e1h)
        e2_y = raw_bytes_from_point(e2, only_y_coord=True)
        # V points
        v_y = raw_bytes_from_point(v, only_y_coord=True)
        vz_xy = raw_bytes_from_point(vz)
        v1_y = raw_bytes_from_point(v1, only_y_coord=True)
        v1h_xy = raw_bytes_from_point(v1h)
        v2_y = raw_bytes_from_point(v2, only_y_coord=True)
        # U points
        uz_xy = raw_bytes_from_point(uz)
        u1_y = raw_bytes_from_point(u1, only_y_coord=True)
        u1h_xy = raw_bytes_from_point(u1h)
        u2_y = raw_bytes_from_point(u2, only_y_coord=True)

        # Get hashed KFrag validity message
        hash_function = hashes.Hash(hashes.SHA256(), backend=backend)

        kfrag_id = self.cfrag.kfrag_id
        precursor = self.cfrag.point_precursor
        delegating_pubkey = self.delegating_pubkey
        receiving_pubkey = self.receiving_pubkey

        validity_input = (kfrag_id, delegating_pubkey, receiving_pubkey, u1, precursor)
        kfrag_validity_message = bytes().join(bytes(item) for item in validity_input)
        hash_function.update(kfrag_validity_message)
        hashed_kfrag_validity_message = hash_function.finalize()

        # Get Alice's verifying pubkey as ETH address
        alice_address = canonical_address_from_umbral_key(self.verifying_pubkey)

        # Get KFrag signature's v value
        v_value = 27
        pubkey_bytes = recover_pubkey_from_signature(prehashed_message=hashed_kfrag_validity_message,
                                                     signature=self.cfrag.proof.kfrag_signature,
                                                     v_value_to_try=v_value)
        if not pubkey_bytes == self.verifying_pubkey.to_bytes():
            v_value = 28
            pubkey_bytes = recover_pubkey_from_signature(prehashed_message=hashed_kfrag_validity_message,
                                                         signature=self.cfrag.proof.kfrag_signature,
                                                         v_value_to_try=v_value)
        if not pubkey_bytes == self.verifying_pubkey.to_bytes():
            raise InvalidSignature("Bad signature: Not possible to recover public key from it.")

        # Bundle everything together
        pieces = (
            e_y, ez_xy, e1_y, e1h_xy, e2_y,
            v_y, vz_xy, v1_y, v1h_xy, v2_y,
            uz_xy, u1_y, u1h_xy, u2_y,
            hashed_kfrag_validity_message,
            alice_address,
            v_value.to_bytes(1, 'big'),
        )
        return b''.join(pieces)
