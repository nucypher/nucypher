from tests.utilities import EVENT_LOOP


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
