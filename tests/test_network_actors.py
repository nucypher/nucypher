import asyncio
import unittest

from nkms.characters import Ursula, Alice
from nkms.crypto.keyring import KeyRing
from nkms.policy.models import PolicyManagerForAlice


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


@unittest.skip(reason="Work in progress")
def test_alice_finds_ursula():
    event_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(event_loop)

    ursula_port = 8468

    ursula = Ursula()
    ursula.server.listen(ursula_port)
    event_loop.run_until_complete(ursula.server.bootstrap([("127.0.0.1", ursula_port)]))

    alice = Alice()
    alice.server.listen(8471)
    event_loop.run_until_complete(ursula.server.bootstrap([("127.0.0.1", 8471)]))

    _discovered_ursula_ip, discovered_ursula_port = alice.find_best_ursula()
    assert ursula_port == ursula_port
