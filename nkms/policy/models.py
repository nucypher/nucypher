import asyncio
import binascii

import msgpack

from nkms.characters import Alice, Bob, Ursula
from nkms.crypto import api
from nkms.crypto.api import keccak_digest
from nkms.crypto.constants import NOT_SIGNED
from nkms.crypto.fragments import KFrag, PFrag
from nkms.crypto.powers import EncryptingPower
from nkms.crypto.signature import Signature
from nkms.crypto.utils import BytestringSplitter
from nkms.keystore.keypairs import PublicKey
from npre.constants import UNKNOWN_KFRAG

group_payload_splitter = BytestringSplitter(PublicKey)
policy_payload_splitter = BytestringSplitter(KFrag)


class PolicyOffer(object):
    """
    An offer from Alice to Ursula to enter into a contract for Re-Encryption services.
    """

    def __init__(self, n, deposit, contract_end_datetime):
        """
        :param n: The total number of Policies which Alice wishes to create.
        :param deposit: Funds which will pay for the timeframe  of the contract (not the actual re-encryptions);
            a portion will be locked for each Ursula that accepts.
        :param contract_end_datetime: The moment which Alice wants the contract to end.
        """
        self.n = n
        self.deposit = deposit
        self.contract_end_datetime = contract_end_datetime


class PolicyOfferResponse(object):
    pass


class PolicyManager(object):
    pass


class PolicyManagerForAlice(PolicyManager):
    def __init__(self, owner: Alice) -> None:
        self.owner = owner

    def create_policy_group(self,
                            bob: Bob,
                            uri: bytes,
                            m: int,
                            n: int,
                            ):
        """
        Alice dictates a new group of policies.
        """

        ##### Temporary until we decide on an API for private key access
        alice_priv_enc = self.owner._crypto_power._power_ups[EncryptingPower].priv_key
        kfrags, pfrag = self.owner.generate_rekey_frags(alice_priv_enc, bob, m,
                                                             n)  # TODO: Access Alice's private key inside this method.
        policy = Policy.from_alice(
            alice=self.owner,
            bob=bob,
            kfrags=kfrags,
            pfrag=pfrag,
            uri=uri,
        )

        return policy


class PolicyGroup(object):
    """
    The terms and conditions by which Alice shares with Bob.
    """

    _id = None

    def __init__(self, uri: bytes, alice: Alice, bob: Bob, policies=None) -> None:
        self.policies = policies or []
        self.alice = alice
        self.bob = bob
        self.uri = uri
        self.treasure_map = TreasureMap()

    @property
    def n(self):
        return len(self.policies)

    @staticmethod
    def hash(message):
        return keccak_digest(message)

    # TODO: This is a stand-in; remove it.
    @property
    def pfrag(self):
        return self.policies[0].pfrag

    def find_n_ursulas(self, networky_stuff, offer: PolicyOffer):
        """
        :param networky_stuff: A compliant interface (maybe a Client instance) to be used to engage the DHT swarm.
        """
        for policy in self.policies:
            try:
                ursula, result = networky_stuff.find_ursula(self.id, offer)
                # TODO: Here, we need to assess the result and see if we're actually good to go.
                if result.was_accepted:
                    policy.activate(ursula, result)
            except networky_stuff.NotEnoughQualifiedUrsulas:
                pass  # Tell Alice to either wait or lower the value of n.

    def hrac(self):
        """
        A convenience method for generating an hrac for this instance.
        """
        return self.hrac_for(self.alice, self.bob, self.uri)

    @staticmethod
    def hrac_for(alice, bob, uri):

        """
        The "hashed resource authentication code".

        A hash of:
        * Alice's public key
        * Bob's public key
        * the uri

        Alice and Bob have all the information they need to construct this.
        Ursula does not, so we share it with her.
        """
        return PolicyGroup.hash(bytes(alice.seal) + bytes(bob.seal) + uri)

    def craft_offer(self, deposit, expiration):
        return PolicyOffer(self.n, deposit, expiration)

    def treasure_map_dht_key(self):
        """
        We need a key that Bob can glean from knowledge he already has *and* which Ursula can verify came from us.
        Ursula will refuse to propagate this key if it she can't prove that our public key, which is included in it,
        was used to sign the payload.

        Our public key (which everybody knows) and the hrac above.
        """
        return self.hash(bytes(self.alice.seal) + self.hrac())

    def enact_policies(self, networky_stuff):

        for policy in self.policies:
            policy_payload = policy.encrypt_payload_for_ursula()
            full_payload = self.alice.seal + msgpack.dumps(policy_payload)
            response = networky_stuff.enact_policy(policy.ursula,
                                                   self.hrac(),
                                                   full_payload)  # TODO: Parse response for confirmation.

            # Assuming response is what we hope for
            self.treasure_map.add_ursula(policy.ursula)

    @property
    def id(self):
        if not self._id:
            self._id = api.keccak_digest(bytes(self.alice.seal), api.keccak_digest(self.uri))
        return self._id

    def publish_treasure_map(self):
        encrypted_treasure_map, signature_for_bob = self.alice.encrypt_for(self.bob,
                                                                     self.treasure_map.packed_payload())
        signature_for_ursula = self.alice.seal(self.hrac())  # TODO: Great use-case for Ciphertext class

        # In order to know this is safe to propagate, Ursula needs to see a signature, our public key,
        # and, reasons explained in treasure_map_dht_key above, the uri_hash.
        dht_value = signature_for_ursula + self.alice.seal + self.hrac() + msgpack.dumps(
            encrypted_treasure_map)  # TODO: Ideally, this is a Ciphertext object instead of msgpack (see #112)
        dht_key = self.treasure_map_dht_key()

        setter = self.alice.server.set(dht_key, b"trmap" + dht_value)
        event_loop = asyncio.get_event_loop()
        event_loop.run_until_complete(setter)
        return encrypted_treasure_map, dht_value, signature_for_bob, signature_for_ursula


class Policy(object):
    """
    An individual agreement between Alice and Ursula.  Together, all of the Policies by which
    Ursula nodes which enter into an agreement regarding the same series of kFrags constitute
    a PolicyGroup.

    A Policy has a unique ID, which includes a fingerprint of Alice's public key so that
    only she can set a policy with that ID.  Ursula must verify this; otherwise a collision
    attack is possible.
    """
    _ursula = None
    hashed_part = None
    _id = None

    def __init__(self, alice, bob=None, kfrag=UNKNOWN_KFRAG, pfrag=None, alices_signature=NOT_SIGNED, challenge_size=20,
                 set_id=True, encrypted_challenge_pack=None):
        """
        :param kfrag:
            The kFrag obviously, but defaults to UNKNOWN_KFRAG in case the user wants to set it later.
        :param deterministic_id_portion:  Probably the fingerprint of Alice's public key.
            Any part that Ursula can use to verify that Alice is the rightful setter of this ID.
            If it's not included, the Policy ID will be completely random.
        :param challenge_size:  The number of challenges to create in the ChallengePack.
        """
        self.alice = alice
        self.bob = bob
        self.alices_signature = alices_signature
        self.kfrag = kfrag
        self.pfrag = pfrag
        self.random_id_portion = api.secure_random(32)  # TOOD: Where do we actually want this to live?
        self.challenge_size = challenge_size
        self.treasure_map = []
        self.challenge_pack = []

        self._encrypted_challenge_pack = encrypted_challenge_pack

    @property
    def id(self):
        if self._id:
            return self._id
        else:
            raise RuntimeError("No implemented way to get id yet.")

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
    def from_alice(kfrag,
                   pfrag,
                   alice,
                   bob,
                   ):
        policy = Policy(alice, bob, kfrag, pfrag)
        policy.generate_challenge_pack()

        return policy

    @staticmethod
    def from_ursula(group_payload, ursula):
        alice_pubkey_sig, payload_encrypted_for_ursula = group_payload_splitter(group_payload,
                                                                                msgpack_remainder=True)
        alice = Alice.from_pubkey_sig_bytes(alice_pubkey_sig)
        ursula.learn_about_actor(alice)
        verified, cleartext = ursula.verify_from(alice, payload_encrypted_for_ursula,
                                                 decrypt=True, signature_is_on_cleartext=True)

        if not verified:
            # TODO: What do we do if it's not signed properly?
            pass

        alices_signature, policy_payload = BytestringSplitter(Signature)(cleartext, return_remainder=True)

        kfrag, encrypted_challenge_pack = policy_payload_splitter(policy_payload, return_remainder=True)
        policy = Policy(alice=alice, alices_signature=alices_signature, kfrag=kfrag,
                        encrypted_challenge_pack=encrypted_challenge_pack)

        return policy

    def payload(self):
        return bytes(self.kfrag) + msgpack.dumps(self.encrypted_challenge_pack)

    def activate(self, ursula, negotiation_result):
        self.ursula = ursula
        self.negotiation_result = negotiation_result

    @property
    def encrypted_challenge_pack(self):
        if not self._encrypted_challenge_pack:
            if not self.bob:
                raise TypeError("This Policy doesn't have a Bob, so there's no way to encrypt a ChallengePack for Bob.")
            else:
                self._encrypted_challenge_pack = self.alice.encrypt_for(self.bob, msgpack.dumps(self.challenge_pack))
        return self._encrypted_challenge_pack

    def generate_challenge_pack(self):
        if self.kfrag == UNKNOWN_KFRAG:
            # TODO: Test this branch
            raise TypeError(
                "Can't generate a challenge pack unless we know the kfrag.  Are you Alice?")

        # TODO: make this work instead of being random.  See #46.
        import random
        self._challenge_pack = [(random.getrandbits(32), random.getrandbits(32)) for x in
                                range(self.challenge_size)]
        return True

    def encrypt_payload_for_ursula(self):
        """
        Craft an offer to send to Ursula.
        """
        return self.alice.encrypt_for(self.ursula, self.payload())[0]  # We don't need the signature separately.


class TreasureMap(object):
    def __init__(self, ursula_interface_ids=None):
        self.ids = ursula_interface_ids or []

    def packed_payload(self):
        return msgpack.dumps(self.ids)

    def add_ursula(self, ursula):
        self.ids.append(ursula.interface_dht_key())

    def __eq__(self, other):
        return self.ids == other.ids

    def __iter__(self):
        return iter(self.ids)

    def __len__(self):
        return len(self.ids)


class WorkOrder(object):
    def __init__(self, bob, kfrag_hrac, pfrags, receipt_bytes, receipt_signature, ursula_id=None):
        self.bob = bob
        self.kfrag_hrac = kfrag_hrac
        self.pfrags = pfrags
        self.receipt_bytes = receipt_bytes
        self.receipt_signature = receipt_signature
        self.ursula_id = ursula_id  # TODO: We may still need a more elegant system for ID'ing Ursula.  See #136.

    def __repr__(self):
        return "WorkOrder (pfrags: {}) {} for {}".format([binascii.hexlify(bytes(p))[:6] for p in self.pfrags],
        binascii.hexlify(self.receipt_bytes)[:6],
        binascii.hexlify(self.ursula_id)[:6])

    def __eq__(self, other):
        return (self.receipt_bytes, self.receipt_signature) == (other.receipt_bytes, other.receipt_signature)

    def __len__(self):
        return len(self.pfrags)

    @classmethod
    def constructed_by_bob(cls, kfrag_hrac, pfrags, ursula_dht_key, bob):
        receipt_bytes = b"wo:" + ursula_dht_key  # TODO: represent the pfrags as bytes and hash them as part of the receipt, ie  + keccak_digest(b"".join(pfrags))  - See #137
        receipt_signature = bob.seal(receipt_bytes)
        return cls(bob, kfrag_hrac, pfrags, receipt_bytes, receipt_signature, ursula_dht_key)

    @classmethod
    def from_rest_payload(cls, kfrag_hrac, rest_payload):
        payload_splitter = BytestringSplitter(Signature, PublicKey)
        signature, bob_pubkey_sig, (receipt_bytes, packed_pfrags) = payload_splitter(rest_payload,
                                                                                     msgpack_remainder=True)
        pfrags = [PFrag(p) for p in msgpack.loads(packed_pfrags)]
        verified = signature.verify(receipt_bytes, bob_pubkey_sig)
        if not verified:
            raise ValueError("This doesn't appear to be from Bob.")
        bob = Bob.from_pubkey_sig_bytes(bob_pubkey_sig)
        return cls(bob, kfrag_hrac, pfrags, receipt_bytes, signature)

    def payload(self):
        pfrags_as_bytes = [bytes(p) for p in self.pfrags]
        packed_receipt_and_pfrags = msgpack.dumps((self.receipt_bytes, msgpack.dumps(pfrags_as_bytes)))
        return bytes(self.receipt_signature) + self.bob.seal + packed_receipt_and_pfrags

    def complete(self, cfrags):
        # TODO: Verify that this is in fact complete - right of CFrags and properly signed.
        # TODO: Mark it complete with datetime.
        self
