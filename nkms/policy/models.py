from nkms.crypto.pre.keys import generate_re_encryption_keys
from nkms.crypto import nkms_hash


class PolicyGroup(object):
    """
    The terms and conditions by which Alice shares with Bob.
    """

    def __init__(self):
        self.policies = []

    def craft(self,
                keychain_alice: "KeyChain",
                pubkey_enc_bob: tuple,
                uri: bytes,
                m: int,
                n: int
                ):
        """
        Alice dictates a new group of policies.
        """
        re_enc_keys = generate_re_encryption_keys(keychain_alice.seckey_end,
                                                  pubkey_enc_bob,
                                                  m,
                                                  n)
        for kfrag_id, key in enumerate(re_enc_keys):
            policy = Policy.from_alice(
                key,  # Bob won't know this.
                keychain_alice.pubkey_sig,
                pubkey_enc_bob,
                uri,  # Ursula won't know this.
                kfrag_id,
            )
            self.policies.append(policy)

    def transmit(self, networky_stuff):
        for policy in self.policies:
            policy_offer = policy.craft_offer()
            result = networky_stuff.transmit_offer(policy.ursula, policy_offer)
            if result.was_accepted():
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

    @staticmethod
    def from_alice(kfrag,
                   pubkey_sig_alice,
                   pubkey_enc_bob,
                   uri,
                   kfrag_id
                   ):

        policy = Policy()
        policy.generate_challenge_pack(kfrag)
        policy.hash(pubkey_enc_bob, uri, kfrag_id, pubkey_sig_alice=pubkey_sig_alice)

        return policy

    def hash(self, pubkey_sig_alice, *args):
        self.hashed_part = nkms_hash(*args)
        self.id = nkms_hash(pubkey_sig_alice, self.hashed_part)
        return self.id

    def craft_offer(self, networky_stuff):
        """
        Find an Ursula and craft an offer for her.
        """
        self.ursula = networky_stuff.find_ursula(self.id, self.hashed_part)
        return self.ursula.encrypt_for(self.kfrag, self.challenge_pack, self.treasure_map)
