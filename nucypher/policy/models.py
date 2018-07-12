import binascii
import uuid
from abc import abstractmethod
from collections import OrderedDict
from typing import Generator, List, Set

import maya
import msgpack

from bytestring_splitter import BytestringSplitter, VariableLengthBytestring
from constant_sorrow import constants
from nucypher.characters import Alice
from nucypher.characters import Bob, Ursula
from nucypher.crypto.api import keccak_digest, encrypt_and_sign, secure_random
from nucypher.crypto.constants import PUBLIC_ADDRESS_LENGTH, KECCAK_DIGEST_LENGTH
from nucypher.crypto.kits import UmbralMessageKit
from nucypher.crypto.powers import SigningPower, EncryptingPower
from nucypher.crypto.signing import Signature
from nucypher.crypto.splitters import key_splitter
from umbral.config import default_params
from umbral.pre import Capsule


class Arrangement:
    """
    A Policy must be implemented by arrangements with n Ursulas.  This class tracks the status of that implementation.
    """
    federated = True
    ID_LENGTH = 32

    splitter = key_splitter + BytestringSplitter((bytes, ID_LENGTH),
                                                 (bytes, 27))

    def __init__(self, alice, expiration, ursula=None, id=None,
                 kfrag=constants.UNKNOWN_KFRAG, value=None, alices_signature=None):
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

    def __init__(self, alice, label, bob=None, kfrags=(constants.UNKNOWN_KFRAG,),
                 public_key=None, m=None, alices_signature=constants.NOT_SIGNED):

        """
        :param kfrags:  A list of KFrags to distribute per this Policy.
        :param label: The identity of the resource to which Bob is granted access.
        """
        self.alice = alice
        self.label = label
        self.bob = bob
        self.kfrags = kfrags
        self.public_key = public_key
        self.treasure_map = TreasureMap(m=m)

        # Keep track of this stuff
        self._accepted_arrangements = set()
        self._rejected_arrangements = set()

        self._enacted_arrangements = OrderedDict()
        self._published_arrangements = OrderedDict()

        self.alices_signature = alices_signature

    class MoreKFragsThanArrangements(TypeError):
        """
        Raised when a Policy has been used to generate Arrangements with Ursulas insufficient number
        such that we don't have enough KFrags to give to each Ursula.
        """

    @property
    def n(self):
        return len(self.kfrags)

    def hrac(self):
        """
        This function is hanging on for dear life.  After 180 is closed, it can be completely deprecated.

        The "hashed resource authentication code".

        A hash of:
        * Alice's public key
        * Bob's public key
        * the uri

        Alice and Bob have all the information they need to construct this.
        Ursula does not, so we share it with her.
        """
        return keccak_digest(bytes(self.alice.stamp) + bytes(self.bob.stamp) + self.label)

    def publish_treasure_map(self, network_middleare):
        self.treasure_map.prepare_for_publication(self.bob.public_key(EncryptingPower),
                                                  self.bob.public_key(SigningPower),
                                                  self.alice.stamp,
                                                  self.label
                                                  )
        if not self.alice._known_nodes:
            # TODO: Optionally block.
            raise RuntimeError("Alice hasn't learned of any nodes.  Thus, she can't push the TreasureMap.")

        responses = {}

        for node in self.alice._known_nodes.values():
            # TODO: It's way overkill to push this to every node we know about.  Come up with a system.  342
            response = network_middleare.put_treasure_map_on_node(node,
                                                                  self.treasure_map.public_id(),
                                                                  bytes(self.treasure_map)
                                                                  )
            if response.status_code == 202:
                responses[node] = response
                # TODO: Handle response wherein node already had a copy of this TreasureMap.  341
            else:
                # TODO: Do something useful here.
                raise RuntimeError

        return responses

    def publish(self, network_middleware) -> None:
        """Spread word of this Policy far and wide."""
        self.publish_treasure_map(network_middleare=network_middleware)

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

    def enact(self, network_middleware, publish=True) -> None:
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
            if publish is True:
                self.publish(network_middleware)

    def consider_arrangement(self, network_middleware, ursula, arrangement):

        try:
            ursula.verify_node(network_middleware, accept_federated_only=arrangement.federated)
        except ursula.InvalidNode:
            # TODO: What do we actually do here?  Report this at least (355)?  Maybe also have another bucket for invalid nodes?
            # It's possible that nothing sordid is happening here; this node may be updating its interface info or rotating a signing key
            #  and we learned about a previous one.
            raise

        negotiation_response = network_middleware.consider_arrangement(arrangement=arrangement)

        # TODO: check out the response: need to assess the result and see if we're actually good to go.
        negotiation_result = negotiation_response.status_code == 200

        bucket = self._accepted_arrangements if negotiation_result is True else self._rejected_arrangements
        bucket.add(arrangement)

        return negotiation_result

    @abstractmethod
    def make_arrangements(self, network_middleware,
                          deposit: int,
                          expiration: maya.MayaDT,
                          ursulas: List[Ursula] = None) -> None:
        """
        Create and consider n Arangement objects.
        """
        raise NotImplementedError

    def _consider_arrangements(self, network_middleware, candidate_ursulas: Set[Ursula],
                               deposit: int, expiration: maya.MayaDT) -> tuple:

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

    def __init__(self, ursulas: Set[Ursula], *args, **kwargs):
        self.ursulas = ursulas
        super().__init__(*args, **kwargs)

    def make_arrangements(self, network_middleware,
                          deposit: int,
                          expiration: maya.MayaDT,
                          ursulas: Set[Ursula] = None) -> None:
        if ursulas is None:
            ursulas = set()
        ursulas.update(self.ursulas)

        if len(ursulas) < self.n:
            raise ValueError(
                "To make a Policy in federated mode, you need to designate *all*\
                 the Ursulas you need (in this case, {}); there's no other way to\
                  know which nodes to use.  Either pass them here or when you make\
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
    node_id_splitter = BytestringSplitter(int(PUBLIC_ADDRESS_LENGTH), Arrangement.ID_LENGTH)

    class InvalidSignature(Exception):
        """Raised when the public signature (typically intended for Ursula) is not valid."""

    def __init__(self,
                 m=None,
                 destinations=None,
                 message_kit=None,
                 public_signature=None,
                 hrac=None):

        if m is not None:
            if m > 255:
                raise ValueError(
                    "Largest allowed value for m is 255.  Why the heck are you trying to make it larger than that anyway?  That's too big.")
            self.m = m
            self.destinations = destinations or {}
        else:
            self.m = constants.NO_DECRYPTION_PERFORMED
            self.destinations = constants.NO_DECRYPTION_PERFORMED

        self.message_kit = message_kit
        self._signature_for_bob = None
        self._public_signature = public_signature
        self._hrac = hrac
        self._payload = None

    def prepare_for_publication(self, bob_encrypting_key, bob_verifying_key, alice_stamp, label):
        plaintext = self.m.to_bytes(1, "big") + self.nodes_as_bytes()

        self.message_kit, _signature_for_bob = encrypt_and_sign(bob_encrypting_key,
                                                                plaintext=plaintext,
                                                                signer=alice_stamp,
                                                                )
        """
        Here's our "hashed resource authentication code".

        A hash of:
        * Alice's public key
        * Bob's public key
        * the uri

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

    def nodes_as_bytes(self):
        if self.destinations == constants.NO_DECRYPTION_PERFORMED:
            return constants.NO_DECRYPTION_PERFORMED
        else:
            return bytes().join(ursula_id + arrangement_id for ursula_id, arrangement_id in self.destinations.items())

    def add_arrangement(self, arrangement):
        if self.destinations == constants.NO_DECRYPTION_PERFORMED:
            raise TypeError("This TreasureMap is encrypted.  You can't add another node without decrypting it.")
        self.destinations[arrangement.ursula.canonical_public_address] = arrangement.id

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
        verified, map_in_the_clear = compass(message_kit=self.message_kit)
        if verified:
            self.m = map_in_the_clear[0]
            self.destinations = dict(self.node_id_splitter.repeat(map_in_the_clear[1:]))
        else:
            raise self.InvalidSignature(
                "This TreasureMap does not contain the correct signature from Alice to Bob.")

    def __eq__(self, other):
        return bytes(self) == bytes(other)

    def __iter__(self):
        return iter(self.destinations.items())

    def __len__(self):
        return len(self.destinations)


class WorkOrder(object):
    def __init__(self, bob, arrangement_id, capsules, receipt_bytes,
                 receipt_signature, ursula=None):
        self.bob = bob
        self.arrangement_id = arrangement_id
        self.capsules = capsules
        self.receipt_bytes = receipt_bytes
        self.receipt_signature = receipt_signature
        self.ursula = ursula  # TODO: We may still need a more elegant system for ID'ing Ursula.  See #136.

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
        receipt_bytes = b"wo:" + ursula.canonical_public_address  # TODO: represent the capsules as bytes and hash them as part of the receipt, ie  + keccak_digest(b"".join(capsules))  - See #137
        receipt_signature = bob.stamp(receipt_bytes)
        return cls(bob, arrangement_id, capsules, receipt_bytes, receipt_signature,
                   ursula)

    @classmethod
    def from_rest_payload(cls, arrangement_id, rest_payload):
        payload_splitter = BytestringSplitter(Signature) + key_splitter
        signature, bob_pubkey_sig, (receipt_bytes, packed_capsules) = payload_splitter(rest_payload,
                                                                                       msgpack_remainder=True)
        capsules = [Capsule.from_bytes(p, params=default_params()) for p in msgpack.loads(packed_capsules)]
        verified = signature.verify(receipt_bytes, bob_pubkey_sig)
        if not verified:
            raise ValueError("This doesn't appear to be from Bob.")
        bob = Bob.from_public_keys({SigningPower: bob_pubkey_sig})
        return cls(bob, arrangement_id, capsules, receipt_bytes, signature)

    def payload(self):
        capsules_as_bytes = [bytes(p) for p in self.capsules]
        packed_receipt_and_capsules = msgpack.dumps(
            (self.receipt_bytes, msgpack.dumps(capsules_as_bytes)))
        return bytes(self.receipt_signature) + self.bob.stamp + packed_receipt_and_capsules

    def complete(self, cfrags):
        # TODO: Verify that this is in fact complete - right number of CFrags and properly signed.
        # TODO: Mark it complete with datetime.
        pass


class WorkOrderHistory:

    def __init__(self):
        self.by_ursula = {}

    def __contains__(self, item):
        assert False

    def __getitem__(self, item):
        if isinstance(item, bytes):
            return self.by_ursula.setdefault(item, {})
        else:
            raise TypeError(
                "If you want to lookup a WorkOrder by Ursula, you need to pass bytes of her signing public key.")

    def __setitem__(self, key, value):
        assert False

    def __len__(self):
        return sum(len(work_orders) for work_orders in self.by_ursula.values())

    @property
    def ursulas(self):
        return self.by_ursula.keys()

    def by_capsule(self, capsule):
        ursulas_by_capsules = {}
        for ursula, capsules in self.by_ursula.items():
            for saved_capsule, work_order in capsules.items():
                if saved_capsule == capsule:
                    ursulas_by_capsules[ursula] = work_order
        return ursulas_by_capsules
