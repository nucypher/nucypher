from functools import partial

from constant_sorrow.constants import FLEET_STATES_MATCH


def test_all_nodes_have_same_fleet_state(ursulas):
    checksums = [u.peers.checksum for u in ursulas]
    assert len(set(checksums)) == 1  # There is only 1 unique value.


def test_peers_cycle(ursulas):
    ursula = list(ursulas)[0]

    # Before we start peering, Ursula has no peer.
    assert ursula._current_peer is None

    # Once we start, Ursula picks a peer node.
    ursula.learn_from_peer()
    first_peer = ursula._current_peer

    # When she learns the second time, it's from a different peer.
    ursula.learn_from_peer()
    second_peer = ursula._current_peer

    assert first_peer != second_peer


def test_nodes_with_equal_fleet_state_do_not_send_anew(ursulas):
    some_ursula = list(ursulas)[2]
    another_ursula = list(ursulas)[3]

    # These two have the same fleet state.
    assert some_ursula.peers.checksum == another_ursula.peers.checksum
    some_ursula._current_peer = another_ursula
    result = some_ursula.learn_from_peer()
    assert result is FLEET_STATES_MATCH


def test_old_state_is_preserved(ursulas, lonely_ursula_maker, accounts):
    lonely_learner = lonely_ursula_maker(accounts).pop()

    # This Ursula doesn't know about any nodes.
    assert len(lonely_learner.peers) == 0

    some_ursula_in_the_fleet = list(ursulas)[0]
    lonely_learner.remember_peer(some_ursula_in_the_fleet)
    checksum_after_peering_one = lonely_learner.peers.checksum
    assert some_ursula_in_the_fleet in lonely_learner.peers
    assert some_ursula_in_the_fleet.checksum_address in lonely_learner.peers
    assert len(lonely_learner.peers) == 1
    assert lonely_learner.peers.population == 2

    another_ursula_in_the_fleet = list(ursulas)[1]
    lonely_learner.remember_peer(another_ursula_in_the_fleet)
    checksum_after_peering_two = lonely_learner.peers.checksum
    assert some_ursula_in_the_fleet in lonely_learner.peers
    assert another_ursula_in_the_fleet in lonely_learner.peers
    assert some_ursula_in_the_fleet.checksum_address in lonely_learner.peers
    assert another_ursula_in_the_fleet.checksum_address in lonely_learner.peers
    assert len(lonely_learner.peers) == 2
    assert lonely_learner.peers.population == 3

    assert checksum_after_peering_one != checksum_after_peering_two

    first_state = lonely_learner.peers._archived_states[-2]
    assert first_state.population == 2
    assert first_state.checksum == checksum_after_peering_one

    second_state = lonely_learner.peers._archived_states[-1]
    assert second_state.population == 3
    assert second_state.checksum == checksum_after_peering_two


def test_state_is_recorded_after_peering(ursulas, lonely_ursula_maker, accounts):
    """
    Similar to above, but this time we show that the Learner records a new state only once after peering
    about a bunch of nodes.
    """
    _lonely_ursula_maker = partial(lonely_ursula_maker, quantity=1, accounts=accounts)
    lonely_learner = _lonely_ursula_maker().pop()
    states = lonely_learner.peers._archived_states

    # This Ursula doesn't know about any nodes.
    assert len(lonely_learner.peers) == 0

    some_ursula_in_the_fleet = list(ursulas)[0]
    lonely_learner.remember_peer(some_ursula_in_the_fleet)
    # Archived states at this point:
    # - inital one (empty, Ursula's metadata is not ready yet, no known nodes)
    # - the one created in Learner.__init__(). Metadata is still not ready, so it's the same
    #   as the previous one and is not recorded.
    # - the one created after Ursula learned about a remote node
    assert len(states) == 2

    # The first fleet state is just us and the one about whom we learned, which is part of the fleet.
    assert states[-1].population == 2

    # The rest of the fucking owl.
    lonely_learner.learn_from_peer()

    # There are two new states: one created after seednodes are loaded, to select a peer,
    # and the second after we get the rest of the nodes from the seednodes.
    assert len(states) == 4

    # When we ran learn_from_peer, we also loaded the rest of the fleet.
    assert states[-1].population == len(ursulas) + 1


def test_peer_records_new_fleet_state_upon_hearing_about_new_node(
    ursulas, lonely_ursula_maker, accounts
):
    _lonely_ursula_maker = partial(lonely_ursula_maker, quantity=1, accounts=accounts)
    lonely_learner = _lonely_ursula_maker().pop()

    some_ursula_in_the_fleet = list(ursulas)[0]

    lonely_learner.remember_peer(some_ursula_in_the_fleet)

    states = some_ursula_in_the_fleet.peers._archived_states

    states_before = len(states)
    lonely_learner.learn_from_peer()
    states_after = len(states)

    # TODO #2568: some kind of a timeout is required here to wait for the peering to end
    return

    # `some_ursula_in_the_fleet` learned about `lonely_learner`
    assert states_before + 1 == states_after

    # The current fleet state of the Teacher...
    peer_fleet_state_checksum = some_ursula_in_the_fleet.peers.checksum

    # ...is the same as the learner, because both have learned about everybody at this point.
    assert peer_fleet_state_checksum == states[-1].checksum
