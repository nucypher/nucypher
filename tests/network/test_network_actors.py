import pytest
from hendrix.experience import crosstown_traffic
from hendrix.utils.test_utils import crosstownTaskListDecoratorFactory
from kademlia.utils import digest

from nucypher.characters.unlawful import Vladimir
from nucypher.crypto.api import keccak_digest
from nucypher.crypto.powers import SigningPower
from nucypher.utilities.sandbox.middleware import MockRestMiddleware


def test_all_blockchain_ursulas_know_about_all_other_ursulas(blockchain_ursulas, three_agents):
    """
    Once launched, all Ursulas know about - and can help locate - all other Ursulas in the network.
    """
    token_agent, miner_agent, policy_agent = three_agents
    for address in miner_agent.swarm():
        for propagating_ursula in blockchain_ursulas:
            assert address in propagating_ursula.known_nodes, "{} did not know about {}".format(propagating_ursula, address)


@pytest.mark.skip("What do we want this test to do now?")
def test_blockchain_alice_finds_ursula_via_rest(blockchain_alice, blockchain_ursulas):
    # Imagine alice knows of nobody.
    blockchain_alice.known_nodes = {}

    some_ursula_interface = blockchain_ursulas.pop().rest_interface

    new_nodes = blockchain_alice.learn_from_teacher_node()

    assert len(new_nodes) == len(blockchain_ursulas)

    for ursula in blockchain_ursulas:
        assert ursula.stamp.as_umbral_pubkey() in new_nodes


def test_alice_creates_policy_with_correct_hrac(idle_federated_policy):
    """
    Alice creates a Policy.  It has the proper HRAC, unique per her, Bob, and the uri (resource_id).
    """
    alice = idle_federated_policy.alice
    bob = idle_federated_policy.bob

    assert idle_federated_policy.hrac() == keccak_digest(
        bytes(alice.stamp) + bytes(bob.stamp) + idle_federated_policy.label)


def test_alice_sets_treasure_map(enacted_federated_policy, federated_ursulas):
    """
    Having enacted all the policies of a PolicyGroup, Alice creates a TreasureMap and ...... TODO
    """

    enacted_federated_policy.publish_treasure_map(network_middleware=MockRestMiddleware())

    treasure_map_as_set_on_network = list(federated_ursulas)[0].treasure_maps[
        digest(enacted_federated_policy.treasure_map.public_id())]
    assert treasure_map_as_set_on_network == enacted_federated_policy.treasure_map


def test_treasure_map_stored_by_ursula_is_the_correct_one_for_bob(alice, bob, federated_ursulas, enacted_federated_policy):
    """
    The TreasureMap given by Alice to Ursula is the correct one for Bob; he can decrypt and read it.
    """
    treasure_map_as_set_on_network = list(federated_ursulas)[0].treasure_maps[
        digest(enacted_federated_policy.treasure_map.public_id())]

    hrac_by_bob = bob.construct_policy_hrac(alice.stamp, enacted_federated_policy.label)
    assert enacted_federated_policy.hrac() == hrac_by_bob

    hrac, map_id_by_bob = bob.construct_hrac_and_map_id(alice.stamp, enacted_federated_policy.label)
    assert map_id_by_bob == treasure_map_as_set_on_network.public_id()


def test_bob_can_retreive_the_treasure_map_and_decrypt_it(enacted_federated_policy, federated_ursulas):
    """
    Above, we showed that the TreasureMap saved on the network is the correct one for Bob.  Here, we show
    that Bob can retrieve it with only the information about which he is privy pursuant to the PolicyGroup.
    """
    bob = enacted_federated_policy.bob

    # Of course, in the real world, Bob has sufficient information to reconstitute a PolicyGroup, gleaned, we presume,
    # through a side-channel with Alice.

    # If Bob doesn't know about any Ursulas, he can't find the TreasureMap via the REST swarm:
    with pytest.raises(bob.NotEnoughUrsulas):
        treasure_map_from_wire = bob.get_treasure_map(enacted_federated_policy.alice.stamp,
                                                      enacted_federated_policy.label)

    # Bob finds out about one Ursula (in the real world, a seed node)
    bob.remember_node(list(federated_ursulas)[0])

    # ...and then learns about the rest of the network.
    bob.learn_from_teacher_node(eager=True)

    # Now he'll have better success finding that map.
    treasure_map_from_wire = bob.get_treasure_map(enacted_federated_policy.alice.stamp,
                                                  enacted_federated_policy.label)

    assert enacted_federated_policy.treasure_map == treasure_map_from_wire


def test_treaure_map_is_legit(enacted_federated_policy):
    """
    Sure, the TreasureMap can get to Bob, but we also need to know that each Ursula in the TreasureMap is on the network.
    """
    for ursula_address, _node_id in enacted_federated_policy.treasure_map:
        assert ursula_address in enacted_federated_policy.bob.known_nodes


def test_vladimir_illegal_interface_key_does_not_propagate(blockchain_ursulas):
    """
    Although Ursulas propagate each other's interface information, as demonstrated above,
    they do not propagate interface information for Vladimir.

    Specifically, if Vladimir tries to perform the most obvious imitation attack -
    propagating his own wallet address along with Ursula's information - the validity
    check will catch it and Ursula will refuse to propagate it and also record Vladimir's
    details.
    """
    ursulas = list(blockchain_ursulas)
    ursula_whom_vladimir_will_imitate, other_ursula = ursulas[0], ursulas[1]

    # This Ursula is totally legit...
    ursula_whom_vladimir_will_imitate.verify_node(MockRestMiddleware(),
                                                  accept_federated_only=True)

    # ...until Vladimir sees her on the network and tries to use her public information.
    vladimir = Vladimir.from_target_ursula(ursula_whom_vladimir_will_imitate)

    learning_callers = []
    crosstown_traffic.decorator = crosstownTaskListDecoratorFactory(learning_callers)

    vladimir.network_middleware.propagate_shitty_interface_id(other_ursula, bytes(vladimir))

    # So far, Ursula hasn't noticed any Vladimirs.
    assert other_ursula.suspicious_activities_witnessed['vladimirs'] == []

    # ...but now, Ursula will now try to learn about Vladimir on a different thread.
    # We only passed one node (Vladimir)...
    learn_about_vladimir = learning_callers.pop()
    #  ...so there was only one learning caller in the queue (now none since we popped it just now).
    assert len(learning_callers) == 0

    # OK, so cool, let's see what happens when Ursula tries to learn about Vlad.
    learn_about_vladimir()

    # And indeed, Ursula noticed the situation.
    # She didn't record Vladimir's address.
    assert vladimir.checksum_public_address not in other_ursula.known_nodes

    # But she *did* record the actual Ursula's address.
    assert ursula_whom_vladimir_will_imitate.checksum_public_address in other_ursula.known_nodes

    # Furthermore, she properly marked Vladimir as suspicious.
    assert vladimir in other_ursula.suspicious_activities_witnessed['vladimirs']


def test_alice_refuses_to_make_arrangement_unless_ursula_is_valid(blockchain_alice,
                                                                  idle_blockchain_policy,
                                                                  blockchain_ursulas):
    target = list(blockchain_ursulas)[2]
    # First, let's imagine that Alice has sampled a Vladimir while making this policy.
    vladimir = Vladimir.from_target_ursula(target)

    message = vladimir._signable_interface_info_message()
    signature = vladimir._crypto_power.power_ups(SigningPower).sign(message)

    vladimir.substantiate_stamp()
    vladimir._interface_signature_object = signature

    class FakeArrangement:
        federated = False

    with pytest.raises(vladimir.InvalidNode):
        idle_blockchain_policy.consider_arrangement(network_middleware=blockchain_alice.network_middleware,
                                                    arrangement=FakeArrangement(),
                                                    ursula=vladimir)
