import msgpack
from npre.constants import UNKNOWN_KFRAG

from nkms.characters import Alice, Bob, Ursula
from nkms.crypto import api
from nkms.crypto.api import keccak_digest
from nkms.crypto.powers import EncryptingPower


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
    def __init__(self, owner: Alice):
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
        re_enc_keys, encrypted_key = self.owner.generate_rekey_frags(alice_priv_enc, bob, m,
                                                                     n)  # TODO: Access Alice's private key inside this method.
        policies = []
        for kfrag_id, rekey in enumerate(re_enc_keys):
            policy = Policy.from_alice(
                alice=self.owner,
                bob=bob,
                kfrag=rekey,
            )
            policies.append(policy)

        return PolicyGroup(uri, self.owner, bob, policies)


class PolicyGroup(object):
    """
    The terms and conditions by which Alice shares with Bob.
    """

    _id = None

    def __init__(self, uri: str, alice: Alice, bob: Bob, policies=None):
        self.policies = policies or []
        self.alice = alice
        self.bob = bob
        self.uri = uri
        self.treasure_map = TreasureMap()

    @property
    def n(self):
        return len(self.policies)

    def hash(self, message):
        return keccak_digest(message)

    def find_n_ursulas(self, networky_stuff, offer: PolicyOffer) -> list:
        """
        :param networky_stuff: A compliant interface (maybe a Client instance) to be used to engage the DHT swarm.

        :return: A list, with each element containing an Ursula and an OfferResult.
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
        The "hashed resource authentication code".

        A hash of:
        * Alice's public key
        * Bob's public key
        * the uri

        Alice and Bob have all the information they need to construct this.
        Ursula does not, so we share it with her.
        """
        return self.hash(bytes(self.alice.seal) + bytes(self.bob.seal) + self.uri)

    def treasure_map_dht_key(self):
        """
        We need a key that Bob can glean from knowledge he already has *and* which Ursula can verify came from us.
        Ursula will refuse to propagate this key if it she can't prove that our public key, which is included in it,
        was used to sign the payload.

        Our public key (which everybody knows) and the hrac above.
        """
        return self.hash(bytes(self.alice.seal) + self.hrac())

    def transmit_payloads(self, networky_stuff):

        for policy in self.policies:
            policy_payload = policy.encrypt_payload_for_ursula()
            full_payload = self.hrac() + self.alice.seal + msgpack.dumps(policy_payload)
            response = networky_stuff.animate_policy(policy.ursula,
                                                      full_payload)  # TODO: Parse response for confirmation and update TreasureMap with new Ursula friend.

            # Assuming response is what we hope for
            self.treasure_map.add_ursula(policy.ursula)

    @property
    def id(self):
        if not self._id:
            self._id = api.keccak_digest(bytes(self.alice.seal), api.keccak_digest(self.uri))
        return self._id


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

    def __init__(self, alice, bob, kfrag=UNKNOWN_KFRAG, challenge_size=20, set_id=True):
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
        self.kfrag = kfrag
        self.random_id_portion = api.secure_random(32)  # TOOD: Where do we actually want this to live?
        self.challenge_size = challenge_size
        self.treasure_map = []
        self.challenge_pack = []

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
                   alice,
                   bob,
                   ):
        policy = Policy(alice, bob, kfrag)
        policy.generate_challenge_pack()

        return policy

    def payload(self):
        return bytes(self.kfrag) + msgpack.dumps(self.encrypted_treasure_map())

    def activate(self, ursula, negotiation_result):
        self.ursula = ursula
        self.negotiation_result = negotiation_result

    def encrypted_treasure_map(self):
        self.alice.encrypt_for(self.bob, msgpack.dumps(self.challenge_pack))

    def generate_challenge_pack(self):
        if self.kfrag == UNKNOWN_KFRAG:
            # TODO: Test this branch
            raise TypeError(
                "Can't generate a challenge pack unless we know the kfrag.  Are you Alice?")

        # TODO: make this work instead of being random.  See #46.
        import random
        self.challenge_pack = [(random.getrandbits(32), random.getrandbits(32)) for x in
                               range(self.challenge_size)]
        return True

    def encrypt_payload_for_ursula(self):
        """
        Craft an offer to send to Ursula.
        """
        return self.alice.encrypt_for(self.ursula, self.payload())


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
