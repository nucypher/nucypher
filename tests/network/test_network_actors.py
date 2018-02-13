import asyncio
import datetime

import msgpack
import pytest

from kademlia.utils import digest
from nkms.characters import Ursula, Character
from nkms.crypto.signature import Signature
from nkms.crypto.utils import BytestringSplitter
from nkms.network import blockchain_client
from nkms.network.protocols import dht_value_splitter
from nkms.policy.models import Policy, Contract
from tests.utilities import MockNetworkyStuff, EVENT_LOOP, URSULA_PORT, NUMBER_OF_URSULAS_IN_NETWORK


def test_alice_cannot_offer_policy_without_first_finding_ursula(alice, ursulas):
    """
    Alice can't just make a deal out of thin air if she doesn't know whether any Ursulas are available (she gets Ursula.NotFound).
    """
    networky_stuff = MockNetworkyStuff(ursulas)
    contract = Contract(alice, "some_hrac,", datetime.datetime.now() + datetime.timedelta(days=5), ursula=ursulas[0])

    with pytest.raises(Ursula.NotFound):
        policy_offer = contract.encrypt_payload_for_ursula()


def test_all_ursulas_know_about_all_other_ursulas(ursulas):
    """
    Once launched, all Ursulas know about - and can help locate - all other Ursulas in the network.
    """
    ignorance = []
    for acounter, announcing_ursula in enumerate(blockchain_client._ursulas_on_blockchain):
        for counter, propagating_ursula in enumerate(ursulas):
            if not digest(announcing_ursula) in propagating_ursula.server.storage:
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
    value = vladimir.interface_dht_value()

    # Except he sets an illegal key for his interface.
    illegal_key = "Not allowed to set arbitrary key for this."
    setter = vladimir.server.set(key=illegal_key, value=value)
    loop = asyncio.get_event_loop()
    loop.run_until_complete(setter)

    # Now Ursula has seen an illegal key.
    assert digest(illegal_key) in ursula.server.protocol.illegal_keys_seen


def test_trying_to_find_unknown_actor_raises_not_found(alice):
    """
    Tony the test character can't make reference to a character he doesn't know about yet.
    """
    tony_clifton = Character()

    message = b"some_message"
    signature = alice.seal(message)

    # Tony can't reference Alice...

    # TODO: This may not actually be necessary anymore since we are mostly doing Character.from_public_keys()
    # with pytest.raises(Character.NotFound):
    #     verification = tony_clifton.verify_from(alice, message, signature)

    # ...before learning about Alice.
    tony_clifton.learn_about_actor(alice)
    verification, NO_DECRYPTION_PERFORMED = tony_clifton.verify_from(alice, message, signature=signature)

    assert verification is True


def test_alice_finds_ursula(alice, ursulas):
    """
    With the help of any Ursula, Alice can find a specific Ursula.
    """
    ursula_index = 1
    all_ursulas = blockchain_client._ursulas_on_blockchain
    getter = alice.server.get(all_ursulas[ursula_index])
    loop = asyncio.get_event_loop()
    value = loop.run_until_complete(getter)
    _signature, _ursula_pubkey_sig, _hrac, interface_info = dht_value_splitter(value.lstrip(b"uaddr-"),
                                                                               return_remainder=True)
    port = msgpack.loads(interface_info)[0]
    assert port == URSULA_PORT + ursula_index


def test_alice_creates_policy_group_with_correct_hrac(idle_policy):
    """
    Alice creates a PolicyGroup.  It has the proper HRAC, unique per her, Bob, and the uri (resource_id).
    """
    alice = idle_policy.alice
    bob = idle_policy.bob

    assert idle_policy.hrac() == idle_policy.hash(
        bytes(alice.seal) + bytes(bob.seal) + alice.__resource_id)


def test_alice_sets_treasure_map_on_network(enacted_policy, ursulas):
    """
    Having enacted all the policies of a PolicyGroup, Alice creates a TreasureMap and sends it to Ursula via the DHT.
    """
    _, packed_encrypted_treasure_map, _, _ = enacted_policy.publish_treasure_map()

    treasure_map_as_set_on_network = ursulas[0].server.storage[
        digest(enacted_policy.treasure_map_dht_key())]
    assert treasure_map_as_set_on_network == b"trmap" + packed_encrypted_treasure_map


def test_treasure_map_with_bad_id_does_not_propagate(idle_policy, ursulas):
    """
    In order to prevent spam attacks, Ursula refuses to propagate a TreasureMap whose PolicyGroup ID does not comport to convention.
    """
    illegal_policygroup_id = "This is not a conventional policygroup id"
    alice = idle_policy.alice
    bob = idle_policy.bob
    treasure_map = idle_policy.treasure_map

    encrypted_treasure_map, signature = alice.encrypt_for(bob, treasure_map.packed_payload())
    packed_encrypted_treasure_map = msgpack.dumps(encrypted_treasure_map)  # TODO: #114?  Do we even need to pack here?

    setter = alice.server.set(illegal_policygroup_id, packed_encrypted_treasure_map)
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

    _signature_for_ursula, pubkey_sig_alice, hrac, encrypted_treasure_map = dht_value_splitter(
        treasure_map_as_set_on_network[5::], msgpack_remainder=True)  # 5:: to account for prepended "trmap"

    verified, cleartext = treasure_map_as_decrypted_by_bob = bob.verify_from(alice,
                                                                 encrypted_treasure_map,
                                                                 decrypt=True,
                                                                 signature_is_on_cleartext=True,
                                                                 )
    _alices_signature, treasure_map_as_decrypted_by_bob = BytestringSplitter(Signature)(cleartext, return_remainder=True)

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
    treasure_map_from_wire = bob.get_treasure_map(enacted_policy)

    assert enacted_policy.treasure_map == treasure_map_from_wire


def test_treaure_map_is_legit(enacted_policy):
    """
    Sure, the TreasureMap can get to Bob, but we also need to know that each Ursula in the TreasureMap is on the network.
    """
    alice = enacted_policy.alice
    for ursula_interface_id in enacted_policy.treasure_map:
        getter = alice.server.get(ursula_interface_id)
        loop = asyncio.get_event_loop()
        value = loop.run_until_complete(getter)
        signature, ursula_pubkey_sig, hrac, interface_info = dht_value_splitter(value.lstrip(b"uaddr-"),
                                                                                return_remainder=True)
        port = msgpack.loads(interface_info)[0]
        legal_ports = range(NUMBER_OF_URSULAS_IN_NETWORK, NUMBER_OF_URSULAS_IN_NETWORK + URSULA_PORT)
        assert port in legal_ports
