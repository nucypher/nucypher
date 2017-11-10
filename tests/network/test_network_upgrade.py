from tests.network.test_network_actors import test_alice_sets_treasure_map_on_network, BOB, URSULAS


def test_bob_can_follow_treasure_map():
    """
    Upon receiving a
    """
    assert len(BOB._ursulas) == 0
    treasure_map, treasure_map_as_set_on_network, signature, policy_group = test_alice_sets_treasure_map_on_network()
    BOB.follow_treasure_map(treasure_map)
    assert len(BOB._ursulas) == len(URSULAS)
