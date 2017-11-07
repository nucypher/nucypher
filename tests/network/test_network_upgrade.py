from tests.network.test_network_actors import test_treasure_map_from_alice_to_ursula, BOB


def test_bob_can_follow_treasure_map():
    treasure_map, treasure_map_as_set_on_network, signature, policy_group = test_treasure_map_from_alice_to_ursula()
    BOB.follow_treasure_map(treasure_map)
    assert False


#
# def test_bob_and_ursula_upgrade_to_tls():
#     pass
#
#

# def test_bob_and_ursula_upgrade_to_tls():
#     treasure_map, treasure_map_as_set_on_network, signature, policy_group = test_treasure_map_from_alice_to_ursula()
#     networky_stuff = MockNetworkyStuff()
#
#     # Of course, in the real world, Bob has sufficient information to reconstitute a PolicyGroup, gleaned, we presume, through a side-channel with Alice.
#     treasure_map_from_wire = BOB.get_treasure_map(policy_group, signature)
#
#
#     # for ursula in treasure_map_from_wire:
#     #     pass
#     #
#     # BOB