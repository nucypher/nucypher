import msgpack

from nkms.characters import Alice, Bob, Ursula
from nkms.crypto import api
from nkms.crypto.powers import EncryptingPower
from nkms.policy.constants import UNKNOWN_KFRAG


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
        re_enc_keys, encrypted_key = self.owner.generate_rekey_frags(alice_priv_enc, bob, m, n)  # TODO: Access Alice's private key inside this method.
        policies = []
        for kfrag_id, rekey in enumerate(re_enc_keys):
            policy = Policy.from_alice(
                alice=self.owner,
                kfrag=rekey,
            )
            policies.append(policy)

        return PolicyGroup(uri, bob, policies)


class PolicyGroup(object):
    """
    The terms and conditions by which Alice shares with Bob.
    """

    _id = None

    def __init__(self, uri: str, bob: Bob, policies=None):
        self.policies = policies or []
        self.bob = bob
        self.uri = uri

    @property
    def n(self):
        return len(self.policies)

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

    def transmit_payloads(self, networky_stuff):

        for policy in self.policies:
            payload = policy.encrypt_payload_for_ursula()
            response = networky_stuff.animate_policy(policy.ursula, payload)
            # TODO: Parse response for confirmation and update TreasureMap with new Ursula friend.

    @property
    def id(self):
        if not self._id:
            self._id = api.keccak_digest(self.uri, bytes(self.bob.seal))
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

    def __init__(self, alice, kfrag=UNKNOWN_KFRAG, deterministic_id_portion=None, challenge_size=20, set_id=True):
        """

        :param kfrag:
            The kFrag obviously, but defaults to UNKNOWN_KFRAG in case the user wants to set it later.
        :param deterministic_id_portion:  Probably the fingerprint of Alice's public key.
            Any part that Ursula can use to verify that Alice is the rightful setter of this ID.
            If it's not included, the Policy ID will be completely random.
        :param challenge_size:  The number of challenges to create in the ChallengePack.
        """
        self.alice = alice
        self.kfrag = kfrag
        self.deterministic_id_portion = deterministic_id_portion
        self.random_id_portion = api.secure_random(32)  # TOOD: Where do we actually want this to live?
        self.challenge_size = challenge_size
        self.treasure_map = []

        if set_id:
            self.set_id()

    @property
    def id(self):
        if self._id:
            return self._id
        else:
            raise RuntimeError("No implemented way to get id yet.")

    def set_id(self):
        if self.deterministic_id_portion:
            self._id = "{}-{}".format(api.keccak_digest(*[str(d).encode() for d in self.deterministic_id_portion], self.random_id_portion),
                                      api.keccak_digest(self.random_id_portion))
        else:
            self._id = api.keccak_digest(self.random_id_portion)

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
                   ):
        policy = Policy(alice, kfrag, deterministic_id_portion=alice.seal)
        policy.generate_challenge_pack()

        return policy

    def payload(self):
        return msgpack.dumps({b"kf": bytes(self.kfrag), b"cp": msgpack.dumps(self.challenge_pack)})

    def activate(self, ursula, negotiation_result):
        self.ursula = ursula
        self.negotiation_result = negotiation_result

    def hash(self, pubkey_sig_alice, hash_input):

        self.hashed_part = api.keccak_digest(hash_input)
        hash_input_for_id = str(pubkey_sig_alice).encode() + str(self.hashed_part).encode()
        self._id = api.keccak_digest(hash_input_for_id)
        return self._id

    def generate_challenge_pack(self):
        if self.kfrag == UNKNOWN_KFRAG:
            raise TypeError(
                "Can't generate a challenge pack unless we know the kfrag.  Are you Alice?")

        # TODO: make this work instead of being random.
        import random
        self.challenge_pack = [(random.getrandbits(32), random.getrandbits(32)) for x in
                               range(self.challenge_size)]
        return True

    def encrypt_payload_for_ursula(self):
        """
        Craft an offer to send to Ursula.
        """
        return self.alice.encrypt_for(self.ursula, self.payload())


    def update_treasure_map(self, policy_offer_result):
        # TODO: parse the result and add the node information to the treasure map.
        self.treasure_map.append(policy_offer_result)


class TreasureMap(object):
    def __init__(self):
        self.nodes = []

    def packed_payload(self):
        return msgpack.dumps(self.nodes)
