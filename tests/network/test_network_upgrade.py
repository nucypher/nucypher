from tests.utilities import BOB, URSULAS


def test_bob_can_follow_treasure_map():
    """
    Upon receiving a TreasureMap, Bob populates his list of Ursulas with the correct number.
    """
    assert len(BOB._ursulas) == 0
    _treasure_map_as_set_on_network, _signature, policy_group = test_alice_sets_treasure_map_on_network()
    BOB.follow_treasure_map(policy_group.treasure_map)
    assert len(BOB._ursulas) == len(URSULAS)
