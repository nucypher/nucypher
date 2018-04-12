import pytest

from tests.utilities import MockNetworkyStuff
from umbral import pre
from umbral.fragments import KFrag


def test_bob_can_follow_treasure_map(enacted_policy, ursulas, alice, bob):
    """
    Upon receiving a TreasureMap, Bob populates his list of Ursulas with the correct number.
    """

    # Simulate Bob finding a TreasureMap on the DHT.
    # A test to show that Bob can do this can be found in test_network_actors.
    hrac, treasure_map = enacted_policy.hrac(), enacted_policy.treasure_map
    bob.treasure_maps[hrac] = treasure_map

    # Bob knows of no Ursulas.
    assert len(bob.known_nodes) == 0

    # ...until he follows the TreasureMap.
    bob.follow_treasure_map(hrac)

    # Now he knows of all the Ursulas.
    assert len(bob.known_nodes) == len(treasure_map)


def test_bob_can_issue_a_work_order_to_a_specific_ursula(enacted_policy, alice, bob, ursulas,
                                                         capsule_side_channel):
    """
    Now that Bob has his list of Ursulas, he can issue a WorkOrder to one.  Upon receiving the WorkOrder, Ursula
    saves it and responds by re-encrypting and giving Bob a cFrag.

    This is a multipart test; it shows proper relations between the Characters Ursula and Bob and also proper
    interchange between a KFrag, Capsule, and CFrag object in the context of REST-driven proxy re-encryption.
    """

    # We pick up our story with Bob already having followed the treasure map above, ie:
    hrac, treasure_map = enacted_policy.hrac(), enacted_policy.treasure_map
    bob.treasure_maps[hrac] = treasure_map
    bob.follow_treasure_map(hrac)
    assert len(bob.known_nodes) == len(ursulas)

    the_hrac = enacted_policy.hrac()

    # Bob has no saved work orders yet, ever.
    assert len(bob._saved_work_orders) == 0

    # We'll test against just a single Ursula - here, we make a WorkOrder for just one.
    # We can pass any number of capsules as args; here we pass just one.
    work_orders = bob.generate_work_orders(the_hrac, capsule_side_channel[0].capsule, num_ursulas=1)

    # Again: one Ursula, one work_order.
    assert len(work_orders) == 1

    # Bob saved the WorkOrder.
    assert len(bob._saved_work_orders) == 1
    # And the Ursula.
    assert len(bob._saved_work_orders.ursulas) == 1

    networky_stuff = MockNetworkyStuff(ursulas)
    ursula_dht_key, work_order = list(work_orders.items())[0]

    # In the real world, we'll have a full Ursula node here.  But in this case, we need to fake it.
    work_order.ursula = ursulas[0]

    # **** RE-ENCRYPTION HAPPENS HERE! ****
    cfrags = bob.get_reencrypted_c_frags(networky_stuff, work_order)

    # We only gave one Capsule, so we only got one cFrag.
    assert len(cfrags) == 1
    the_cfrag = cfrags[0]

    # Attach the CFrag to the Capsule.
    capsule_side_channel[0].capsule.attach_cfrag(the_cfrag)

    # Having received the cFrag, Bob also saved the WorkOrder as complete.
    assert len(bob._saved_work_orders) == 1

    # OK, so cool - Bob has his cFrag!  Let's make sure everything went properly.  First, we'll show that it is in fact
    # the correct cFrag (ie, that Ursula performed reencryption properly).
    ursula = work_order.ursula
    kfrag_bytes = ursula.datastore.get_policy_arrangement(
        work_order.kfrag_hrac.hex().encode()).k_frag
    the_kfrag = KFrag.from_bytes(kfrag_bytes)
    the_correct_cfrag = pre.reencrypt(the_kfrag, capsule_side_channel[0].capsule)
    assert bytes(the_cfrag) == bytes(the_correct_cfrag)  # It's the correct cfrag!

    # Now we'll show that Ursula saved the correct WorkOrder.
    work_orders_from_bob = ursula.work_orders(bob=bob)
    assert len(work_orders_from_bob) == 1
    assert work_orders_from_bob[0] == work_order


def test_bob_remembers_that_he_has_cfrags_for_a_particular_capsule(enacted_policy, alice, bob,
                                                                   ursulas, capsule_side_channel):
    # In our last episode, Bob made a WorkOrder for the capsule...
    assert len(bob._saved_work_orders.by_capsule(capsule_side_channel[0].capsule)) == 1
    # ...and he used it to obtain a CFrag from Ursula.
    assert len(capsule_side_channel[0].capsule._attached_cfrags) == 1

    # He can also get a dict of {Ursula:WorkOrder} by looking them up from the capsule.
    workorders_by_capsule = bob._saved_work_orders.by_capsule(capsule_side_channel[0].capsule)

    # Bob has just one WorkOrder from that one Ursula.
    assert len(workorders_by_capsule) == 1
    saved_work_order = list(workorders_by_capsule.values())[0]

    # The rest of this test will show that if Bob generates another WorkOrder, it's for a *different* Ursula.
    generated_work_orders = bob.generate_work_orders(enacted_policy.hrac(),
                                                     capsule_side_channel[0].capsule,
                                                     num_ursulas=1)
    id_of_this_new_ursula, new_work_order = list(generated_work_orders.items())[0]

    # This new Ursula isn't the same one to whom we've already issued a WorkOrder.
    id_of_ursula_from_whom_we_already_have_a_cfrag = list(workorders_by_capsule.keys())[0]
    assert id_of_ursula_from_whom_we_already_have_a_cfrag != id_of_this_new_ursula

    # ...and, although this WorkOrder has the same capsules as the saved one...
    assert new_work_order.capsules == saved_work_order.capsules

    # ...it's not the same WorkOrder.
    assert new_work_order != saved_work_order

    # We can get a new CFrag, just like last time.
    networky_stuff = MockNetworkyStuff(ursulas)
    # In the real world, we'll have a full Ursula node here.  But in this case, we need to fake it.
    new_work_order.ursula = ursulas[1]

    cfrags = bob.get_reencrypted_c_frags(networky_stuff, new_work_order)

    # Again: one Capsule, one cFrag.
    assert len(cfrags) == 1
    new_cfrag = cfrags[0]

    # Attach the CFrag to the Capsule.
    capsule_side_channel[0].capsule.attach_cfrag(new_cfrag)


def test_bob_gathers_and_combines(enacted_policy, bob, ursulas, capsule_side_channel):
    # The side channel is represented as a single MessageKit, which is all that Bob really needs.
    the_message_kit, the_data_source = capsule_side_channel

    # Bob has saved two WorkOrders so far.
    assert len(bob._saved_work_orders) == 2

    # ...but the policy requires us to collect more cfrags.
    assert len(bob._saved_work_orders) < enacted_policy.m

    # Bob can't decrypt yet with just two CFrags.  He needs to gather at least m.
    with pytest.raises(pre.GenericUmbralError):
        bob.decrypt(the_message_kit)

    number_left_to_collect = enacted_policy.m - len(bob._saved_work_orders)

    new_work_orders = bob.generate_work_orders(enacted_policy.hrac(),
                                               the_message_kit.capsule,
                                               num_ursulas=number_left_to_collect)
    _id_of_yet_another_ursula, new_work_order = list(new_work_orders.items())[0]

    networky_stuff = MockNetworkyStuff(ursulas)
    # In the real world, we'll have a full Ursula node here.  But in this case, we need to fake it.
    new_work_order.ursula = ursulas[2]
    cfrags = bob.get_reencrypted_c_frags(networky_stuff, new_work_order)
    the_message_kit.capsule.attach_cfrag(cfrags[0])

    # Now.
    # At long last.
    is_valid, cleartext = bob.verify_from(the_data_source, the_message_kit, decrypt=True)
    assert cleartext == b'Welcome to the flippering.'
    assert is_valid
