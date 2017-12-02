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

    setter, encrypted_treasure_map, packed_encrypted_treasure_map, signature_for_bob, signature_for_ursula = alice.publish_treasure_map(
        enacted_policy_group)
    _set_event = EVENT_LOOP.run_until_complete(setter)

    bob.follow_treasure_map(enacted_policy_group.treasure_map)
    assert len(bob._ursulas) == len(ursulas)


def test_bob_can_issue_a_work_order_to_a_specific_ursula(enacted_policy_group, alice, bob, ursulas):

    # We pick up our story with Bob already having follwed the treasure map above, ie:
    assert len(bob._ursulas) == len(ursulas)

    p_frags = (b"llamas", b"dingos")
    work_orders = bob.generate_work_orders(enacted_policy_group, p_frags, num_ursulas=1)

    assert len(work_orders) == 1

    networky_stuff = MockNetworkyStuff(ursulas)

    for ursula_dht_key, work_order in work_orders.items():
        bob.get_reencrypted_c_frag(networky_stuff, work_order)  # Issue the work order only to the first Ursula.

    first_ursula = bob.get_ursula(0)
    work_orders_from_bob = first_ursula.work_orders(bob=bob)

    assert len(work_orders_from_bob) == 1
    assert work_orders_from_bob[0] == work_order
