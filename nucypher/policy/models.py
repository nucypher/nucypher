"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""
import binascii
import os
from abc import abstractmethod
from collections import OrderedDict

import maya
import msgpack
import uuid
from bytestring_splitter import BytestringSplitter, VariableLengthBytestring
from constant_sorrow import constants
from eth_utils import to_canonical_address, to_checksum_address
from typing import Generator, List, Set
from umbral.config import default_params
from umbral.pre import Capsule

from nucypher.characters.lawful import Alice
from nucypher.characters.lawful import Bob, Ursula, Character
from nucypher.crypto.api import keccak_digest, encrypt_and_sign, secure_random
from nucypher.crypto.constants import PUBLIC_ADDRESS_LENGTH, KECCAK_DIGEST_LENGTH
from nucypher.crypto.kits import UmbralMessageKit, RevocationKit
from nucypher.crypto.powers import SigningPower, DecryptingPower
from nucypher.crypto.signing import Signature, InvalidSignature
from nucypher.crypto.splitters import key_splitter
from nucypher.network.middleware import RestMiddleware


class Arrangement:
    """
    A Policy must be implemented by arrangements with n Ursulas.  This class tracks the status of that implementation.
    """
    federated = True
    ID_LENGTH = 32

    splitter = key_splitter + BytestringSplitter((bytes, ID_LENGTH),
                                                 (bytes, 27))

    def __init__(self, alice, expiration, ursula=None, id=None,
                 kfrag=constants.UNKNOWN_KFRAG, value=None, alices_signature=None) -> None:
        """
        :param deposit: Funds which will pay for the timeframe  of this Arrangement (not the actual re-encryptions);
            a portion will be locked for each Ursula that accepts.
        :param expiration: The moment which Alice wants the Arrangement to end.

        Other params are hopefully self-evident.
        """
        self.id = id or secure_random(self.ID_LENGTH)
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
        alice_pubkey_sig, id, expiration_bytes = cls.splitter(arrangement_as_bytes)
        expiration = maya.parse(expiration_bytes.decode())
        alice = Alice.from_public_keys({SigningPower: alice_pubkey_sig})
        return cls(alice=alice, id=id, expiration=expiration)

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

    def publish(self):
        """
        Publish arrangement.
        """
        raise NotImplementedError

    @abstractmethod
    def revoke(self):
        """
        Publish arrangement.
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
                 kfrags=(constants.UNKNOWN_KFRAG,),
                 public_key=None,
                 m: int = None,
                 alices_signature=constants.NOT_SIGNED) -> None:

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
            response = network_middleware.put_treasure_map_on_node(node,
                                                                   self.treasure_map.public_id(),
                                                                   bytes(self.treasure_map)
                                                                   )  # TODO: Certificate filepath needs to be looked up and passed here
            if response.status_code == 202:
                responses[node] = response
                # TODO: Handle response wherein node already had a copy of this TreasureMap.  341
            else:
                # TODO: Do something useful here.
                raise RuntimeError

        return responses

    def publish(self, network_middleware: RestMiddleware) -> dict:
        """Spread word of this Policy far and wide."""
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
            self.revocation_kit = RevocationKit(self.treasure_map,
                                                self.alice.stamp)

            if publish is True:
                return self.publish(network_middleware)

    def consider_arrangement(self, network_middleware, ursula, arrangement):
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
        negotiation_result = negotiation_response.status_code == 200

        bucket = self._accepted_arrangements if negotiation_result is True else self._rejected_arrangements
        bucket.add(arrangement)

        return negotiation_result

    @abstractmethod
    def make_arrangements(self,
                          network_middleware: RestMiddleware,
                          deposit: int,
                          expiration: maya.MayaDT,
                          ursulas: Set[Ursula] = None) -> None:
        """
        Create and consider n Arangement objects.
        """
        raise NotImplementedError

    def _consider_arrangements(self,
                               network_middleware: RestMiddleware,
                               candidate_ursulas: Set[Ursula],
                               deposit: int,
                               expiration: maya.MayaDT):

        for selected_ursula in candidate_ursulas:
            arrangement = self._arrangement_class(alice=self.alice,
                                                  ursula=selected_ursula,
                                                  value=deposit,
                                                  expiration=expiration,
                                                  )

            self.consider_arrangement(ursula=selected_ursula,
                                      arrangement=arrangement,
                                      network_middleware=network_middleware)


class FederatedPolicy(Policy):
    _arrangement_class = Arrangement

    def __init__(self, ursulas: Set[Ursula], *args, **kwargs) -> None:
        self.ursulas = ursulas
        super().__init__(*args, **kwargs)

    def make_arrangements(self,
                          network_middleware: RestMiddleware,
                          deposit: int,
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
                                    deposit=deposit,
                                    expiration=expiration)

        if len(self._accepted_arrangements) < self.n:
            raise self.MoreKFragsThanArrangements


class TreasureMap:
    splitter = BytestringSplitter(Signature,
                                  (bytes, KECCAK_DIGEST_LENGTH),  # hrac
                                  (UmbralMessageKit, VariableLengthBytestring)
                                  )
    node_id_splitter = BytestringSplitter((to_checksum_address, int(PUBLIC_ADDRESS_LENGTH)), Arrangement.ID_LENGTH)

    from nucypher.crypto.signing import InvalidSignature  # Raised when the public signature (typically intended for Ursula) is not valid.

    def __init__(self,
                 m: int = None,
                 destinations=None,
                 message_kit: UmbralMessageKit= None,
                 public_signature: Signature = None,
                 hrac=None) -> None:

        if m is not None:
            if m > 255:
                raise ValueError("Largest allowed value for m is 255.")
            self._m = m

            self._destinations = destinations or {}
        else:
            self._m = constants.NO_DECRYPTION_PERFORMED
            self._destinations = constants.NO_DECRYPTION_PERFORMED

        self.message_kit = message_kit
        self._signature_for_bob = None
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
        if self._m == constants.NO_DECRYPTION_PERFORMED:
            raise TypeError("The TreasureMap is probably encrypted. You must decrypt it first.")
        return self._m

    @property
    def destinations(self):
        if self._destinations == constants.NO_DECRYPTION_PERFORMED:
            raise TypeError("The TreasureMap is probably encrypted. You must decrypt it first.")
        return self._destinations

    def nodes_as_bytes(self):
        if self.destinations == constants.NO_DECRYPTION_PERFORMED:
            return constants.NO_DECRYPTION_PERFORMED
        else:
            return bytes().join(to_canonical_address(ursula_id) + arrangement_id for ursula_id, arrangement_id in self.destinations.items())

    def add_arrangement(self, arrangement):
        if self.destinations == constants.NO_DECRYPTION_PERFORMED:
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
        signature, hrac, tmap_message_kit = \
            cls.splitter(bytes_representation)

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
    def __init__(self,
                 bob,
                 arrangement_id,
                 capsules,
                 capsule_signatures,
                 receipt_bytes,
                 receipt_signature,
                 ursula=None,
                 ) -> None:
        self.bob = bob
        self.arrangement_id = arrangement_id
        self.capsules = capsules
        self.capsule_signatures = capsule_signatures
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
        capsules_bytes = [bytes(c) for c in capsules]
        receipt_bytes = b"wo:" + ursula.canonical_public_address
        receipt_bytes += msgpack.dumps(capsules_bytes)
        receipt_signature = bob.stamp(receipt_bytes)
        capsule_signatures = [bob.stamp(c) for c in capsules_bytes]
        return cls(bob, arrangement_id, capsules, capsule_signatures, receipt_bytes, receipt_signature,
                   ursula)

    @classmethod
    def from_rest_payload(cls, arrangement_id, rest_payload):
        payload_splitter = BytestringSplitter(Signature) + key_splitter
        signature, bob_pubkey_sig, \
            (receipt_bytes, packed_capsules, packed_signatures) = payload_splitter(rest_payload,
                                                                                   msgpack_remainder=True)
        capsules, capsule_signatures = list(), list()
        for capsule_bytes, signed_capsule in zip(msgpack.loads(packed_capsules), msgpack.loads(packed_signatures)):
            capsules.append(Capsule.from_bytes(capsule_bytes, params=default_params()))
            signed_capsule = Signature.from_bytes(signed_capsule)
            capsule_signatures.append(signed_capsule)
            if not signed_capsule.verify(capsule_bytes, bob_pubkey_sig):
                raise ValueError("This doesn't appear to be from Bob.")

        verified = signature.verify(receipt_bytes, bob_pubkey_sig)
        if not verified:
            raise ValueError("This doesn't appear to be from Bob.")
        bob = Bob.from_public_keys({SigningPower: bob_pubkey_sig})
        return cls(bob, arrangement_id, capsules, capsule_signatures, receipt_bytes, signature)

    def payload(self):
        capsules_as_bytes = [bytes(p) for p in self.capsules]
        capsule_signatures_as_bytes = [bytes(s) for s in self.capsule_signatures]
        packed_receipt_and_capsules = msgpack.dumps(
            (self.receipt_bytes, msgpack.dumps(capsules_as_bytes), msgpack.dumps(capsule_signatures_as_bytes)))
        return bytes(self.receipt_signature) + self.bob.stamp + packed_receipt_and_capsules

    def complete(self, cfrags_and_signatures):
        good_cfrags = []
        if not len(self) == len(cfrags_and_signatures):
            raise ValueError("Ursula gave back the wrong number of cfrags.  She's up to something.")
        for counter, capsule in enumerate(self.capsules):
            cfrag, signature = cfrags_and_signatures[counter]
            if signature.verify(bytes(cfrag) + bytes(capsule), self.ursula.stamp.as_umbral_pubkey()):
                good_cfrags.append(cfrag)
            else:
                raise self.ursula.InvalidSignature("This CFrag is not properly signed by Ursula.")
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

    def by_capsule(self, capsule):
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
