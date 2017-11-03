import asyncio
import datetime

import msgpack
import pytest

from nkms.characters import Ursula, Alice, Character, Bob, community_meeting
from nkms.crypto import api
from nkms.network import blockchain_client
from nkms.network.blockchain_client import list_all_ursulas
from nkms.network.node import NetworkyStuff
from nkms.policy.constants import NON_PAYMENT
from nkms.policy.models import PolicyManagerForAlice, PolicyOffer, TreasureMap, PolicyGroup, Policy

EVENT_LOOP = asyncio.get_event_loop()
asyncio.set_event_loop(EVENT_LOOP)

URSULA_PORT = 7468


def make_fake_ursulas(how_many):
    URSULAS = []
    for _u in range(how_many):
        _URSULA = Ursula()
        _URSULA.attach_server()
        _URSULA.listen(URSULA_PORT + _u, "127.0.0.1")
        blockchain_client._ursulas_on_blockchain.append(_URSULA.ip_dht_key())

        URSULAS.append(_URSULA)

    for _counter, ursula in enumerate(URSULAS):
        # EVENT_LOOP.run_until_complete(ursula.server.bootstrap([("127.0.0.1", URSULA_PORT)]))
        EVENT_LOOP.run_until_complete(ursula.server.bootstrap([("127.0.0.1", URSULA_PORT + _counter)]))
        ursula.publish_interface_information()

    EVENT_LOOP.run_until_complete(ursula.server.bootstrap([("127.0.0.1", URSULA_PORT + p) for p in range(how_many)]))

    return URSULAS

URSULAS = make_fake_ursulas(6)

ALICE = Alice()
ALICE.attach_server()
ALICE.server.listen(8471)
EVENT_LOOP.run_until_complete(ALICE.server.bootstrap([("127.0.0.1", URSULA_PORT)]))

BOB = Bob(alice=ALICE)
BOB.attach_server()
BOB.server.listen(8475)
EVENT_LOOP.run_until_complete(BOB.server.bootstrap([("127.0.0.1", URSULA_PORT)]))


community_meeting(ALICE, BOB, URSULAS[0])


def test_alice_finds_ursula():
    all_ursulas = list_all_ursulas()
    _discovered_ursula_dht_key = ALICE.find_best_ursula()
    getter = ALICE.server.get(_discovered_ursula_dht_key)
    loop = asyncio.get_event_loop()
    interface_bytes = loop.run_until_complete(getter)
    port, interface = msgpack.loads(interface_bytes)
    assert port == URSULA_PORT


class MockPolicyOfferResponse(object):
    was_accepted = True


class MockNetworkyStuff(NetworkyStuff):
    def go_live_with_policy(self, ursula, policy_offer):
        return

    def find_ursula(self, id, offer=None):
        if offer:
            return Ursula(), MockPolicyOfferResponse()
        else:
            return super().find_ursula(id)

    def animate_policy(self, ursula, payload):
        return


def test_treasure_map_from_alice_to_ursula():
    """
    Shows that Alice can share a TreasureMap with Ursula and that Bob can receive and decrypt it.
    """
    treasure_map = TreasureMap([api.secure_random(50) for _ in range(50)])  # TODO: This is still random here.

    encrypted_treasure_map, signature = ALICE.encrypt_for(BOB, treasure_map.packed_payload())
    packed_encrypted_treasure_map = msgpack.dumps(encrypted_treasure_map)

    # For example, a hashed path.
    resource_id = b"as098duasdlkj213098asf"
    policy_group = PolicyGroup(resource_id, BOB)
    setter = ALICE.server.set(policy_group.id, packed_encrypted_treasure_map)
    set_event = EVENT_LOOP.run_until_complete(setter)

    treasure_map_as_set_on_network = list(URSULAS[0].server.storage.items())[0][1]
    assert treasure_map_as_set_on_network == packed_encrypted_treasure_map  # IE, Ursula stores it properly.
    return treasure_map, treasure_map_as_set_on_network, signature, policy_group


def test_treasure_map_stored_by_ursula_is_the_correct_one_for_bob():
    treasure_map, treasure_map_as_set_on_network, signature, _ = test_treasure_map_from_alice_to_ursula()
    encrypted_treasure_map = msgpack.loads(treasure_map_as_set_on_network)
    verified, treasure_map_as_decrypted_by_bob = BOB.verify_from(ALICE, signature,
                                                                 encrypted_treasure_map,
                                                                 decrypt=True,
                                                                 signature_is_on_cleartext=True,
                                                                 )
    assert treasure_map_as_decrypted_by_bob == treasure_map.packed_payload()
    assert verified is True


def test_treasure_map_from_ursula_to_bob():
    """
    Bob finds Ursula and upgrades their connection to TLS to receive the TreasureMap.
    """
    treasure_map, treasure_map_as_set_on_network, signature, policy_group = test_treasure_map_from_alice_to_ursula()
    networky_stuff = MockNetworkyStuff()

    # Of course, in the real world, Bob has sufficient information to reconstitute a PolicyGroup, gleaned, we presume, through a side-channel with Alice.
    treasure_map_from_wire = BOB.get_treasure_map(policy_group, signature)

    assert treasure_map == treasure_map_from_wire


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
