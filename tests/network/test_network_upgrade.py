from tests.network.test_network_actors import test_treasure_map_from_alice_to_ursula, BOB, URSULAS


def test_bob_can_follow_treasure_map():
    """
    Upon receiving a
    """
    assert len(BOB._ursulas) == 0
    treasure_map, treasure_map_as_set_on_network, signature, policy_group = test_treasure_map_from_alice_to_ursula()
    BOB.follow_treasure_map(treasure_map)
    assert len(BOB._ursulas) == len(URSULAS)
