from nkms.crypto import api
from tests.utilities import EVENT_LOOP, MockNetworkyStuff


def test_bob_can_follow_treasure_map(enacted_policy, ursulas, alice, bob):
    """
    Upon receiving a TreasureMap, Bob populates his list of Ursulas with the correct number.
    """

    # Simulate Bob finding a TreasureMap on the DHT.
    # A test to show that Bob can do this can be found in test_network_actors.
    hrac, treasure_map = enacted_policy_group.hrac(), enacted_policy_group.treasure_map
    bob.treasure_maps[hrac] = treasure_map

    # Bob knows of no Ursulas.
    assert len(bob._ursulas) == 0

    # ...until he follows the TreasureMap.
    bob.follow_treasure_map(hrac)

    # Now he knows of all the Ursulas.
    assert len(bob._ursulas) == len(treasure_map)


def test_bob_can_issue_a_work_order_to_a_specific_ursula(enacted_policy, alice, bob, ursulas):
    """
    Now that Bob has his list of Ursulas, he can issue a WorkOrder to one.  Upon receiving the WorkOrder, Ursula
    saves it and responds by re-encrypting and giving Bob a cFrag.

    This is a multipart test; it shows proper relations between the Characters Ursula and Bob and also proper
    interchange between a KFrag, PFrag, and CFrag object in the context of REST-driven proxy re-encryption.
    """

    # We pick up our story with Bob already having followed the treasure map above, ie:
    assert len(bob._ursulas) == len(ursulas)

    the_pfrag = enacted_policy_group.pfrag
    the_hrac = enacted_policy_group.hrac()

    # Bob has no saved work orders yet, ever.
    assert len(bob._saved_work_orders) == 0

    # We'll test against just a single Ursula - here, we make a WorkOrder for just one.
    work_orders = bob.generate_work_orders(the_hrac, the_pfrag, num_ursulas=1)
    assert len(work_orders) == 1

    # Bob has saved the WorkOrder, but since he hasn't used it for reencryption yet, it's empty.
    assert len(bob._saved_work_orders) == 1
    assert len(list(bob._saved_work_orders.items())[0][1]) == 0

    networky_stuff = MockNetworkyStuff(ursulas)

    ursula_dht_key, work_order = list(work_orders.items())[0]

    # **** RE-ENCRYPTION HAPPENS HERE! ****
    cfrags = bob.get_reencrypted_c_frags(networky_stuff, work_order)
    the_cfrag = cfrags[0]  # We only gave one pFrag, so we only got one cFrag.

    # Having received the cFrag, Bob also saved the WorkOrder as complete.
    assert len(list(bob._saved_work_orders.items())[0][1]) == 1

    # OK, so cool - Bob has his cFrag!  Let's make sure everything went properly.  First, we'll show that it is in fact
    # the correct cFrag (ie, that Ursula performed reencryption properly).
    ursula = networky_stuff.get_ursula_by_id(work_order.ursula_id)
    the_kfrag = ursula.keystore.get_kfrag(work_order.kfrag_hrac)
    the_correct_cfrag = api.ecies_reencrypt(the_kfrag, the_pfrag.encrypted_key)
    assert the_cfrag == the_correct_cfrag  # It's the correct cfrag!

    # Now we'll show that Ursula saved the correct WorkOrder.
    work_orders_from_bob = ursula.work_orders(bob=bob)
    assert len(work_orders_from_bob) == 1
    assert work_orders_from_bob[0] == work_order


def test_bob_remember_that_he_has_cfrags_for_a_particular_pfrag(enacted_policy, alice, bob, ursulas):

    # In our last episode, Bob obtained a cFrag from Ursula.
    bobs_saved_work_order_map = list(bob._saved_work_orders.items())

    # Bob only has a saved WorkOrder from one Ursula.
    assert len(bobs_saved_work_order_map) == 1

    id_of_ursula_from_whom_we_already_have_a_cfrag, saved_work_orders = bobs_saved_work_order_map[0]

    # ...and only one WorkOrder from that 1 Ursula.
    assert len(saved_work_orders) == 1

    # The rest of this test will show that if Bob generates another WorkOrder, it's for a *different* Ursula.

    generated_work_order_map = bob.generate_work_orders(enacted_policy_group.hrac(), enacted_policy_group.pfrag, num_ursulas=1)
    id_of_this_new_ursula, new_work_order = list(generated_work_order_map.items())[0]

    # This new Ursula isn't the same one to whom we've already issued a WorkOrder.
    assert id_of_ursula_from_whom_we_already_have_a_cfrag != id_of_this_new_ursula

    # ...and, although this WorkOrder has the same pfrags as the saved one...
    new_work_order.pfrags == saved_work_orders[0].pfrags

    # ...it's not the same WorkOrder.
    assert new_work_order not in saved_work_orders
