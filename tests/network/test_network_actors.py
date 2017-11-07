import asyncio
import datetime

import msgpack
import pytest

from kademlia.utils import digest
from nkms.characters import Ursula, Alice, Character, Bob, community_meeting
from nkms.network.blockchain_client import list_all_ursulas
from nkms.network.node import NetworkyStuff
from nkms.policy.constants import NON_PAYMENT
from nkms.policy.models import PolicyManagerForAlice, PolicyOffer, Policy

EVENT_LOOP = asyncio.get_event_loop()
asyncio.set_event_loop(EVENT_LOOP)

URSULA_PORT = 7468
NUMBER_OF_URSULAS_IN_NETWORK = 6

URSULA_PORTS = range(URSULA_PORT, URSULA_PORT + NUMBER_OF_URSULAS_IN_NETWORK)


def make_fake_ursulas(how_many):
    URSULAS = []
    for _u in range(how_many):
        _URSULA = Ursula()
        _URSULA.attach_server()
        _URSULA.listen(URSULA_PORT + _u, "127.0.0.1")

        URSULAS.append(_URSULA)

    for _counter, ursula in enumerate(URSULAS):
        EVENT_LOOP.run_until_complete(
            ursula.server.bootstrap([("127.0.0.1", URSULA_PORT + _c) for _c in range(how_many)]))
        ursula.publish_interface_information()

    return URSULAS


URSULAS = make_fake_ursulas(NUMBER_OF_URSULAS_IN_NETWORK)

ALICE = Alice()
ALICE.attach_server()
ALICE.server.listen(8471)
EVENT_LOOP.run_until_complete(ALICE.server.bootstrap([("127.0.0.1", URSULA_PORT)]))

BOB = Bob(alice=ALICE)
BOB.attach_server()
BOB.server.listen(8475)
EVENT_LOOP.run_until_complete(BOB.server.bootstrap([("127.0.0.1", URSULA_PORT)]))

community_meeting(ALICE, BOB, URSULAS[0])


def test_all_ursulas_know_about_all_other_ursulas():
    ignorance = []
    for acounter, announcing_ursula in enumerate(list_all_ursulas()):
        for counter, propagating_ursula in enumerate(URSULAS):
            if not digest(announcing_ursula) in propagating_ursula.server.storage:
                ignorance.append((counter, acounter))
    if ignorance:
        pytest.fail(str(["{} didn't know about {}".format(counter, acounter) for counter, acounter in ignorance]))


def test_alice_finds_ursula():
    ursula_index = 1
    all_ursulas = list_all_ursulas()
    getter = ALICE.server.get(all_ursulas[ursula_index])
    loop = asyncio.get_event_loop()
    value = loop.run_until_complete(getter)
    signature, ursula_pubkey_sig, interface_info = msgpack.loads(value.lstrip(b"uaddr-"))
    port, interface = msgpack.loads(interface_info)
    assert port == URSULA_PORT + ursula_index


def test_vladimir_illegal_interface_key_does_not_propagate():
    vladimir = URSULAS[0]
    ursula = URSULAS[1]

    # Ursula hasn't seen any illegal keys.
    assert ursula.server.protocol.illegal_keys_seen == []

    # Vladimir does almost everything right....
    interface_info = msgpack.dumps((vladimir.port, vladimir.interface))
    signature = vladimir.seal(interface_info)
    value = b"uaddr-" + msgpack.dumps([signature, bytes(vladimir.seal), interface_info])

    # Except he sets an illegal key for his interface.
    illegal_key = "Not allowed to set arbitrary key for this."
    setter = vladimir.server.set(key=illegal_key, value=value)
    loop = asyncio.get_event_loop()
    loop.run_until_complete(setter)

    # Now Ursula has seen an illegal key.
    assert digest(illegal_key) in ursula.server.protocol.illegal_keys_seen


class MockPolicyOfferResponse(object):
    was_accepted = True


class MockNetworkyStuff(NetworkyStuff):
    def __init__(self):
        self.ursulas = iter(URSULAS)

    def go_live_with_policy(self, ursula, policy_offer):
        return

    def find_ursula(self, id, offer=None):
        if offer:
            try:
                return next(self.ursulas), MockPolicyOfferResponse()
            except StopIteration:
                raise self.NotEnoughQualifiedUrsulas
        else:
            return super().find_ursula(id)

    def animate_policy(self, ursula, payload):
        return


def test_treasure_map_from_alice_to_ursula():
    """
    Shows that Alice can share a TreasureMap with Ursula and that Bob can receive and decrypt it.
    """
    # For example, a hashed path.
    resource_id = b"as098duasdlkj213098asf"
    policy_group = test_alice_has_ursulas_public_key_and_uses_it_to_encode_policy_payload()

    # treasure_map = TreasureMap([api.secure_random(50) for _ in range(50)])  # TODO: This is still random here.
    treasure_map = policy_group.treasure_map

    encrypted_treasure_map, signature = ALICE.encrypt_for(BOB, treasure_map.packed_payload())
    packed_encrypted_treasure_map = msgpack.dumps(encrypted_treasure_map)

    setter = ALICE.server.set(policy_group.id, packed_encrypted_treasure_map)
    _set_event = EVENT_LOOP.run_until_complete(setter)

    treasure_map_as_set_on_network = URSULAS[0].server.storage[digest(policy_group.id)]
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
    n = NUMBER_OF_URSULAS_IN_NETWORK
    deposit = NON_PAYMENT
    contract_end_datetime = datetime.datetime.now() + datetime.timedelta(days=5)
    offer = PolicyOffer(n, deposit, contract_end_datetime)

    # Now, Alice needs to find N Ursulas to whom to make the offer.
    networky_stuff = MockNetworkyStuff()
    policy_manager = PolicyManagerForAlice(ALICE)

    policy_group = policy_manager.create_policy_group(
        BOB,
        resource_id,
        m=3,
        n=n,
    )
    networky_stuff = MockNetworkyStuff()
    policy_group.find_n_ursulas(networky_stuff, offer)
    policy_group.transmit_payloads(networky_stuff)  # Until we figure out encrypt_for logic

    return policy_group


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


def test_treaure_map_is_legit():
    treasure_map, treasure_map_as_set_on_network, signature, policy_group = test_treasure_map_from_alice_to_ursula()

    for ursula_interface_id in treasure_map:
        getter = ALICE.server.get(ursula_interface_id)
        loop = asyncio.get_event_loop()
        value = loop.run_until_complete(getter)
        signature, ursula_pubkey_sig, interface_info = msgpack.loads(value.lstrip(b"uaddr-"))
        port, _interface = msgpack.loads(interface_info)
        assert port in URSULA_PORTS

