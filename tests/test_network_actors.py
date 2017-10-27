import asyncio
import datetime

import pytest
import unittest

from nkms.characters import Ursula, Alice, Character, Bob, community_meeting
from nkms.crypto import api
from nkms.crypto.constants import NO_DECRYPTION_PERFORMED
from nkms.policy.constants import NON_PAYMENT
from nkms.policy.models import PolicyManagerForAlice, PolicyOffer, TreasureMap, PolicyGroup, Policy


EVENT_LOOP = asyncio.new_event_loop()
asyncio.set_event_loop(EVENT_LOOP)

URSULA_PORT = 8468

URSULA = Ursula()
URSULA.attach_server()
URSULA.server.listen(URSULA_PORT)
EVENT_LOOP.run_until_complete(URSULA.server.bootstrap([("127.0.0.1", URSULA_PORT)]))

ALICE = Alice()
ALICE.attach_server()
ALICE.server.listen(8471)
EVENT_LOOP.run_until_complete(URSULA.server.bootstrap([("127.0.0.1", 8471)]))

BOB = Bob()

community_meeting(ALICE, BOB, URSULA)


def test_alice_finds_ursula():
    _discovered_ursula_ip, discovered_ursula_port = ALICE.find_best_ursula()
    assert discovered_ursula_port == URSULA_PORT



class MockPolicyOfferResponse(object):
    was_accepted = True


class MockNetworkyStuff(object):
    def go_live_with_policy(self, ursula, policy_offer):
        return

    def find_ursula(self, id, offer):
        return Ursula(), MockPolicyOfferResponse()

    def animate_policy(self, ursula, payload):
        return

def test_treasure_map_from_alice_to_ursula():
    """
    Shows that Alice can share a TreasureMap with Ursula and that Bob can receive and decrypt it.
    """
    treasure_map = TreasureMap()
    for i in range(50):
        treasure_map.nodes.append(api.secure_random(50))

    encrypted_treasure_map, signature = ALICE.encrypt_for(BOB, treasure_map.packed_payload())

    # For example, a hashed path.
    resource_id = b"as098duasdlkj213098asf"
    policy_group = PolicyGroup(resource_id, BOB)
    setter = ALICE.server.set(policy_group.id, encrypted_treasure_map)
    EVENT_LOOP.run_until_complete(setter)

    treasure_map_as_set_on_network = list(URSULA.server.storage.items())[0][1]
    assert tuple(treasure_map_as_set_on_network) == encrypted_treasure_map  # IE, Ursula stores it properly.

    verified, treasure_map_as_decrypted_by_bob = BOB.verify_from(ALICE, signature,
                                                                 treasure_map_as_set_on_network,
                                                                 decrypt=True,
                                                                 signature_is_on_cleartext=True,
                                                                 )

    return treasure_map, treasure_map_as_set_on_network, signature


def test_treasure_map_stored_by_ursula_is_the_correct_one_for_bob():
    treasure_map, treasure_map_as_set_on_network, signature = test_treasure_map_from_alice_to_ursula()
    verified, treasure_map_as_decrypted_by_bob = BOB.verify_from(ALICE, signature,
                                                                 treasure_map_as_set_on_network,
                                                                 decrypt=True,
                                                                 signature_is_on_cleartext=True,
                                                                 )
    assert treasure_map_as_decrypted_by_bob == treasure_map.packed_payload()
    assert verified is True


def test_treasure_map_from_ursula_to_bob():
    """
    Bob finds Ursula and upgrades their connection to TLS to receive the TreasureMap.
    """
    pass


def test_cannot_offer_policy_without_finding_ursula():
    networky_stuff = MockNetworkyStuff()
    policy = Policy(Alice())
    with pytest.raises(Ursula.NotFound):
        policy_offer = policy.encrypt_payload_for_ursula()


def test_alice_has_ursulas_public_key_and_uses_it_to_encode_policy_payload():
    # For example, a hashed path.
    resource_id = b"as098duasdlkj213098asf"

    # Alice has a policy in mind; she crafts an offer.
    n = 50
    deposit = NON_PAYMENT
    contract_end_datetime = datetime.datetime.now() + datetime.timedelta(days=5)
    offer = PolicyOffer(n, deposit, contract_end_datetime)

    # Now, Alice needs to find N Ursulas to whom to make the offer.
    networky_stuff = MockNetworkyStuff()
    policy_manager = PolicyManagerForAlice(ALICE)

    policy_group = policy_manager.create_policy_group(
        BOB,
        resource_id,
        m=20,
        n=50,
    )
    networky_stuff = MockNetworkyStuff()
    policy_group.find_n_ursulas(networky_stuff, offer)
    policy_group.transmit_payloads(networky_stuff)  # Until we figure out encrypt_for logic


def test_trying_to_find_unknown_actor_raises_not_found():
    tony_clifton = Character()

    message = b"some_message"
    signature = ALICE.seal(message)

    # Tony can't reference Alice...
    with pytest.raises(Character.NotFound):
        verification = tony_clifton.verify_from(ALICE, signature, message)

    # ...before learning about Alice.
    tony_clifton.learn_about_actor(ALICE)
    verification, NO_DECRYPTION_PERFORMED = tony_clifton.verify_from(ALICE, signature, message)

    assert verification is True