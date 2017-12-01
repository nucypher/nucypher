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
