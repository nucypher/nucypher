from nkms.crypto import api
from tests.utilities import EVENT_LOOP, MockNetworkyStuff


def test_alice_enacts_policies_in_policy_group_via_rest(enacted_policy_group):
    """
    Now that Alice has made a PolicyGroup, she can enact its policies, using Ursula's Public Key to encrypt each offer
    and transmitting them via REST.
    """
    ursula = enacted_policy_group.policies[0].ursula
    kfrag_that_was_set = ursula.keystore.get_kfrag(enacted_policy_group.hrac())
    assert bool(kfrag_that_was_set)  # TODO: This can be a more poignant assertion.


def test_bob_can_follow_treasure_map(enacted_policy_group, ursulas, alice, bob):
    """
    Upon receiving a TreasureMap, Bob populates his list of Ursulas with the correct number.
    """
    assert len(bob._ursulas) == 0

    enacted_policy_group.publish_treasure_map()

    bob.follow_treasure_map(enacted_policy_group.treasure_map)
    assert len(bob._ursulas) == len(ursulas)


def test_bob_can_issue_a_work_order_to_a_specific_ursula(enacted_policy_group, alice, bob, ursulas):
    """
    Now that Bob has his list of Ursulas, he can issue a WorkOrder to one.  Upon receiving the WorkOrder, Ursula
    saves it and responds by re-encrypting and giving Bob a cFrag.

    This is a multipart test; it shows proper relations between the Characters Ursula and Bob and also proper
    interchange between a KFrag, PFrag, and CFrag object in the context of REST-driven proxy re-encryption.
    """

    # We pick up our story with Bob already having followed the treasure map above, ie:
    enacted_policy_group.publish_treasure_map()
    bob.follow_treasure_map(enacted_policy_group.treasure_map)
    assert len(bob._ursulas) == len(ursulas)

    # Now we assume Bob has received the pFrag through a side-channel:
    the_pfrag = enacted_policy_group.pfrag

    # We'll test against just a single Ursula - here, we made a WorkOrder for just one.
    work_orders = bob.generate_work_orders(enacted_policy_group, the_pfrag, num_ursulas=1)
    assert len(work_orders) == 1

    networky_stuff = MockNetworkyStuff(ursulas)

    ursula_dht_key, work_order = list(work_orders.items())[0]
    cfrags = bob.get_reencrypted_c_frag(networky_stuff, work_order)

    the_cfrag = cfrags[0]  # We only gave one pFrag, so we only got one cFrag.

    # Wow, Bob has his cFrag!  Let's make sure everything went properly.  First, we'll show that it is in fact
    # the correct cFrag (ie, that Ursula performed reencryption properly).
    ursula = networky_stuff.get_ursula_by_id(work_order.ursula_id)
    the_kfrag = ursula.keystore.get_kfrag(work_order.kfrag_hrac)
    the_correct_cfrag = api.ecies_reencrypt(the_kfrag, the_pfrag.encrypted_key)
    assert the_cfrag == the_correct_cfrag  # It's the correct cfrag!

    # Now we'll show that Ursula saved the correct WorkOrder.
    work_orders_from_bob = ursula.work_orders(bob=bob)
    assert len(work_orders_from_bob) == 1
    assert work_orders_from_bob[0] == work_order
