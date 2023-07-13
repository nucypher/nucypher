import os
from unittest.mock import patch

import pytest
from web3.datastructures import AttributeDict

from nucypher.blockchain.eth.trackers.dkg import ActiveRitualTracker


@pytest.fixture(scope="module")
def cohort(ursulas):
    """Creates a cohort of Ursulas"""
    nodes = list(sorted(ursulas[:4], key=lambda x: int(x.checksum_address, 16)))
    assert len(nodes) == 4  # sanity check
    return nodes


def test_action_required(cohort):
    ursula = cohort[0]
    agent = ursula.coordinator_agent
    active_ritual_tracker = ActiveRitualTracker(ritualist=ursula)

    for event in agent.contract.events:
        action_required = False
        if (
            event.event_name == "StartRitual"
            or event.event_name == "StartAggregationRound"
        ):
            action_required = True

        event_type = getattr(agent.contract.events, event.event_name)
        assert (
            active_ritual_tracker._action_required(event_type=event_type)
            == action_required
        )


def test_is_relevant_event_start_ritual(cohort, get_random_checksum_address):
    ritual_id = 12
    args_dict = {"ritualId": ritual_id}
    ursula = cohort[0]
    agent = ursula.coordinator_agent
    active_ritual_tracker = ActiveRitualTracker(ritualist=ursula)

    # StartRitual
    start_ritual_event = agent.contract.events.StartRitual()
    event_type = getattr(agent.contract.events, start_ritual_event.event_name)

    # create args data
    args_dict["initiator"] = get_random_checksum_address()
    args_dict["participants"] = [
        get_random_checksum_address(),
        get_random_checksum_address(),
        get_random_checksum_address(),
    ]  # not included by default

    # Ensure that test matches latest event information
    verify_event_args_match_latest_event_inputs(
        event=start_ritual_event, args_dict=args_dict
    )

    event_data = AttributeDict({"args": AttributeDict(args_dict)})

    #
    # not participating
    #
    verify_not_participating(active_ritual_tracker, ritual_id, event_data, event_type)

    #
    # clear prior information
    #
    active_ritual_tracker.participation_states.clear()

    #
    # actually participating now
    #
    args_dict["participants"] = [u.checksum_address for u in cohort]  # now included
    event_data = AttributeDict({"args": AttributeDict(args_dict)})

    verify_participating(
        active_ritual_tracker,
        ritual_id,
        event_data,
        event_type,
        expected_posted_transcript=False,
        expected_posted_aggregate=False,
    )


def test_is_relevant_event_transcript_posted(cohort, get_random_checksum_address):
    ritual_id = 12
    args_dict = {"ritualId": ritual_id}
    ursula = cohort[0]
    agent = ursula.coordinator_agent
    active_ritual_tracker = ActiveRitualTracker(ritualist=ursula)

    # TranscriptPosted
    transcript_posted_event = agent.contract.events.TranscriptPosted()
    event_type = getattr(agent.contract.events, transcript_posted_event.event_name)

    # create args data
    args_dict["node"] = get_random_checksum_address()  # node address not this one
    args_dict["transcriptDigest"] = os.urandom(32)

    # ensure that test matches latest event information
    verify_event_args_match_latest_event_inputs(
        event=transcript_posted_event, args_dict=args_dict
    )

    event_data = AttributeDict({"args": AttributeDict(args_dict)})

    #
    # not participating
    #
    verify_not_participating(active_ritual_tracker, ritual_id, event_data, event_type)

    #
    # clear prior information
    #
    active_ritual_tracker.participation_states.clear()

    #
    # actually participating now
    #
    args_dict["node"] = ursula.checksum_address  # set node address to this one
    event_data = AttributeDict({"args": AttributeDict(args_dict)})

    verify_participating(
        active_ritual_tracker,
        ritual_id,
        event_data,
        event_type,
        expected_posted_transcript=True,
        expected_posted_aggregate=False,
    )


def test_is_relevant_event_aggregation_posted(cohort, get_random_checksum_address):
    ritual_id = 12
    args_dict = {"ritualId": ritual_id}
    ursula = cohort[0]
    agent = ursula.coordinator_agent
    active_ritual_tracker = ActiveRitualTracker(ritualist=ursula)

    # AggregationPosted
    aggregation_posted_event = agent.contract.events.AggregationPosted()
    event_type = getattr(agent.contract.events, aggregation_posted_event.event_name)

    # create args data
    args_dict["node"] = get_random_checksum_address()  # node address not this one
    args_dict["aggregatedTranscriptDigest"] = os.urandom(32)

    # ensure that test matches latest event information
    verify_event_args_match_latest_event_inputs(
        event=aggregation_posted_event, args_dict=args_dict
    )
    event_data = AttributeDict({"args": AttributeDict(args_dict)})

    #
    # not participating
    #
    verify_not_participating(active_ritual_tracker, ritual_id, event_data, event_type)

    #
    # clear prior information
    #
    active_ritual_tracker.participation_states.clear()

    #
    # actually participating now
    #
    args_dict["node"] = ursula.checksum_address  # set node address to this one
    event_data = AttributeDict({"args": AttributeDict(args_dict)})

    verify_participating(
        active_ritual_tracker,
        ritual_id,
        event_data,
        event_type,
        expected_posted_transcript=True,
        expected_posted_aggregate=True,
    )


def test_is_relevant_event_start_aggregation_round_participation_not_already_tracked(
    cohort, get_random_checksum_address
):
    # StartAggregation is a special case because we can't determine participation directly
    #  from the event arguments
    ritual_id = 12
    args_dict = {"ritualId": ritual_id}
    ursula = cohort[0]
    agent = ursula.coordinator_agent
    active_ritual_tracker = ActiveRitualTracker(ritualist=ursula)

    start_aggregation_round_event = agent.contract.events.StartAggregationRound()
    event_type = getattr(
        agent.contract.events, start_aggregation_round_event.event_name
    )

    # ensure that test matches latest event information
    verify_event_args_match_latest_event_inputs(
        event=start_aggregation_round_event, args_dict=args_dict
    )
    event_data = AttributeDict({"args": AttributeDict(args_dict)})

    def not_participating(*args, **kwargs):
        return False

    #
    # not participating
    #
    with patch(
        "nucypher.blockchain.eth.trackers.dkg.ActiveRitualTracker._is_participating_in_ritual",
        not_participating,
    ):
        verify_not_participating(
            active_ritual_tracker, ritual_id, event_data, event_type
        )

    #
    # clear prior information
    #
    active_ritual_tracker.participation_states.clear()

    #
    # actually participating now
    #
    def participating(*args, **kwargs):
        return True

    with patch(
        "nucypher.blockchain.eth.trackers.dkg.ActiveRitualTracker._is_participating_in_ritual",
        participating,
    ):
        verify_participating(
            active_ritual_tracker,
            ritual_id,
            event_data,
            event_type,
            expected_posted_transcript=True,
            expected_posted_aggregate=False,
        )


def test_is_relevant_event_start_aggregation_round_participation_already_tracked(
    cohort, get_random_checksum_address
):
    # StartAggregation is a special case because we can't determine participation directly
    #  from the event arguments
    ritual_id = 12
    args_dict = {"ritualId": ritual_id}
    ursula = cohort[0]
    agent = ursula.coordinator_agent
    active_ritual_tracker = ActiveRitualTracker(ritualist=ursula)

    start_aggregation_round_event = agent.contract.events.StartAggregationRound()
    event_type = getattr(
        agent.contract.events, start_aggregation_round_event.event_name
    )

    # ensure that test matches latest event information
    verify_event_args_match_latest_event_inputs(
        event=start_aggregation_round_event, args_dict=args_dict
    )
    event_data = AttributeDict({"args": AttributeDict(args_dict)})

    #
    # not participating
    #

    # mimic already tracked prior state: not participating
    active_ritual_tracker.participation_states[
        ritual_id
    ] = active_ritual_tracker.ParticipationState(False, False, False)
    verify_not_participating(active_ritual_tracker, ritual_id, event_data, event_type)

    #
    # actually participating now
    #

    # mimic already tracked prior state: participating
    active_ritual_tracker.participation_states[
        ritual_id
    ] = active_ritual_tracker.ParticipationState(True, False, False)

    assert active_ritual_tracker._is_relevant_event(event_data, event_type)

    # new state stored
    assert len(active_ritual_tracker.participation_states) == 1

    # check values
    current_state = active_ritual_tracker.participation_states[ritual_id]
    assert current_state.participating
    assert not current_state.already_posted_aggregate

    # check again if relevant
    assert active_ritual_tracker._is_relevant_event(event_data, event_type)

    # no new information
    assert len(active_ritual_tracker.participation_states) == 1


def test_is_relevant_event_end_ritual_participation_not_already_tracked(
    cohort, get_random_checksum_address
):
    # StartAggregation is a special case because we can't determine participation directly
    #  from the event arguments
    ritual_id = 12
    args_dict = {"ritualId": ritual_id}
    ursula = cohort[0]
    agent = ursula.coordinator_agent
    active_ritual_tracker = ActiveRitualTracker(ritualist=ursula)

    end_ritual_event = agent.contract.events.EndRitual()
    event_type = getattr(agent.contract.events, end_ritual_event.event_name)

    # create args data
    args_dict["initiator"] = get_random_checksum_address()
    args_dict["successful"] = True

    # ensure that test matches latest event information
    verify_event_args_match_latest_event_inputs(
        event=end_ritual_event, args_dict=args_dict
    )
    event_data = AttributeDict({"args": AttributeDict(args_dict)})

    #
    # not participating
    #
    def not_participating(*args, **kwargs):
        return False

    with patch(
        "nucypher.blockchain.eth.trackers.dkg.ActiveRitualTracker._is_participating_in_ritual",
        not_participating,
    ):
        assert not active_ritual_tracker._is_relevant_event(event_data, event_type)

        # not state stored
        assert len(active_ritual_tracker.participation_states) == 0

    #
    # clear prior information
    #
    active_ritual_tracker.participation_states.clear()

    #
    # actually participating now
    #
    def participating(*args, **kwargs):
        return True

    with patch(
        "nucypher.blockchain.eth.trackers.dkg.ActiveRitualTracker._is_participating_in_ritual",
        participating,
    ):
        assert active_ritual_tracker._is_relevant_event(event_data, event_type)

        # no state stored
        assert len(active_ritual_tracker.participation_states) == 0


def test_is_relevant_event_end_ritual_participation_already_tracked(
    cohort, get_random_checksum_address
):
    # StartAggregation is a special case because we can't determine participation directly
    #  from the event arguments
    ritual_id = 12
    args_dict = {"ritualId": ritual_id}
    ursula = cohort[0]
    agent = ursula.coordinator_agent
    active_ritual_tracker = ActiveRitualTracker(ritualist=ursula)

    end_ritual_event = agent.contract.events.EndRitual()
    event_type = getattr(agent.contract.events, end_ritual_event.event_name)

    # create args data
    args_dict["initiator"] = get_random_checksum_address()
    args_dict["successful"] = False

    # ensure that test matches latest event information
    verify_event_args_match_latest_event_inputs(
        event=end_ritual_event, args_dict=args_dict
    )
    event_data = AttributeDict({"args": AttributeDict(args_dict)})

    #
    # not participating
    #

    # mimic already tracked prior state: not participating
    active_ritual_tracker.participation_states[
        ritual_id
    ] = active_ritual_tracker.ParticipationState(False, False, False)
    assert not active_ritual_tracker._is_relevant_event(event_data, event_type)

    # state is removed
    assert len(active_ritual_tracker.participation_states) == 0

    #
    # actually participating now
    #

    # mimic already tracked prior state: participating
    active_ritual_tracker.participation_states[
        ritual_id
    ] = active_ritual_tracker.ParticipationState(True, False, False)

    assert active_ritual_tracker._is_relevant_event(event_data, event_type)

    # state is removed
    assert len(active_ritual_tracker.participation_states) == 0


def verify_not_participating(
    active_ritual_tracker,
    ritual_id,
    event_data,
    event_type,
):
    assert not active_ritual_tracker._is_relevant_event(event_data, event_type)

    # new participation state stored
    assert len(active_ritual_tracker.participation_states) == 1

    # check stored state
    current_state = active_ritual_tracker.participation_states[ritual_id]
    assert not current_state.participating
    assert not current_state.already_posted_transcript
    assert not current_state.already_posted_aggregate

    # check again that not participating
    assert not active_ritual_tracker._is_relevant_event(event_data, event_type)

    # no new information
    assert len(active_ritual_tracker.participation_states) == 1

    # check stored state
    assert not current_state.participating
    assert not current_state.already_posted_transcript
    assert not current_state.already_posted_aggregate


def verify_participating(
    active_ritual_tracker,
    ritual_id,
    event_data,
    event_type,
    expected_posted_transcript,
    expected_posted_aggregate,
):
    assert active_ritual_tracker._is_relevant_event(event_data, event_type)

    # new state stored
    assert len(active_ritual_tracker.participation_states) == 1

    # check values
    current_state = active_ritual_tracker.participation_states[ritual_id]
    assert current_state.participating
    assert current_state.already_posted_transcript == expected_posted_transcript
    assert current_state.already_posted_aggregate == expected_posted_aggregate

    # check again if relevant
    assert active_ritual_tracker._is_relevant_event(event_data, event_type)

    # no new information
    assert len(active_ritual_tracker.participation_states) == 1

    # pretend to lose previous information eg. restart of node etc.
    active_ritual_tracker.participation_states.clear()
    assert len(active_ritual_tracker.participation_states) == 0

    assert active_ritual_tracker._is_relevant_event(event_data, event_type)

    # new state stored
    assert len(active_ritual_tracker.participation_states) == 1

    # check values
    current_state = active_ritual_tracker.participation_states[ritual_id]
    assert current_state.participating
    assert current_state.already_posted_transcript == expected_posted_transcript
    assert current_state.already_posted_aggregate == expected_posted_aggregate


def verify_event_args_match_latest_event_inputs(event, args_dict):
    event_inputs = event.abi["inputs"]
    assert len(event_inputs) == len(args_dict)
    for event_input in event_inputs:
        assert event_input["name"] in args_dict
