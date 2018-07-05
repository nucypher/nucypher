import asyncio

import msgpack
import pytest
from constant_sorrow import constants, default_constant_splitter
from kademlia.utils import digest

from nucypher.crypto.api import keccak_digest
from nucypher.crypto.kits import UmbralMessageKit
from nucypher.policy.models import TreasureMap
from tests.utilities import TEST_EVENT_LOOP, MockRestMiddleware


@pytest.mark.usefixtures('testerchain')
def test_all_ursulas_know_about_all_other_ursulas(ursulas, three_agents):
    """
    Once launched, all Ursulas know about - and can help locate - all other Ursulas in the network.
    """
    token_agent, miner_agent, policy_agent = three_agents

    ignorance = []
    for acounter, announcing_ursula in enumerate(miner_agent.swarm()):
        for counter, propagating_ursula in enumerate(ursulas):
            announcing_ursula_ether_address, announcing_ursula_id = announcing_ursula
            if not digest(bytes(announcing_ursula_id)) in propagating_ursula.server.storage:
                ignorance.append((counter, acounter))
    if ignorance:
        pytest.fail(str(["{} didn't know about {}".format(counter, acounter) for counter, acounter in ignorance]))


def test_vladimir_illegal_interface_key_does_not_propagate(ursulas):
    """
    Although Ursulas propagate each other's interface information, as demonstrated above, they do not propagate
    interface information for Vladimir, an Evil Ursula.
    """
    ursulas = list(ursulas)
    vladimir, ursula = ursulas[0], ursulas[1]

    # Ursula hasn't seen any illegal keys.
    assert ursula.dht_server.protocol.illegal_keys_seen == []

    # Vladimir does almost everything right....
    value = vladimir.interface_info_with_metadata()

    # Except he sets an illegal key for his interface.
    illegal_key = b"Not allowed to set arbitrary key for this."
    setter = vladimir.dht_server.set(key=illegal_key, value=value)
    loop = asyncio.get_event_loop()
    loop.run_until_complete(setter)

    # Now Ursula has seen an illegal key.
    assert digest(illegal_key) in ursula.dht_server.protocol.illegal_keys_seen


@pytest.mark.skip("What do we want this test to do now?")
def test_alice_finds_ursula_via_rest(alice, ursulas):

    # Imagine alice knows of nobody.
    alice._known_nodes = {}

    some_ursula_interface = ursulas.pop().rest_interface

    new_nodes = alice.learn_from_teacher_node()

    assert len(new_nodes) == len(ursulas)

    for ursula in ursulas:
        assert ursula.stamp.as_umbral_pubkey() in new_nodes


def test_alice_creates_policy_group_with_correct_hrac(idle_federated_policy):
    """
    Alice creates a PolicyGroup.  It has the proper HRAC, unique per her, Bob, and the uri (resource_id).
    """
    alice = idle_federated_policy.alice
    bob = idle_federated_policy.bob

    assert idle_federated_policy.hrac() == keccak_digest(
        bytes(alice.stamp) + bytes(bob.stamp) + alice.__resource_id)


def test_alice_sets_treasure_map(enacted_federated_policy, ursulas):
    """
    Having enacted all the policies of a PolicyGroup, Alice creates a TreasureMap and sends it to Ursula via the DHT.
    """
    networky_stuff = MockRestMiddleware()
    enacted_federated_policy.publish_treasure_map(network_middleare=networky_stuff)

    treasure_map_as_set_on_network = list(ursulas)[0].dht_server.storage[
        digest(enacted_federated_policy.treasure_map_dht_key())]
    assert treasure_map_as_set_on_network == constants.BYTESTRING_IS_TREASURE_MAP + bytes(enacted_federated_policy.treasure_map)


@pytest.mark.skip("Needs cleanup.")
def test_treasure_map_with_bad_id_does_not_propagate(idle_federated_policy, ursulas):
    """
    In order to prevent spam attacks, Ursula refuses to propagate a TreasureMap whose PolicyGroup ID does not comport to convention.
    """
    illegal_policygroup_id = b"This is not a conventional policygroup id"
    alice = idle_federated_policy.alice
    bob = idle_federated_policy.bob
    treasure_map = idle_federated_policy.treasure_map

    message_kit, signature = alice.encrypt_for(bob, treasure_map.packed_payload())

    alice.network_middleware.put_treasure_map_on_node(node=ursulas[1],
                                                       map_id=illegal_policygroup_id,
                                                       map_payload=message_kit.to_bytes())

    # setter = alice.server.set(illegal_policygroup_id, message_kit.to_bytes())
    # _set_event = TEST_EVENT_LOOP.run_until_complete(setter)

    # with pytest.raises(KeyError):
    #     _ = ursulas_on_network[0].server.storage[digest(illegal_policygroup_id)]
    assert False


def test_treasure_map_stored_by_ursula_is_the_correct_one_for_bob(alice, bob, ursulas, enacted_federated_policy):
    """
    The TreasureMap given by Alice to Ursula is the correct one for Bob; he can decrypt and read it.
    """
    treasure_map_as_set_on_network = list(ursulas)[0].dht_server.storage[
        digest(enacted_federated_policy.treasure_map_dht_key())]

    header, payload = default_constant_splitter(treasure_map_as_set_on_networka)

    treasure_map = TreasureMap.from_bytes(payload)

    assert header == constants.BYTESTRING_IS_TREASURE_MAP

    tmap_message_kit = UmbralMessageKit.from_bytes(encrypted_treasure_map)
    verified, treasure_map_as_decrypted_by_bob = bob.verify_from(alice,
                                           tmap_message_kit,
                                           decrypt=True)

    assert treasure_map_as_decrypted_by_bob == enacted_federated_policy.treasure_map.packed_payload()
    assert verified is True


@pytest.mark.usefixtures("treasure_map_is_set_on_dht")
def test_bob_can_retreive_the_treasure_map_and_decrypt_it(enacted_federated_policy, ursulas):
    """
    Above, we showed that the TreasureMap saved on the network is the correct one for Bob.  Here, we show
    that Bob can retrieve it with only the information about which he is privy pursuant to the PolicyGroup.
    """
    bob = enacted_federated_policy.bob
    _ = MockRestMiddleware()

    # Of course, in the real world, Bob has sufficient information to reconstitute a PolicyGroup, gleaned, we presume,
    # through a side-channel with Alice.

    # If Bob doesn't know about any Ursulas, he can't find the TreasureMap via the REST swarm:
    with pytest.raises(bob.NotEnoughUrsulas):
        treasure_map_from_wire = bob.get_treasure_map(enacted_federated_policy.alice.stamp, enacted_federated_policy.hrac())

    # Let's imagine he has learned about some - say, from the blockchain.
    bob._known_nodes = {u.interface_info_with_metadata(): u for u in ursulas}

    # Now try.
    treasure_map_from_wire = bob.get_treasure_map(enacted_federated_policy.alice.stamp, enacted_federated_policy.hrac())

    assert enacted_federated_policy.treasure_map == treasure_map_from_wire


def test_treaure_map_is_legit(enacted_federated_policy):
    """
    Sure, the TreasureMap can get to Bob, but we also need to know that each Ursula in the TreasureMap is on the network.
    """
    alice = enacted_federated_policy.alice
    for ursula_interface_id in enacted_federated_policy.treasure_map:
        value = alice.server.get_now(ursula_interface_id)
        header, signature, ursula_pubkey_sig, interface_info = dht_value_splitter(value, return_remainder=True)
        assert header == constants.BYTESTRING_IS_URSULA_IFACE_INFO
        port = msgpack.loads(interface_info)[1]
        legal_ports = range(int(constants.NUMBER_OF_URSULAS_IN_NETWORK), int(constants.NUMBER_OF_URSULAS_IN_NETWORK+constants.URSULA_PORT_SEED))
        assert port in legal_ports
