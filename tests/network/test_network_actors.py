import asyncio
import datetime

import msgpack
import pytest

from kademlia.utils import digest
from nkms.characters import Ursula, Alice, Character, Bob, congregate
from nkms.network.blockchain_client import list_all_ursulas
from nkms.network.protocols import dht_value_splitter
from nkms.policy.constants import NON_PAYMENT
from nkms.policy.models import PolicyManagerForAlice, PolicyOffer, Policy
from tests.test_utilities import make_fake_ursulas, MockNetworkyStuff

EVENT_LOOP = asyncio.get_event_loop()
asyncio.set_event_loop(EVENT_LOOP)

URSULA_PORT = 7468
NUMBER_OF_URSULAS_IN_NETWORK = 6

URSULAS, URSULA_PORTS = make_fake_ursulas(NUMBER_OF_URSULAS_IN_NETWORK, URSULA_PORT)

ALICE = Alice()
ALICE.attach_server()
ALICE.server.listen(8471)
ALICE.__resource_id = b"some_resource_id"
EVENT_LOOP.run_until_complete(ALICE.server.bootstrap([("127.0.0.1", URSULA_PORT)]))

BOB = Bob(alice=ALICE)
BOB.attach_server()
BOB.server.listen(8475)
EVENT_LOOP.run_until_complete(BOB.server.bootstrap([("127.0.0.1", URSULA_PORT)]))

congregate(ALICE, BOB, URSULAS[0])


def test_all_ursulas_know_about_all_other_ursulas():
    """
    Once launched, all Ursulas know about - and can help locate - all other Ursulas in the network.
    """
    ignorance = []
    for acounter, announcing_ursula in enumerate(list_all_ursulas()):
        for counter, propagating_ursula in enumerate(URSULAS):
            if not digest(announcing_ursula) in propagating_ursula.server.storage:
                ignorance.append((counter, acounter))
    if ignorance:
        pytest.fail(str(["{} didn't know about {}".format(counter, acounter) for counter, acounter in ignorance]))


def test_vladimir_illegal_interface_key_does_not_propagate():
    """
    Although Ursulas propagate each other's interface information, as demonstrated above, they do not propagate
        interface information for Vladimir, an Evil Ursula.
    """
    vladimir = URSULAS[0]
    ursula = URSULAS[1]

    # Ursula hasn't seen any illegal keys.
    assert ursula.server.protocol.illegal_keys_seen == []

    # Vladimir does almost everything right....
    value = vladimir.interface_dht_value()

    # Except he sets an illegal key for his interface.
    illegal_key = "Not allowed to set arbitrary key for this."
    setter = vladimir.server.set(key=illegal_key, value=value)
    loop = asyncio.get_event_loop()
    loop.run_until_complete(setter)

    # Now Ursula has seen an illegal key.
    assert digest(illegal_key) in ursula.server.protocol.illegal_keys_seen


def test_alice_cannot_offer_policy_without_first_finding_ursula():
    """
    Alice can't just offer a Policy if she doesn't know whether any Ursulas are available (she gets Ursula.NotFound).
    """
    networky_stuff = MockNetworkyStuff(URSULAS)
    policy = Policy(ALICE, BOB)

    with pytest.raises(Ursula.NotFound):
        policy_offer = policy.encrypt_payload_for_ursula()


def test_trying_to_find_unknown_actor_raises_not_found():
    """
    Tony the test character can't make reference to a character he doesn't know about yet.
    """
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


def test_alice_finds_ursula():
    """
    With the help of any Ursula, Alice can find a specific Ursula.
    """
    ursula_index = 1
    all_ursulas = list_all_ursulas()
    getter = ALICE.server.get(all_ursulas[ursula_index])
    loop = asyncio.get_event_loop()
    value = loop.run_until_complete(getter)
    _signature, _ursula_pubkey_sig, _hrac, interface_info = dht_value_splitter(value.lstrip(b"uaddr-"),
                                                                               return_remainder=True)
    port = msgpack.loads(interface_info)[0]
    assert port == URSULA_PORT + ursula_index


def test_alice_has_ursulas_public_key_and_uses_it_to_encode_policy_payload():
    """
    Now that Alice has found an Ursula, Alice can make a PolicyGroup, using Ursula's Public Key to encrypt each offer.
    """
    ALICE.__resource_id += b"/unique-again"  # A unique name each time, like a path.
    n = NUMBER_OF_URSULAS_IN_NETWORK

    # Alice needs to find N Ursulas to whom to make her offer.
    networky_stuff = MockNetworkyStuff(URSULAS)
    policy_manager = PolicyManagerForAlice(ALICE)

    policy_group = policy_manager.create_policy_group(
        BOB,
        ALICE.__resource_id,
        m=3,
        n=n,
    )
    # TODO: Make an assertion here.
    return policy_group

def test_alice_enacts_policies_in_policy_group_via_rest():
    policy_group = test_alice_has_ursulas_public_key_and_uses_it_to_encode_policy_payload()

    # Alice has a policy in mind and knows of enough qualifies Ursulas; she crafts an offer for them.
    deposit = NON_PAYMENT
    contract_end_datetime = datetime.datetime.now() + datetime.timedelta(days=5)
    offer = PolicyOffer(policy_group.n, deposit, contract_end_datetime)

    networky_stuff = MockNetworkyStuff(URSULAS)
    policy_group.find_n_ursulas(networky_stuff, offer)
    policy_group.enact_policies(networky_stuff)
    # TODO: Make an assertion
    return policy_group

def test_alice_sets_treasure_map_on_network():
    """
    Having made a PolicyGroup, Alice creates a TreasureMap and sends it to Ursula via the DHT.
    """
    policy_group = test_alice_enacts_policies_in_policy_group_via_rest()

    setter, encrypted_treasure_map, packed_encrypted_treasure_map, signature_for_bob, signature_for_ursula = ALICE.publish_treasure_map(
        policy_group)
    _set_event = EVENT_LOOP.run_until_complete(setter)

    treasure_map_as_set_on_network = URSULAS[0].server.storage[
        digest(policy_group.treasure_map_dht_key())]
    assert treasure_map_as_set_on_network == b"trmap" + packed_encrypted_treasure_map
    return treasure_map_as_set_on_network, signature_for_bob, policy_group


def test_treasure_map_with_bad_id_does_not_propagate():
    """
    In order to prevent spam attacks, Ursula refuses to propagate a TreasureMap whose PolicyGroup ID does not comport to convention.
    """
    illegal_policygroup_id = "This is not a conventional policygroup id"
    policy_group = test_alice_has_ursulas_public_key_and_uses_it_to_encode_policy_payload()

    treasure_map = policy_group.treasure_map

    encrypted_treasure_map, signature = ALICE.encrypt_for(BOB, treasure_map.packed_payload())
    packed_encrypted_treasure_map = msgpack.dumps(encrypted_treasure_map)  # TODO: #114?  Do we even need to pack here?

    setter = ALICE.server.set(illegal_policygroup_id, packed_encrypted_treasure_map)
    _set_event = EVENT_LOOP.run_until_complete(setter)

    with pytest.raises(KeyError):
        URSULAS[0].server.storage[digest(illegal_policygroup_id)]


def test_treasure_map_stored_by_ursula_is_the_correct_one_for_bob():
    """
    The TreasureMap given by Alice to Ursula is the correct one for Bob; he can decrypt and read it.
    """

    treasure_map_as_set_on_network, signature, policy_group = test_alice_sets_treasure_map_on_network()
    _signature_for_ursula, pubkey_sig_alice, hrac, encrypted_treasure_map = dht_value_splitter(
        treasure_map_as_set_on_network[5::], msgpack_remainder=True)  # 5:: to account for prepended "trmap"

    verified, treasure_map_as_decrypted_by_bob = BOB.verify_from(ALICE, signature,
                                                                 encrypted_treasure_map,
                                                                 decrypt=True,
                                                                 signature_is_on_cleartext=True,
                                                                 )
    assert treasure_map_as_decrypted_by_bob == policy_group.treasure_map.packed_payload()
    assert verified is True


def test_bob_can_retreive_the_treasure_map_and_decrypt_it():
    """
    Above, we showed that the TreasureMap saved on the network is the correct one for Bob.  Here, we show
    that Bob can retrieve it with only the information about which he is privy pursuant to the PolicyGroup.
    """
    treasure_map_as_set_on_network, signature, policy_group = test_alice_sets_treasure_map_on_network()
    networky_stuff = MockNetworkyStuff(URSULAS)

    # Of course, in the real world, Bob has sufficient information to reconstitute a PolicyGroup, gleaned, we presume,
    # through a side-channel with Alice.
    treasure_map_from_wire = BOB.get_treasure_map(policy_group, signature)

    assert policy_group.treasure_map == treasure_map_from_wire


def test_treaure_map_is_legit():
    """
    Sure, the TreasureMap can get to Bob, but we also need to know that each Ursula in the TreasureMap is on the network.
    """
    treasure_map_as_set_on_network, signature, policy_group = test_alice_sets_treasure_map_on_network()

    for ursula_interface_id in policy_group.treasure_map:
        getter = ALICE.server.get(ursula_interface_id)
        loop = asyncio.get_event_loop()
        value = loop.run_until_complete(getter)
        signature, ursula_pubkey_sig, hrac, interface_info = dht_value_splitter(value.lstrip(b"uaddr-"),
                                                                                return_remainder=True)
        port = msgpack.loads(interface_info)[0]
        assert port in URSULA_PORTS
