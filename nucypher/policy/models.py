import binascii
import uuid
from collections import OrderedDict

import maya
import msgpack
from bytestring_splitter import BytestringSplitter
from constant_sorrow import constants

from nucypher.blockchain.eth.agents import MinerAgent
from nucypher.characters import Alice
from nucypher.characters import Bob, Ursula
from nucypher.crypto.api import keccak_digest
from nucypher.crypto.constants import KECCAK_DIGEST_LENGTH
from nucypher.crypto.powers import SigningPower
from nucypher.crypto.signing import Signature
from nucypher.crypto.splitters import key_splitter
from umbral.config import default_params
from umbral.pre import Capsule


class Arrangement:
    """
    A Policy must be implemented by arrangements with n Ursulas.  This class tracks the status of that implementation.
    """
    splitter = key_splitter + BytestringSplitter((bytes, KECCAK_DIGEST_LENGTH),
                                                 (bytes, 27))

    def __init__(self, alice, hrac, expiration, ursula=None,
                 kfrag=constants.UNKNOWN_KFRAG, alices_signature=None):
        """
        :param deposit: Funds which will pay for the timeframe  of this Arrangement (not the actual re-encryptions);
            a portion will be locked for each Ursula that accepts.
        :param expiration: The moment which Alice wants the Arrangement to end.

        Other params are hopefully self-evident.
        """
        self.expiration = expiration
        self.hrac = hrac
        self.alice = alice
        self.uuid = uuid.uuid4()

        """
        These will normally not be set if Alice is drawing up this arrangement - she hasn't assigned a kfrag yet
        (because she doesn't know if this Arrangement will be accepted).  She doesn't have an Ursula, for the same reason.
        """
        self.kfrag = kfrag
        self.ursula = ursula

        arrangement_delta = maya.now() - self.expiration
        policy_duration = arrangement_delta.days
        #
        # super().__init__(author=self.alice, miner=ursula,
        #                  value=self.deposit, lock_periods=policy_duration,
        #                  arrangement_id=self.id())

    def __bytes__(self):
        return bytes(self.alice.stamp) + bytes(
            self.hrac) + self.expiration.iso8601().encode()

    def id(self):
        if not self.ursula:
            raise TypeError("Can't make an ID for this arrangement yet as we don't know the Ursula.")
        id_nugget = keccak_digest(self.ursula + self.uuid)
        full_id = keccak_digest(self.alice.stamp + id_nugget)
        return id_nugget, full_id

    @classmethod
    def from_bytes(cls, arrangement_as_bytes):
        # Still unclear how to arrive at the correct number of bytes to represent a deposit.  See #148.
        alice_pubkey_sig, hrac, expiration_bytes = cls.splitter(arrangement_as_bytes)
        expiration = maya.parse(expiration_bytes.decode())
        alice = Alice.from_public_keys({SigningPower: alice_pubkey_sig})
        return cls(alice=alice, hrac=hrac, expiration=expiration)

    def publish(self):
        """
        Publish arrangement to blockchain

        # TODO Negotiate the receipt of a KFrag per Ursula
        """
        super().publish()

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


class Policy:
    """
    An edict by Alice, arranged with n Ursulas, to perform re-encryption for a specific Bob
    for a specific path.

    Once Alice is ready to enact a Policy, she generates KFrags, which become part of the Policy.

    Each Ursula is offered a Arrangement (see above) for a given Policy by Alice.

    Once Alice has secured agreement with n Ursulas to enact a Policy, she sends each a KFrag,
    and generates a TreasureMap for the Policy, recording which Ursulas got a KFrag.
    """
    _ursula = None

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
        self._accepted_arrangements = list()
        self._rejected_arrangements = list()

        self._enacted_arrangements = OrderedDict()
        self._published_arrangements = OrderedDict()

        self.alices_signature = alices_signature
        self.arrangements = dict()

    class MoreKFragsThanArrangements(TypeError):
        """
        Raised when a Policy has been used to generate Arrangements with Ursulas insufficient number
        such that we don't have enough KFrags to give to each Ursula.
        """

    @property
    def n(self):
        return len(self.kfrags)

    @property
    def ursula(self):
        if not self._ursula:
            raise Ursula.NotFound
        else:
            return self._ursula

    @ursula.setter
    def ursula(self, ursula_object):
        self.alice.learn_about_actor(ursula_object)
        self._ursula = ursula_object

    @staticmethod
    def from_alice(kfrags,
                   alice,
                   label,
                   bob,
                   public_key,
                   m,
                   ):
        # TODO: What happened to Alice's signature - don't we include it here?
        policy = Policy(alice, label, bob, kfrags, public_key, m)

        return policy

    def hrac(self):
        """
        The "hashed resource authentication code".

        A hash of:
        * Alice's public key
        * Bob's public key
        * the uri

        Alice and Bob have all the information they need to construct this.
        Ursula does not, so we share it with her.
        """
        return keccak_digest(bytes(self.alice.stamp) + bytes(self.bob.stamp) + self.label)

    def treasure_map_dht_key(self):
        """
        We need a key that Bob can glean from knowledge he already has *and* which Ursula can verify came from us.
        Ursula will refuse to propagate this key if it she can't prove that our public key, which is included in it,
        was used to sign the payload.

        Our public key (which everybody knows) and the hrac above.
        """
        return keccak_digest(bytes(self.alice.stamp) + self.hrac())

    def publish_treasure_map(self, network_middleare=None, use_dht=False):
        if network_middleare is None and use_dht is False:
            raise ValueError("Can't engage the REST swarm without networky stuff.")
        tmap_message_kit, signature_for_bob = self.alice.encrypt_for(
            self.bob,
            self.treasure_map.packed_payload())
        signature_for_ursula = self.alice.stamp(self.hrac())

        # In order to know this is safe to propagate, Ursula needs to see a signature, our public key,
        # and, reasons explained in treasure_map_dht_key above, the uri_hash.
        # TODO: Clean this up.  See #172.
        map_payload = signature_for_ursula + self.alice.stamp + self.hrac() + tmap_message_kit.to_bytes()
        map_id = self.treasure_map_dht_key()

        if not self.alice.known_nodes:
            raise RuntimeError("Alice hasn't learned of any nodes.  Thus, she can't push the TreasureMap.")

        for node in self.alice.known_nodes.values():
            response = network_middleare.push_treasure_map_to_node(node, map_id,
                                                                   constants.BYTESTRING_IS_TREASURE_MAP + map_payload)
            # TODO: Do something here based on success or failure
            if response.status_code == 204:
                pass

        return tmap_message_kit, map_payload, signature_for_bob, signature_for_ursula

    def publish(self) -> None:
        """Publish enacted arrangements to the blockchain"""
        while len(self._enacted_arrangements) > 0:
            kfrag, arrangement = self._enacted_arrangements.popitem()
            arrangement.publish(arrangement.kfrag)  # TODO

    def __assign_kfrags(self):

        if len(self._accepted_arrangements) < self.n:
            raise self.MoreKFragsThanArrangements("Not enough candidate arrangements. "
                                                  "Call make_arrangements to make more.")

        for kfrag in self.kfrags:
            for arrangement, in self._accepted_arrangements:
                if kfrag not in self._enacted_arrangements:
                    arrangement.kfrag = kfrag
                    yield arrangement
                    self._enacted_arrangements[kfrag] = arrangement

    def enact(self, network_middleware):
        """Assign kfrags to ursulas, and distribute them via REST, populating enacted_arrangements"""
        for arrangement in self.__assign_kfrags():
            policy_message_kit = arrangement.encrypt_payload_for_ursula()

            response = network_middleware.enact_policy(arrangement.ursula,
                                                       self.hrac(),
                                                       policy_message_kit.to_bytes())

            # TODO: What if there weren't enough Arrangements approved to distribute n kfrags?
            # We need to raise NotEnoughQualifiedUrsulas.

            # TODO: Parse response for confirmation.
            response

            # Assuming response is what we hope for
            self.treasure_map.add_ursula(arrangement.ursula)

    def make_arrangements(self, network_middleware, quantity: int,
                          deposit: int, expiration: maya.MayaDT) -> None:
        """
        Create and consider n Arangement objects from sampled miners.
        """
        try:
            sampled_miners = self.alice.recruit(quantity=quantity or self.n)
        except MinerAgent.NotEnoughMiners:
            raise  # TODO

        for miner in sampled_miners:

            # Cast the miner into an ursula
            ursula = Ursula(is_me=False, ether_address=miner.ether_address)
            arrangement = Arrangement(alice=self.alice, ursula=ursula,
                                      hrac=self.hrac(),
                                      expiration=expiration)

            try:
                # TODO: check out the response: need to assess the result and see if we're actually good to go.
                ursula, negotiation_result = network_middleware.consider_arrangement(arrangement)
                bucket = self._accepted_arrangements if negotiation_result is True else self._rejected_arrangements
                bucket.append(arrangement)
            except network_middleware.NotEnoughQualifiedUrsulas:
                raise  # TODO: Tell Alice to either wait or lower the value of num_ursulas.


class TreasureMap(object):
    def __init__(self, m, ursula_interface_ids=None):
        self.m = m
        self.ids = set(ursula_interface_ids or set())

    def packed_payload(self):
        return msgpack.dumps(self.nodes_as_bytes() + [self.m])

    def nodes_as_bytes(self):
        return [bytes(ursula_id) for ursula_id in self.ids]

    def add_ursula(self, ursula):
        self.ids.add(bytes(ursula.stamp))

    def __eq__(self, other):
        return self.ids == other.ids

    def __iter__(self):
        return iter(self.ids)

    def __len__(self):
        return len(self.ids)


class WorkOrder(object):
    def __init__(self, bob, kfrag_hrac, capsules, receipt_bytes,
                 receipt_signature, ursula=None):
        self.bob = bob
        self.kfrag_hrac = kfrag_hrac
        self.capsules = capsules
        self.receipt_bytes = receipt_bytes
        self.receipt_signature = receipt_signature
        self.ursula = ursula  # TODO: We may still need a more elegant system for ID'ing Ursula.  See #136.

    def __repr__(self):
        return "WorkOrder for hrac {hrac}: (capsules: {capsule_bytes}) for {ursulas}".format(
            hrac=self.kfrag_hrac.hex()[:6],
            capsule_bytes=[binascii.hexlify(bytes(cap))[:6] for cap in self.capsules],
            ursulas=binascii.hexlify(bytes(self.ursula.stamp))[:6])

    def __eq__(self, other):
        return (self.receipt_bytes, self.receipt_signature) == (
            other.receipt_bytes, other.receipt_signature)

    def __len__(self):
        return len(self.capsules)

    @classmethod
    def construct_by_bob(cls, kfrag_hrac, capsules, ursula, bob):
        receipt_bytes = b"wo:" + ursula.interface_information()  # TODO: represent the capsules as bytes and hash them as part of the receipt, ie  + keccak_digest(b"".join(capsules))  - See #137
        receipt_signature = bob.stamp(receipt_bytes)
        return cls(bob, kfrag_hrac, capsules, receipt_bytes, receipt_signature,
                   ursula)

    @classmethod
    def from_rest_payload(cls, kfrag_hrac, rest_payload):
        payload_splitter = BytestringSplitter(Signature) + key_splitter
        signature, bob_pubkey_sig, (receipt_bytes, packed_capsules) = payload_splitter(rest_payload,
                                                                                       msgpack_remainder=True)
        capsules = [Capsule.from_bytes(p, params=default_params()) for p in msgpack.loads(packed_capsules)]
        verified = signature.verify(receipt_bytes, bob_pubkey_sig)
        if not verified:
            raise ValueError("This doesn't appear to be from Bob.")
        bob = Bob.from_public_keys({SigningPower: bob_pubkey_sig})
        return cls(bob, kfrag_hrac, capsules, receipt_bytes, signature)

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
        for ursula, pfrags in self.by_ursula.items():
            for saved_pfrag, work_order in pfrags.items():
                if saved_pfrag == capsule:
                    ursulas_by_capsules[ursula] = work_order
        return ursulas_by_capsules
