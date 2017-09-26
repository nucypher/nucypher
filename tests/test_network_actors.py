from nkms.crypto.keyring import KeyRing
from nkms.policy.models import PolicyGroup, PolicyManagerForAlice


class MockUrsula(object):
    def encrypt_for(self, payload):
        # TODO: Make this a testable result
        import random
        return random.getrandbits(32)



class MockPolicyOfferResponse(object):
    was_accepted = True


class MockNetworkyStuff(object):

    def transmit_offer(self, ursula, policy_offer):
        return MockPolicyOfferResponse()

    def find_ursula(self, id, hashed_part):
        return MockUrsula()





def test_alice_has_ursulas_public_key_and_uses_it_to_encode_policy_payload():
    keychain_alice = KeyRing()
    keychain_bob = KeyRing()
    keychain_ursula = KeyRing()

    # For example, a hashed path.
    resource_id = b"as098duasdlkj213098asf"

    # Alice runs this to get a policy object.
    policy_manager = PolicyManagerForAlice(keychain_alice)
    policy_group = policy_manager.create_policy_group(
                                     keychain_bob.enc_keypair.pub_key,
                                     resource_id,
                                     m=20,
                                     n=50
                                     )
    networky_stuff = MockNetworkyStuff()
    policy_group.transmit(networky_stuff)
