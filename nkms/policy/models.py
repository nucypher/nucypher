import msgpack

from nkms.characters import Alice, Bob
from nkms.crypto import api
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


class PolicyManager(object):
    pass


class PolicyManagerForAlice(PolicyManager):
    def __init__(self, owner: Alice):
        self.owner = owner

    def find_n_ursulas(self, networky_stuff, n, offer: PolicyOffer) -> list:
        """
        :param networky_stuff: A compliant interface (maybe a Client instance) to be used to engage the DHT swarm.

        :return: A list, with each element containing an Ursula and an OfferResult.
        """
        ursulas_and_results = []
        while len(ursulas_and_results) < n:
            try:
                ursulas_and_results.append(
                    networky_stuff.find_ursula(self.id, self.hashed_part, offer))
            except networky_stuff.NotEnoughQualifiedUrsulas:
                pass  # Tell Alice to either wait or lower the value of n.
        return ursulas_and_results

    def create_policy_group(self,
                            bob: Bob,
                            uri: bytes,
                            m: int,
                            n: int,
                            offer: PolicyOffer,
                            ):
        """
        Alice dictates a new group of policies.
        """
        re_enc_keys = self.owner.generate_re_encryption_keys(
                                                  bob.seal.as_tuple(),
                                                  m,
                                                  n)
        policies = []
        for kfrag_id, rekey in enumerate(re_enc_keys):
            policy = Policy.from_alice(
                rekey,
                self.owner.seal.as_bytes(),
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

    def transmit(self, networky_stuff):

        for policy in self.policies:
            policy_offer = policy.craft_offer(networky_stuff)
            result = networky_stuff.transmit_offer(policy.ursula, policy_offer)
            if result.was_accepted:
                policy.update_treasure_map(result)

    @property
    def id(self):
        if not self._id:
            self._id = api.keccak_digest(self.uri, self.bob.seal.as_bytes())
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
    ursula = None
    hashed_part = None
    _id = None

    def __init__(self, kfrag=UNKNOWN_KFRAG, deterministic_id_portion=None, challenge_size=20, set_id=True):
        """

        :param kfrag:
            The kFrag obviously, but defaults to UNKNOWN_KFRAG in case the user wants to set it later.
        :param deterministic_id_portion:  Probably the fingerprint of Alice's public key.
            Any part that Ursula can use to verify that Alice is the rightful setter of this ID.
            If it's not included, the Policy ID will be completely random.
        :param challenge_size:  The number of challenges to create in the ChallengePack.
        """
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



    @staticmethod
    def from_alice(kfrag,
                   pubkey_sig_alice,
                   ):
        policy = Policy(kfrag, deterministic_id_portion=pubkey_sig_alice)
        policy.generate_challenge_pack()

        return policy

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

    def craft_offer(self, networky_stuff):
        """
        Craft an offer to send to Ursula.
        """
        return self.ursula.encrypt_for((self.kfrag, self.challenge_pack, self.treasure_map))

    def update_treasure_map(self, policy_offer_result):
        # TODO: parse the result and add the node information to the treasure map.
        self.treasure_map.append(policy_offer_result)


class TreasureMap(object):
    def __init__(self):
        self.nodes = []

    def packed_payload(self):
        return msgpack.dumps(self.nodes)
