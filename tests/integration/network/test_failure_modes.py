


import datetime
from functools import partial

import maya
import pytest

from nucypher.policy.policies import Policy
from tests.utils.middleware import NodeIsDownMiddleware


def test_alice_can_grant_even_when_the_first_nodes_she_tries_are_down(
    blockchain_alice, blockchain_bob, blockchain_ursulas
):
    threshold, shares = 2, 3
    policy_end_datetime = maya.now() + datetime.timedelta(days=5)
    label = b"this_is_the_path_to_which_access_is_being_granted"
    blockchain_alice.known_nodes.current_state._nodes = {}

    blockchain_alice.network_middleware = NodeIsDownMiddleware()

    # OK, her first and only node is down.
    down_node = list(blockchain_ursulas)[0]
    blockchain_alice.remember_node(down_node)
    blockchain_alice.network_middleware.node_is_down(down_node)

    # Here's the command we want to run.
    alice_grant_action = partial(
        blockchain_alice.grant,
        blockchain_bob,
        label,
        threshold=threshold,
        shares=shares,
        expiration=policy_end_datetime,
        timeout=0.1,
    )

    # Go!
    blockchain_alice.start_learning_loop()

    # Now we'll have a situation where Alice knows about all 10,
    # though only one is up.

    # She'll try to learn about more, but there aren't any.
    # Because she has successfully completed learning, but the nodes about which she learned are down,
    # she'll get a different error.

    more_nodes = list(blockchain_ursulas)[1:10]
    for node in more_nodes:
        blockchain_alice.network_middleware.node_is_down(node)

    for node in more_nodes:
        blockchain_alice.remember_node(node)
    with pytest.raises(Policy.NotEnoughUrsulas):
        alice_grant_action()

    # Now let's let a few of them come up.
    for node in more_nodes[0:4]:
        blockchain_alice.network_middleware.node_is_up(node)

    # Now the same exact action works.
    # TODO: This action only succeeds here because we are forcing
    #       grant to accept the ursulas that just came back online (handpicked_ursulas).
    #       Since there are now enough Ursulas online, this action *can* succeed without forcing sample.
    policy = alice_grant_action(ursulas=more_nodes[:3])

    # TODO: This is how it's actually done. How can we measure such random results?
    #       The below line will fail with ? probability, if more then 2 of the nodes selected
    #       are among those still down.
    # policy = alice_grant_action()
    assert policy.shares == shares


def test_node_has_changed_cert(blockchain_alice, blockchain_ursulas):
    blockchain_alice.known_nodes.current_state._nodes = {}
    blockchain_alice.network_middleware = NodeIsDownMiddleware()
    blockchain_alice.network_middleware.client.certs_are_broken = True

    firstula = list(blockchain_ursulas)[0]
    blockchain_alice.remember_node(firstula)
    blockchain_alice.start_learning_loop(now=True)
    blockchain_alice.learn_from_teacher_node()

    # Cool - we didn't crash because of SSLError.
    # TODO: Assertions and such.
