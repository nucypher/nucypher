"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""


import pytest
import pytest_twisted
from twisted.internet import threads

from umbral import pre
from umbral.kfrags import KFrag
from umbral.cfrags import CapsuleFrag

from nucypher.crypto.powers import DecryptingPower 
from nucypher.utilities.sandbox.middleware import MockRestMiddleware


def test_bob_cannot_follow_the_treasure_map_in_isolation(enacted_federated_policy, federated_bob):

    # Assume for the moment that Bob has already received a TreasureMap, perhaps via a side channel.
    hrac, treasure_map = enacted_federated_policy.hrac(), enacted_federated_policy.treasure_map
    federated_bob.treasure_maps[treasure_map.public_id()] = treasure_map

    # Bob knows of no Ursulas.
    assert len(federated_bob.known_nodes) == 0

    # He can't successfully follow the TreasureMap until he learns of a node to ask.
    unknown, known = federated_bob.peek_at_treasure_map(map_id=treasure_map.public_id())
    assert len(known) == 0

    # TODO: Show that even with learning loop going, nothing happens here.
    # Probably use Clock?
    federated_bob.follow_treasure_map(treasure_map=treasure_map)
    assert len(known) == 0


def test_bob_already_knows_all_nodes_in_treasure_map(enacted_federated_policy, federated_ursulas, federated_bob,
                                                     federated_alice):
    # Bob knows of no Ursulas.
    assert len(federated_bob.known_nodes) == 0

    # Now we'll inform Bob of some Ursulas.
    for ursula in federated_ursulas:
        federated_bob.remember_node(ursula)

    # Now, Bob can get the TreasureMap all by himself, and doesn't need a side channel.
    map = federated_bob.get_treasure_map(federated_alice.stamp, enacted_federated_policy.label)
    unknown, known = federated_bob.peek_at_treasure_map(treasure_map=map)

    # He finds that he didn't need to discover any new nodes...
    assert len(unknown) == 0

    # ...because he already knew of all the Ursulas on the map.
    assert len(known) == len(enacted_federated_policy.treasure_map)


@pytest_twisted.inlineCallbacks
def test_bob_can_follow_treasure_map_even_if_he_only_knows_of_one_node(enacted_federated_policy,
                                                                       federated_ursulas,
                                                                       certificates_tempdir):
    """
    Similar to above, but this time, we'll show that if Bob can connect to a single node, he can
    learn enough to follow the TreasureMap.

    Also, we'll get the TreasureMap from the hrac alone (ie, not via a side channel).
    """

    from nucypher.characters.lawful import Bob

    bob = Bob(network_middleware=MockRestMiddleware(),
              start_learning_now=False,
              abort_on_learning_error=True,
              federated_only=True)

    # Again, let's assume that he received the TreasureMap via a side channel.
    hrac, treasure_map = enacted_federated_policy.hrac(), enacted_federated_policy.treasure_map
    map_id = treasure_map.public_id()
    bob.treasure_maps[map_id] = treasure_map

    # Now, let's create a scenario in which Bob knows of only one node.
    assert len(bob.known_nodes) == 0
    first_ursula = list(federated_ursulas).pop(0)
    bob.remember_node(first_ursula)
    assert len(bob.known_nodes) == 1

    # This time, when he follows the TreasureMap...
    unknown_nodes, known_nodes = bob.peek_at_treasure_map(map_id=map_id)

    # Bob already knew about one node; the rest are unknown.
    assert len(unknown_nodes) == len(treasure_map) - 1

    # He needs to actually follow the treasure map to get the rest.
    bob.follow_treasure_map(map_id=map_id)

    # The nodes in the learning loop are now his top target, but he's not learning yet.
    assert not bob._learning_task.running

    # ...so he hasn't learned anything (ie, Bob still knows of just one node).
    assert len(bob.known_nodes) == 1

    # Now, we'll start his learning loop.
    bob.start_learning_loop()

    # ...and block until the unknown_nodes have all been found.
    d = threads.deferToThread(bob.block_until_specific_nodes_are_known, unknown_nodes)
    yield d

    # ...and he now has no more unknown_nodes.
    assert len(bob.known_nodes) == len(treasure_map)


def test_bob_can_issue_a_work_order_to_a_specific_ursula(enacted_federated_policy, federated_bob,
                                                         federated_alice, federated_ursulas, capsule_side_channel):
    """
    Now that Bob has his list of Ursulas, he can issue a WorkOrder to one. Upon receiving the WorkOrder, Ursula
    saves it and responds by re-encrypting and giving Bob a cFrag.

    This is a multipart test; it shows proper relations between the Characters Ursula and Bob and also proper
    interchange between a KFrag, Capsule, and CFrag object in the context of REST-driven proxy re-encryption.
    """

    # We pick up our story with Bob already having followed the treasure map above, ie:
    hrac, treasure_map = enacted_federated_policy.hrac(), enacted_federated_policy.treasure_map
    map_id = treasure_map.public_id()
    federated_bob.treasure_maps[map_id] = treasure_map
    federated_bob.start_learning_loop()

    federated_bob.follow_treasure_map(map_id=map_id, block=True, timeout=1)

    assert len(federated_bob.known_nodes) == len(federated_ursulas)

    # Bob has no saved work orders yet, ever.
    assert len(federated_bob._saved_work_orders) == 0

    # We'll test against just a single Ursula - here, we make a WorkOrder for just one.
    # We can pass any number of capsules as args; here we pass just one.
    capsule = capsule_side_channel[0].capsule
    capsule.set_correctness_keys(delegating=enacted_federated_policy.public_key,
                                 receiving=federated_bob.public_keys(DecryptingPower),
                                 verifying=federated_alice.stamp.as_umbral_pubkey())
    work_orders = federated_bob.generate_work_orders(map_id, capsule, num_ursulas=1)

    # Again: one Ursula, one work_order.
    assert len(work_orders) == 1

    # Bob saved the WorkOrder.
    assert len(federated_bob._saved_work_orders) == 1
    # And the Ursula.
    assert len(federated_bob._saved_work_orders.ursulas) == 1

    ursula_id, work_order = list(work_orders.items())[0]

    # The work order is not yet complete, of course.
    assert work_order.completed is False

    # **** RE-ENCRYPTION HAPPENS HERE! ****
    cfrags = federated_bob.get_reencrypted_cfrags(work_order)

    # We only gave one Capsule, so we only got one cFrag.
    assert len(cfrags) == 1
    the_cfrag = cfrags[0]

    # ...and the work order is complete.
    assert work_order.completed

    # Attach the CFrag to the Capsule.
    capsule.attach_cfrag(the_cfrag)

    # Having received the cFrag, Bob also saved the WorkOrder as complete.
    assert len(federated_bob._saved_work_orders.by_ursula[ursula_id]) == 1

    # OK, so cool - Bob has his cFrag!  Let's make sure everything went properly.  First, we'll show that it is in fact
    # the correct cFrag (ie, that Ursula performed re-encryption properly).
    for u in federated_ursulas:
        if u.rest_information()[0].port == work_order.ursula.rest_information()[0].port:
            ursula = u
            break
    else:
        raise RuntimeError("We've lost track of the Ursula that has the WorkOrder. Can't really proceed.")

    kfrag_bytes = ursula.datastore.get_policy_arrangement(
        work_order.arrangement_id.hex().encode()).kfrag
    the_kfrag = KFrag.from_bytes(kfrag_bytes)
    the_correct_cfrag = pre.reencrypt(the_kfrag, capsule)

    # The first CFRAG_LENGTH_WITHOUT_PROOF bytes (ie, the cfrag proper, not the proof material), are the same:
    assert bytes(the_cfrag)[:CapsuleFrag.expected_bytes_length()] == bytes(
        the_correct_cfrag)[:CapsuleFrag.expected_bytes_length()]  # It's the correct cfrag!

    assert the_correct_cfrag.verify_correctness(capsule)

    # Now we'll show that Ursula saved the correct WorkOrder.
    work_orders_from_bob = ursula.work_orders(bob=federated_bob)
    assert len(work_orders_from_bob) == 1
    assert work_orders_from_bob[0] == work_order


def test_bob_remembers_that_he_has_cfrags_for_a_particular_capsule(enacted_federated_policy, federated_bob,
                                                                   federated_ursulas, capsule_side_channel):
    # In our last episode, Bob made a WorkOrder for the capsule...
    assert len(federated_bob._saved_work_orders.by_capsule(capsule_side_channel[0].capsule)) == 1
    # ...and he used it to obtain a CFrag from Ursula.
    assert len(capsule_side_channel[0].capsule._attached_cfrags) == 1

    # He can also get a dict of {Ursula:WorkOrder} by looking them up from the capsule.
    work_orders_by_capsule = federated_bob._saved_work_orders.by_capsule(capsule_side_channel[0].capsule)

    # Bob has just one WorkOrder from that one Ursula.
    assert len(work_orders_by_capsule) == 1
    saved_work_order = list(work_orders_by_capsule.values())[0]

    # The rest of this test will show that if Bob generates another WorkOrder, it's for a *different* Ursula.
    generated_work_orders = federated_bob.generate_work_orders(enacted_federated_policy.treasure_map.public_id(),
                                                               capsule_side_channel[0].capsule,
                                                               num_ursulas=1)
    id_of_this_new_ursula, new_work_order = list(generated_work_orders.items())[0]

    # This new Ursula isn't the same one to whom we've already issued a WorkOrder.
    id_of_ursula_from_whom_we_already_have_a_cfrag = list(work_orders_by_capsule.keys())[0]
    assert id_of_ursula_from_whom_we_already_have_a_cfrag != id_of_this_new_ursula

    # ...and, although this WorkOrder has the same capsules as the saved one...
    for (new_item, saved_item) in zip(new_work_order.tasks, saved_work_order.tasks):
        assert new_item.capsule == saved_item.capsule

    # ...it's not the same WorkOrder.
    assert new_work_order != saved_work_order

    # We can get a new CFrag, just like last time.
    cfrags = federated_bob.get_reencrypted_cfrags(new_work_order)

    # Again: one Capsule, one cFrag.
    assert len(cfrags) == 1
    new_cfrag = cfrags[0]

    # Attach the CFrag to the Capsule.
    capsule_side_channel[0].capsule.attach_cfrag(new_cfrag)


def test_bob_gathers_and_combines(enacted_federated_policy, federated_bob, federated_alice, capsule_side_channel):
    # The side channel delivers all that Bob needs at this point:
    # - A single MessageKit, containing a Capsule
    # - A representation of the data source
    the_message_kit, the_data_source = capsule_side_channel

    # Bob has saved two WorkOrders so far.
    assert len(federated_bob._saved_work_orders) == 2

    # ...but the policy requires us to collect more cfrags.
    assert len(federated_bob._saved_work_orders) < enacted_federated_policy.treasure_map.m

    # Bob can't decrypt yet with just two CFrags.  He needs to gather at least m.
    with pytest.raises(pre.GenericUmbralError):
        federated_bob.decrypt(the_message_kit)

    number_left_to_collect = enacted_federated_policy.treasure_map.m - len(federated_bob._saved_work_orders)

    new_work_orders = federated_bob.generate_work_orders(enacted_federated_policy.treasure_map.public_id(),
                                                         the_message_kit.capsule,
                                                         num_ursulas=number_left_to_collect)
    _id_of_yet_another_ursula, new_work_order = list(new_work_orders.items())[0]

    cfrags = federated_bob.get_reencrypted_cfrags(new_work_order)
    the_message_kit.capsule.attach_cfrag(cfrags[0])

    # Now.
    # At long last.
    cleartext = federated_bob.verify_from(the_data_source, the_message_kit,
                                          decrypt=True)
    assert cleartext == b'Welcome to the flippering.'


def test_federated_bob_retrieves(federated_bob,
                                 federated_alice,
                                 capsule_side_channel,
                                 enacted_federated_policy,
                                 ):

    # The side channel delivers all that Bob needs at this point:
    # - A single MessageKit, containing a Capsule
    # - A representation of the data source
    the_message_kit, the_data_source = capsule_side_channel

    alices_verifying_key = federated_alice.stamp.as_umbral_pubkey()

    delivered_cleartexts = federated_bob.retrieve(message_kit=the_message_kit,
                                                  data_source=the_data_source,
                                                  alice_verifying_key=alices_verifying_key,
                                                  label=enacted_federated_policy.label)

    # We show that indeed this is the passage originally encrypted by the Enrico.
    assert b"Welcome to the flippering." == delivered_cleartexts[0]
