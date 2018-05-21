import asyncio

import msgpack
import pytest
from constant_sorrow import constants
from kademlia.utils import digest

from nucypher.crypto.api import keccak_digest
from nucypher.crypto.kits import UmbralMessageKit
from nucypher.network import blockchain_client
from nucypher.network.protocols import dht_value_splitter, dht_with_hrac_splitter
from tests.utilities import MockNetworkyStuff, EVENT_LOOP, URSULA_PORT, NUMBER_OF_URSULAS_IN_NETWORK


def test_all_ursulas_know_about_all_other_ursulas(ursulas):
    """
    Once launched, all Ursulas know about - and can help locate - all other Ursulas in the network.
    """
    ignorance = []
    for acounter, announcing_ursula in enumerate(blockchain_client._ursulas_on_blockchain):
        for counter, propagating_ursula in enumerate(ursulas):
            if not digest(bytes(announcing_ursula)) in propagating_ursula.server.storage:
                ignorance.append((counter, acounter))
    if ignorance:
        pytest.fail(str(["{} didn't know about {}".format(counter, acounter) for counter, acounter in ignorance]))


def test_vladimir_illegal_interface_key_does_not_propagate(ursulas):
    """
    Although Ursulas propagate each other's interface information, as demonstrated above, they do not propagate
        interface information for Vladimir, an Evil Ursula.
    """
    vladimir = ursulas[0]
    ursula = ursulas[1]

    # Ursula hasn't seen any illegal keys.
    assert ursula.server.protocol.illegal_keys_seen == []

    # Vladimir does almost everything right....
    value = vladimir.interface_info_with_metadata()

    # Except he sets an illegal key for his interface.
    illegal_key = b"Not allowed to set arbitrary key for this."
    setter = vladimir.server.set(key=illegal_key, value=value)
    loop = asyncio.get_event_loop()
    loop.run_until_complete(setter)

    # Now Ursula has seen an illegal key.
    assert digest(illegal_key) in ursula.server.protocol.illegal_keys_seen


def test_alice_finds_ursula_via_dht(alice, ursulas):
    """
    With the help of any Ursula, Alice can find a specific Ursula.
    """
    ursula_index = 1
    all_ursulas = blockchain_client._ursulas_on_blockchain
    value = alice.server.get_now(all_ursulas[ursula_index])
    header, _signature, _ursula_pubkey_sig, interface_info = dht_value_splitter(value,
                                                                               return_remainder=True)

    assert header == constants.BYTESTRING_IS_URSULA_IFACE_INFO
    port = msgpack.loads(interface_info)[1]
    assert port == URSULA_PORT + ursula_index


def test_alice_finds_ursula_via_rest(alice, ursulas):
    networky_stuff = MockNetworkyStuff(ursulas)

    # Imagine alice knows of nobody.
    alice.known_nodes = {}

    new_nodes = alice.learn_about_nodes(address="https://localhost", port=ursulas[0].rest_port)
    assert len(new_nodes) == len(ursulas)

    for ursula in ursulas:
        assert ursula.stamp.as_umbral_pubkey() in new_nodes


def test_alice_creates_policy_group_with_correct_hrac(idle_policy):
    """
    Alice creates a PolicyGroup.  It has the proper HRAC, unique per her, Bob, and the uri (resource_id).
    """
    alice = idle_policy.alice
    bob = idle_policy.bob

    assert idle_policy.hrac() == keccak_digest(
        bytes(alice.stamp) + bytes(bob.stamp) + alice.__resource_id)


def test_alice_sets_treasure_map_on_network(enacted_policy, ursulas):
    """
    Having enacted all the policies of a PolicyGroup, Alice creates a TreasureMap and sends it to Ursula via the DHT.
    """
    networky_stuff = MockNetworkyStuff(ursulas)
    _, packed_encrypted_treasure_map, _, _ = enacted_policy.publish_treasure_map(networky_stuff=networky_stuff, use_dht=True)

    treasure_map_as_set_on_network = ursulas[0].server.storage[
        digest(enacted_policy.treasure_map_dht_key())]
    assert treasure_map_as_set_on_network == constants.BYTESTRING_IS_TREASURE_MAP + packed_encrypted_treasure_map


def test_treasure_map_with_bad_id_does_not_propagate(idle_policy, ursulas):
    """
    In order to prevent spam attacks, Ursula refuses to propagate a TreasureMap whose PolicyGroup ID does not comport to convention.
    """
    illegal_policygroup_id = b"This is not a conventional policygroup id"
    alice = idle_policy.alice
    bob = idle_policy.bob
    treasure_map = idle_policy.treasure_map

    message_kit, signature = alice.encrypt_for(bob, treasure_map.packed_payload())

    setter = alice.server.set(illegal_policygroup_id, message_kit.to_bytes())
    _set_event = EVENT_LOOP.run_until_complete(setter)

    with pytest.raises(KeyError):
        ursulas[0].server.storage[digest(illegal_policygroup_id)]


@pytest.mark.usefixtures("treasure_map_is_set_on_dht")
def test_treasure_map_stored_by_ursula_is_the_correct_one_for_bob(alice, bob, ursulas, enacted_policy):
    """
    The TreasureMap given by Alice to Ursula is the correct one for Bob; he can decrypt and read it.
    """
    treasure_map_as_set_on_network = ursulas[0].server.storage[
        digest(enacted_policy.treasure_map_dht_key())]

    header, _signature_for_ursula, pubkey_sig_alice, hrac, encrypted_treasure_map = dht_with_hrac_splitter(
        treasure_map_as_set_on_network, return_remainder=True)

    assert header == constants.BYTESTRING_IS_TREASURE_MAP

    tmap_message_kit = UmbralMessageKit.from_bytes(encrypted_treasure_map)
    verified, treasure_map_as_decrypted_by_bob = bob.verify_from(alice,
                                           tmap_message_kit,
                                           decrypt=True,
                                           )

    assert treasure_map_as_decrypted_by_bob == enacted_policy.treasure_map.packed_payload()
    assert verified is True


@pytest.mark.usefixtures("treasure_map_is_set_on_dht")
def test_bob_can_retreive_the_treasure_map_and_decrypt_it(enacted_policy, ursulas):
    """
    Above, we showed that the TreasureMap saved on the network is the correct one for Bob.  Here, we show
    that Bob can retrieve it with only the information about which he is privy pursuant to the PolicyGroup.
    """
    bob = enacted_policy.bob
    networky_stuff = MockNetworkyStuff(ursulas)

    # Of course, in the real world, Bob has sufficient information to reconstitute a PolicyGroup, gleaned, we presume,
    # through a side-channel with Alice.

    # If Bob doesn't know about any Ursulas, he can't find the TreasureMap via the REST swarm:
    with pytest.raises(bob.NotEnoughUrsulas):
        treasure_map_from_wire = bob.get_treasure_map(enacted_policy.alice.stamp, enacted_policy.hrac())

    # Let's imagine he has learned about some - say, from the blockchain.
    bob.known_nodes = {u.interface_info_with_metadata(): u for u in ursulas}

    # Now try.
    treasure_map_from_wire = bob.get_treasure_map(enacted_policy.alice.stamp, enacted_policy.hrac())

    assert enacted_policy.treasure_map == treasure_map_from_wire


def test_treaure_map_is_legit(enacted_policy):
    """
    Sure, the TreasureMap can get to Bob, but we also need to know that each Ursula in the TreasureMap is on the network.
    """
    alice = enacted_policy.alice
    for ursula_interface_id in enacted_policy.treasure_map:
        value = alice.server.get_now(ursula_interface_id)
        header, signature, ursula_pubkey_sig, interface_info = dht_value_splitter(value,
                                                                                return_remainder=True)
        assert header == constants.BYTESTRING_IS_URSULA_IFACE_INFO
        port = msgpack.loads(interface_info)[1]
        legal_ports = range(NUMBER_OF_URSULAS_IN_NETWORK, NUMBER_OF_URSULAS_IN_NETWORK + URSULA_PORT)
        assert port in legal_ports


# # TODO: Have Alice inherit from PolicyAuthor
# def test_alice_finds_ursulas_from_blockchain(chain, mock_miner_agent, mock_token_deployer):
#     mock_token_deployer._global_airdrop(amount=10000)
#
#     # Create some miners to find
#     _, *miner_addresses = chain._chain.web3.eth.accounts[1:]
#     spawn_miners(miner_addresses, mock_miner_agent, mock_miner_agent.token_agent._deployer._M, 100)
#
#     chain.wait_time(mock_miner_agent._deployer._hours_per_period)
#
#     reenc_nodes = mock_miner_agent.sample(quantity=4)
#     assert len(reenc_nodes) >= 4
