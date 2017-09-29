from nkms.crypto.hash import content_hash
from nkms.crypto.keyring import KeyRing
from nkms.crypto.pre.keygen import generate_re_encryption_keys
from nkms.policy.constants import UNKNOWN_KFRAG


class PolicyManager(object):
    pass


class PolicyManagerForAlice(PolicyManager):
    def __init__(self, keychain_alice: KeyRing):
        self.keychain_alice = keychain_alice

    def find_n_ursulas(self, networky_stuff, offer: PolicyOffer) -> list:
        """
        :param networky_stuff: A compliant interface (maybe a Client instance) to be used to engage the DHT swarm.

        :return: A list, with each element containing an Ursula and an OfferResult.
        """
        ursulas_and_results = []
        while ursulas_and_results < n:
            try:
                # TODO: Oh wait.  I guess we need Policy IDs before this moment.
                ursulas_and_results.append(networky_stuff.find_ursula(self.id, self.hashed_part, offer))
            except networky_stuff.NotEnoughQualifiedUrsulas:
                pass  # Tell Alice to either wait or lower the value of n.
        return ursulas_and_results

    def create_policy_group(self,
                            pubkey_enc_bob: tuple,
                            uri: bytes,
                            m: int,
                            n: int
                            ):
        """
        Alice dictates a new group of policies.
        """
        re_enc_keys = generate_re_encryption_keys(self.keychain_alice.enc_keypair.priv_key,
                                                  pubkey_enc_bob,
                                                  m,
                                                  n)
        policies = []
        for kfrag_id, key in enumerate(re_enc_keys):
            policy = Policy.from_alice(
                key,  # Bob won't know this.
                self.keychain_alice.sig_keypair.pub_key,
                pubkey_enc_bob,
                uri,  # Ursula won't know this.
                kfrag_id,
            )
            policies.append(policy)

        return PolicyGroup(policies)


class PolicyGroup(object):
    """
    The terms and conditions by which Alice shares with Bob.
    """

    def __init__(self, policies=None):
        self.policies = policies or []

    def transmit(self, networky_stuff):

        for policy in self.policies:
            policy_offer = policy.craft_offer(networky_stuff)
            result = networky_stuff.transmit_offer(policy.ursula, policy_offer)
            if result.was_accepted:
                policy.update_treasure_map(result)


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

    def __init__(self, kfrag=UNKNOWN_KFRAG, challenge_size=20):
        self.kfrag = kfrag
        self.challenge_size = challenge_size
        self.treasure_map = []

    @property
    def id(self):
        if self._id:
            return self._id
        else:
            raise RuntimeError("No implemented way to get id yet.")

    @staticmethod
    def from_alice(kfrag,
                   pubkey_sig_alice,
                   pubkey_enc_bob,
                   uri,
                   kfrag_id
                   ):
        policy = Policy(kfrag)
        policy.generate_challenge_pack()
        policy.hash(pubkey_sig_alice=pubkey_sig_alice, hash_input=(pubkey_enc_bob, uri, kfrag_id))

        return policy

    def hash(self, pubkey_sig_alice, hash_input):
        hash_input = str(hash_input).encode()
        self.hashed_part = content_hash(hash_input)
        hash_input_for_id = str(pubkey_sig_alice).encode() + str(self.hashed_part).encode()
        self._id = content_hash(hash_input_for_id)
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