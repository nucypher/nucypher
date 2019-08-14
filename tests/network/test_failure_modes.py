import datetime
import maya
import pytest

from nucypher.network.nodes import Learner
from nucypher.policy.collections import TreasureMap
from nucypher.policy.policies import Policy
from nucypher.utilities.sandbox.middleware import NodeIsDownMiddleware
from functools import partial


def test_bob_does_not_let_a_connection_error_stop_him(enacted_federated_policy,
                                                      federated_ursulas,
                                                      federated_bob,
                                                      federated_alice):
    assert len(federated_bob.known_nodes) == 0
    ursula1 = list(federated_ursulas)[0]
    ursula2 = list(federated_ursulas)[1]

    federated_bob.remember_node(ursula1)

    federated_bob.network_middleware = NodeIsDownMiddleware()
    federated_bob.network_middleware.node_is_down(ursula1)

    with pytest.raises(TreasureMap.NowhereToBeFound):
        federated_bob.get_treasure_map(federated_alice.stamp, enacted_federated_policy.label)

    federated_bob.remember_node(ursula2)

    map = federated_bob.get_treasure_map(federated_alice.stamp, enacted_federated_policy.label)

    assert sorted(list(map.destinations.keys())) == sorted(
        list(u.checksum_address for u in list(federated_ursulas)))


def test_alice_can_grant_even_when_the_first_nodes_she_tries_are_down(federated_alice, federated_bob, federated_ursulas):
    m, n = 2, 3
    policy_end_datetime = maya.now() + datetime.timedelta(days=5)
    label = b"this_is_the_path_to_which_access_is_being_granted"
    federated_alice.known_nodes._nodes = {}

    federated_alice.network_middleware = NodeIsDownMiddleware()

    # OK, her first and only node is down.
    down_node = list(federated_ursulas)[0]
    federated_alice.remember_node(down_node)
    federated_alice.network_middleware.node_is_down(down_node)

    # Here's the command we want to run.
    alice_grant_action = partial(federated_alice.grant, federated_bob, label, m=m, n=n, expiration=policy_end_datetime, timeout=.1)

    # Try a first time, failing because no known nodes are up for Alice to even try to learn from.
    with pytest.raises(down_node.NotEnoughNodes):
        alice_grant_action()

    # Now she learn about one node that *is* up...
    reliable_node = list(federated_ursulas)[1]
    federated_alice.remember_node(reliable_node)

    # ...amidst a few others that are down.
    more_nodes = list(federated_ursulas)[2:10]

    # Alice still only knows aboot two nodes (the one that is down and the new one).
    assert len(federated_alice.known_nodes) == 2

    for node in more_nodes:
        federated_alice.network_middleware.node_is_down(node)

    # Alice can't verify enough nodes to complete the Policy.
    with pytest.raises(Learner.NotEnoughNodes):
        alice_grant_action()

    # Now we'll have a situation where Alice knows about all 10,
    # though only one is up.
    # She'll try to learn about more, but there aren't any.
    # Because she has successfully completed learning, but the nodes about which she learned are down,
    # she'll get a different error.
    for node in more_nodes:
        federated_alice.remember_node(node)
    with pytest.raises(Policy.MoreKFragsThanArrangements):
        alice_grant_action()

    # Now let's let a few of them come up.
    for node in more_nodes[0:4]:
        federated_alice.network_middleware.node_is_up(node)

    # Now the same exact action works.
    policy = alice_grant_action()  # I'm a little surprised this doesn't fail once in a while, if more then 2 of the nodes selected are among those still down.

    # The number of accepted arrangements at least the number of Ursulas we're using (n)
    assert len(policy._accepted_arrangements) >= n

    # The number of actually enacted arrangements is exactly equal to n.
    assert len(policy._enacted_arrangements) == n


def test_node_has_changed_cert(federated_alice, federated_ursulas):
    federated_alice.known_nodes._nodes = {}
    federated_alice.network_middleware = NodeIsDownMiddleware()
    federated_alice.network_middleware.client.certs_are_broken = True

    firstula = list(federated_ursulas)[0]
    federated_alice.remember_node(firstula)
    federated_alice.start_learning_loop(now=True)
    federated_alice.learn_from_teacher_node()

    # Cool - we didn't crash because of SSLError.
    # TODO: Assertions and such.
