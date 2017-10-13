import asyncio
import datetime

import pytest

from nkms.characters import Ursula, Alice, Character, Bob
from nkms.crypto import api
from nkms.policy.constants import NON_PAYMENT
from nkms.policy.models import PolicyManagerForAlice, PolicyOffer, TreasureMap, PolicyGroup


class MockPolicyOfferResponse(object):
    was_accepted = True


class MockNetworkyStuff(object):
    def transmit_offer(self, ursula, policy_offer):
        return MockPolicyOfferResponse()

    def find_ursula(self, id, hashed_part):
        return Ursula()


def test_treasure_map_direct_from_alice_to_bob():
    """
    Shows that Alice can share a TreasureMap with Ursula and that Bob can receive and decrypt it.
    """
    alice, ursula, event_loop = test_alice_finds_ursula()
    bob = Bob()
    alice.learn_about_actor(bob)
    bob.learn_about_actor(alice)

    _discovered_ursula_ip, discovered_ursula_port = alice.find_best_ursula()

    treasure_map = TreasureMap()
    for i in range(50):
        treasure_map.nodes.append(api.secure_random(50))

    encrypted_treasure_map, signature = alice.encrypt_for(bob, treasure_map.packed_payload())

    # For example, a hashed path.
    resource_id = b"as098duasdlkj213098asf"
    policy_group = PolicyGroup(resource_id, bob)
    setter = alice.server.set(policy_group.id, encrypted_treasure_map)
    event_loop.run_until_complete(setter)

    treasure_map_as_set_on_network = list(ursula.server.storage.items())[0][1]
    verified, treasure_map_as_decrypted_by_bob = bob.verify_from(alice, signature,
                                                                 treasure_map_as_set_on_network,
                                                                 decrypt=True,
                                                                 signature_is_on_cleartext=True,
                                                                 )
    assert treasure_map_as_decrypted_by_bob == treasure_map.packed_payload()
    assert verified is True


def test_alice_has_ursulas_public_key_and_uses_it_to_encode_policy_payload():
    alice = Alice()
    bob = Bob()

    # For example, a hashed path.
    resource_id = b"as098duasdlkj213098asf"

    # Alice has a policy in mind; she crafts an offer.
    n = 50
    deposit = NON_PAYMENT
    contract_end_datetime = datetime.datetime.now() + datetime.timedelta(days=5)
    offer = PolicyOffer(n, deposit, contract_end_datetime)

    # Now, Alice needs to find N Ursulas to whom to make the offer.
    networky_stuff = MockNetworkyStuff()
    policy_manager = PolicyManagerForAlice(alice)

    policy_group = policy_manager.create_policy_group(
        bob,
        resource_id,
        m=20,
        n=50,
        offer=offer,
    )
    networky_stuff = MockNetworkyStuff()
    # policy_group.transmit(networky_stuff)  # Until we figure out encrypt_for logic


def test_alice_finds_ursula():
    event_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(event_loop)

    ursula_port = 8468

    ursula = Ursula()
    ursula.attach_server()
    ursula.server.listen(ursula_port)
    event_loop.run_until_complete(ursula.server.bootstrap([("127.0.0.1", ursula_port)]))

    alice = Alice()
    alice.attach_server()
    alice.server.listen(8471)
    event_loop.run_until_complete(ursula.server.bootstrap([("127.0.0.1", 8471)]))

    _discovered_ursula_ip, discovered_ursula_port = alice.find_best_ursula()
    assert ursula_port == ursula_port
    return alice, ursula, event_loop


def test_trying_to_find_unknown_actor_raises_not_found():
    terry = Character()
    alice = Alice()

    message = b"some_message"
    signature = alice.seal(message)

    # Terry can't reference Alice...
    with pytest.raises(Character.NotFound):
        verification = terry.verify_from(alice, signature, message)

    # ...before learning about Alice.
    terry.learn_about_actor(alice)
    verification = terry.verify_from(alice, signature, message)
