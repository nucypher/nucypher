import os
from typing import Dict, Type
from unittest.mock import Mock, patch

import pytest
from eth_typing import ChecksumAddress
from web3.contract.contract import ContractEvent
from web3.datastructures import AttributeDict

from nucypher.blockchain.eth.agents import CoordinatorAgent
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

    start_ritual_type = agent.contract.events.StartRitual
    start_aggregation_type = agent.contract.events.StartAggregationRound
    actionable_event_types = [start_ritual_type, start_aggregation_type]

    # non-actionable events
    # if we get to _action_required() check, we know the node is
    # participating, but no transcript/aggregate posted
    participation_state = ActiveRitualTracker.ParticipationState(
        participating=True,
        already_posted_transcript=False,
        already_posted_aggregate=False,
    )

    for event in agent.contract.events:
        event_type = getattr(agent.contract.events, event.event_name)
        if event_type not in actionable_event_types:
            assert not active_ritual_tracker._action_required(
                participation_state=participation_state, event_type=event_type
            )

    # actionable events - both actions required since transcript/aggregate not posted
    for event_type in actionable_event_types:
        assert active_ritual_tracker._action_required(
            participation_state=participation_state, event_type=event_type
        )

    # already posted transcript - action on required for aggregation
    participation_state.already_posted_transcript = True
    assert not active_ritual_tracker._action_required(
        participation_state=participation_state, event_type=start_ritual_type
    )
    assert active_ritual_tracker._action_required(
        participation_state=participation_state, event_type=start_aggregation_type
    )

    # already posted aggregate - no action required for both event types
    participation_state.already_posted_aggregate = True
    assert not active_ritual_tracker._action_required(
        participation_state=participation_state, event_type=start_ritual_type
    )
    assert not active_ritual_tracker._action_required(
        participation_state=participation_state, event_type=start_aggregation_type
    )


def test_get_participation_state_start_ritual(cohort, get_random_checksum_address):
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
    check_event_args_match_latest_event_inputs(
        event=start_ritual_event, args_dict=args_dict
    )

    event_data = AttributeDict({"args": AttributeDict(args_dict)})

    #
    # not participating
    #
    verify_non_participation_flow(active_ritual_tracker, event_data, event_type)

    #
    # clear prior information
    #
    active_ritual_tracker.participation_states.clear()

    #
    # actually participating now
    #
    args_dict["participants"] = [
        u.checksum_address for u in cohort
    ]  # ursula address included
    event_data = AttributeDict({"args": AttributeDict(args_dict)})

    verify_participation_flow(
        active_ritual_tracker,
        event_data,
        event_type,
        expected_posted_transcript=False,
        expected_posted_aggregate=False,
    )


def test_get_participation_state_transcript_posted(cohort, get_random_checksum_address):
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
    check_event_args_match_latest_event_inputs(
        event=transcript_posted_event, args_dict=args_dict
    )

    event_data = AttributeDict({"args": AttributeDict(args_dict)})

    #
    # not participating
    #
    verify_non_participation_flow(active_ritual_tracker, event_data, event_type)

    #
    # clear prior information
    #
    active_ritual_tracker.participation_states.clear()

    #
    # actually participating now
    #
    args_dict["node"] = ursula.checksum_address  # set node address to ursula's
    event_data = AttributeDict({"args": AttributeDict(args_dict)})

    verify_participation_flow(
        active_ritual_tracker,
        event_data,
        event_type,
        expected_posted_transcript=True,
        expected_posted_aggregate=False,
    )


def test_get_participation_state_aggregation_posted(
    cohort, get_random_checksum_address
):
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
    check_event_args_match_latest_event_inputs(
        event=aggregation_posted_event, args_dict=args_dict
    )
    event_data = AttributeDict({"args": AttributeDict(args_dict)})

    #
    # not participating
    #
    verify_non_participation_flow(active_ritual_tracker, event_data, event_type)

    #
    # clear prior information
    #
    active_ritual_tracker.participation_states.clear()

    #
    # actually participating now
    #
    args_dict["node"] = ursula.checksum_address  # set node address to this one
    event_data = AttributeDict({"args": AttributeDict(args_dict)})

    verify_participation_flow(
        active_ritual_tracker,
        event_data,
        event_type,
        expected_posted_transcript=True,
        expected_posted_aggregate=True,
    )


def test_get_participation_state_start_aggregation_round_participation_not_already_tracked(
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
    check_event_args_match_latest_event_inputs(
        event=start_aggregation_round_event, args_dict=args_dict
    )
    event_data = AttributeDict({"args": AttributeDict(args_dict)})

    def not_participating(*args, **kwargs):
        return None

    #
    # not participating
    #
    with patch(
        "nucypher.blockchain.eth.trackers.dkg.ActiveRitualTracker._get_participant_info",
        not_participating,
    ):
        verify_non_participation_flow(active_ritual_tracker, event_data, event_type)

    #
    # clear prior information
    #
    active_ritual_tracker.participation_states.clear()

    #
    # actually participating now
    #
    def participating(*args, **kwargs):
        return Mock(spec=CoordinatorAgent.Ritual.Participant)

    with patch(
        "nucypher.blockchain.eth.trackers.dkg.ActiveRitualTracker._get_participant_info",
        participating,
    ):
        verify_participation_flow(
            active_ritual_tracker,
            event_data,
            event_type,
            expected_posted_transcript=True,
            expected_posted_aggregate=False,
        )


def test_get_participation_state_start_aggregation_round_participation_already_tracked(
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
    check_event_args_match_latest_event_inputs(
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
    verify_non_participation_flow(active_ritual_tracker, event_data, event_type)

    #
    # actually participating now
    #

    # mimic already tracked prior state: participating
    active_ritual_tracker.participation_states[
        ritual_id
    ] = active_ritual_tracker.ParticipationState(True, False, False)

    participation_state = active_ritual_tracker._get_participation_state(
        event_data, event_type
    )
    check_participation_state(
        participation_state,
        expected_participating=True,
        expected_already_posted_transcript=True,
    )

    # new state stored
    assert len(active_ritual_tracker.participation_states) == 1
    assert active_ritual_tracker.participation_states[ritual_id] == participation_state

    # check again
    participation_state = active_ritual_tracker._get_participation_state(
        event_data, event_type
    )
    check_participation_state(
        participation_state,
        expected_participating=True,
        expected_already_posted_transcript=True,
    )

    # no new state information
    assert len(active_ritual_tracker.participation_states) == 1
    assert active_ritual_tracker.participation_states[ritual_id] == participation_state


def test_get_participation_state_end_ritual_participation_not_already_tracked(
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
    check_event_args_match_latest_event_inputs(
        event=end_ritual_event, args_dict=args_dict
    )
    event_data = AttributeDict({"args": AttributeDict(args_dict)})

    #
    # not participating
    #
    def not_participating(*args, **kwargs):
        return None

    with patch(
        "nucypher.blockchain.eth.trackers.dkg.ActiveRitualTracker._get_participant_info",
        not_participating,
    ):
        participation_state = active_ritual_tracker._get_participation_state(
            event_data, event_type
        )
        check_participation_state(participation_state)
        # no state stored
        assert len(active_ritual_tracker.participation_states) == 0

    #
    # clear prior information
    #
    active_ritual_tracker.participation_states.clear()

    #
    # actually participating now: successful
    #
    def participating(*args, **kwargs):
        participant = CoordinatorAgent.Ritual.Participant(
            provider=ChecksumAddress(ursula.checksum_address),
            aggregated=True,
            transcript=os.urandom(32),
            decryption_request_static_key=os.urandom(42),
        )

        return participant

    with patch(
        "nucypher.blockchain.eth.trackers.dkg.ActiveRitualTracker._get_participant_info",
        participating,
    ):
        participation_state = active_ritual_tracker._get_participation_state(
            event_data, event_type
        )
        check_participation_state(
            participation_state,
            expected_participating=True,
            expected_already_posted_transcript=True,
            expected_already_posted_aggregate=True,
        )
        # no state stored
        assert len(active_ritual_tracker.participation_states) == 0

    #
    # actually participating now: not successful - transcript not posted
    #
    def participating(*args, **kwargs):
        participant = CoordinatorAgent.Ritual.Participant(
            provider=ChecksumAddress(ursula.checksum_address),
            aggregated=False,
            transcript=b"",
            decryption_request_static_key=os.urandom(42),
        )

        return participant

    with patch(
        "nucypher.blockchain.eth.trackers.dkg.ActiveRitualTracker._get_participant_info",
        participating,
    ):
        args_dict["successful"] = False
        event_data = AttributeDict({"args": AttributeDict(args_dict)})
        participation_state = active_ritual_tracker._get_participation_state(
            event_data, event_type
        )
        check_participation_state(
            participation_state,
            expected_participating=True,
            expected_already_posted_transcript=False,
            expected_already_posted_aggregate=False,
        )
        # no state stored
        assert len(active_ritual_tracker.participation_states) == 0

    #
    # actually participating now: not successful - aggregate not posted
    #
    def participating(*args, **kwargs):
        participant = CoordinatorAgent.Ritual.Participant(
            provider=ChecksumAddress(ursula.checksum_address),
            aggregated=False,
            transcript=os.urandom(32),
            decryption_request_static_key=os.urandom(42),
        )

        return participant

    with patch(
        "nucypher.blockchain.eth.trackers.dkg.ActiveRitualTracker._get_participant_info",
        participating,
    ):
        args_dict["successful"] = False
        event_data = AttributeDict({"args": AttributeDict(args_dict)})
        participation_state = active_ritual_tracker._get_participation_state(
            event_data, event_type
        )
        check_participation_state(
            participation_state,
            expected_participating=True,
            expected_already_posted_transcript=True,
            expected_already_posted_aggregate=False,
        )
        # no state stored
        assert len(active_ritual_tracker.participation_states) == 0


def test_get_participation_state_end_ritual_participation_already_tracked(
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
    check_event_args_match_latest_event_inputs(
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
    participation_state = active_ritual_tracker._get_participation_state(
        event_data, event_type
    )
    check_participation_state(participation_state, expected_participating=False)

    # state is removed
    assert len(active_ritual_tracker.participation_states) == 0

    #
    # actually participating now
    #

    # mimic already tracked prior state: participating
    active_ritual_tracker.participation_states[
        ritual_id
    ] = active_ritual_tracker.ParticipationState(True, False, False)

    participation_state = active_ritual_tracker._get_participation_state(
        event_data, event_type
    )
    check_participation_state(
        participation_state,
        expected_participating=True,
        expected_already_posted_transcript=True,
        expected_already_posted_aggregate=True,
    )

    # state is removed
    assert len(active_ritual_tracker.participation_states) == 0


def test_get_participation_state_unexpected_event_without_ritual_id_arg(cohort):
    ursula = cohort[0]
    agent = ursula.coordinator_agent
    active_ritual_tracker = ActiveRitualTracker(ritualist=ursula)

    # TimeoutChanged
    timeout_changed_event = agent.contract.events.TimeoutChanged()
    event_type = getattr(agent.contract.events, timeout_changed_event.event_name)

    # create args data
    args_dict = {"oldTimeout": 1, "newTimeout": 2}

    # ensure that test matches latest event information
    check_event_args_match_latest_event_inputs(
        event=timeout_changed_event, args_dict=args_dict
    )

    event_data = AttributeDict({"args": AttributeDict(args_dict)})

    with pytest.raises(ValueError):
        active_ritual_tracker._get_participation_state(event_data, event_type)


def test_get_participation_state_unexpected_event_with_ritual_id_arg(cohort):
    ursula = cohort[0]
    agent = ursula.coordinator_agent
    active_ritual_tracker = ActiveRitualTracker(ritualist=ursula)

    # TimeoutChanged
    event_type = agent.contract.events.TimeoutChanged

    # create args data - faked to include ritual id arg
    args_dict = {"ritualId": 0, "oldTimeout": 1, "newTimeout": 2}

    event_data = AttributeDict({"args": AttributeDict(args_dict)})

    with pytest.raises(ValueError):
        active_ritual_tracker._get_participation_state(event_data, event_type)


def test_get_participation_state_multiple_participation_states_concurrent_rituals(
    cohort, get_random_checksum_address
):
    # let's pretend that rituals 5, 10, 15, 20 are being tracked at the same time
    ritual_id_1 = 5
    ritual_id_2 = 10
    ritual_id_3 = 15
    ritual_id_4 = 20
    # this will be the ritual that the ursula is NOT participating in but getting events for

    ritual_ids = [ritual_id_1, ritual_id_2, ritual_id_3, ritual_id_4]

    ursula = cohort[0]
    agent = ursula.coordinator_agent
    active_ritual_tracker = ActiveRitualTracker(ritualist=ursula)

    #
    # start ritual
    #
    event_type = agent.contract.events.StartRitual

    participants_when_participating = [
        get_random_checksum_address(),
        get_random_checksum_address(),
        get_random_checksum_address(),
        ursula.checksum_address,
    ]
    participants_when_not_participating = [
        get_random_checksum_address(),
        get_random_checksum_address(),
    ]

    # create list of events and use appropriately
    for i, r_id in enumerate(ritual_ids):
        event_data = AttributeDict(
            {
                "args": AttributeDict(
                    {
                        "ritualId": r_id,
                        "participants": participants_when_participating
                        if r_id != ritual_id_4
                        else participants_when_not_participating,
                    }
                )
            }
        )
        participation_state = active_ritual_tracker._get_participation_state(
            event_data, event_type
        )
        check_participation_state(
            participation_state, expected_participating=(r_id != ritual_id_4)
        )
        assert len(active_ritual_tracker.participation_states) == (i + 1)

    assert len(active_ritual_tracker.participation_states) == 4

    #
    # Transcript Posted
    #
    event_type = agent.contract.events.TranscriptPosted

    # receive transcript posted event for ritual_id 1
    event_data = AttributeDict(
        {
            "args": AttributeDict(
                {"ritualId": ritual_id_1, "node": ursula.checksum_address}
            )
        }
    )
    participation_state = active_ritual_tracker._get_participation_state(
        event_data, event_type
    )
    assert (
        participation_state == active_ritual_tracker.participation_states[ritual_id_1]
    )

    check_participation_state(
        active_ritual_tracker.participation_states[ritual_id_1],
        expected_participating=True,
        expected_already_posted_transcript=True,
    )
    check_participation_state(
        active_ritual_tracker.participation_states[ritual_id_2],
        expected_participating=True,
    )
    check_participation_state(
        active_ritual_tracker.participation_states[ritual_id_3],
        expected_participating=True,
    )
    check_participation_state(active_ritual_tracker.participation_states[ritual_id_4])

    #
    # Receive StartAggregation Round for ritual_id 2
    #
    event_type = agent.contract.events.StartAggregationRound

    event_data = AttributeDict(
        {
            "args": AttributeDict(
                {
                    "ritualId": ritual_id_2,
                }
            )
        }
    )
    participation_state = active_ritual_tracker._get_participation_state(
        event_data, event_type
    )
    assert (
        participation_state == active_ritual_tracker.participation_states[ritual_id_2]
    )

    check_participation_state(
        active_ritual_tracker.participation_states[ritual_id_1],
        expected_participating=True,
        expected_already_posted_transcript=True,
    )
    check_participation_state(
        active_ritual_tracker.participation_states[ritual_id_2],
        expected_participating=True,
        expected_already_posted_transcript=True,
    )
    check_participation_state(
        active_ritual_tracker.participation_states[ritual_id_3],
        expected_participating=True,
    )
    check_participation_state(active_ritual_tracker.participation_states[ritual_id_4])

    #
    # Receive AggregationPosted for ritual_id 3
    #
    event_type = agent.contract.events.AggregationPosted
    event_data = AttributeDict(
        {
            "args": AttributeDict(
                {"ritualId": ritual_id_3, "node": ursula.checksum_address}
            )
        }
    )
    participation_state = active_ritual_tracker._get_participation_state(
        event_data, event_type
    )
    assert (
        participation_state == active_ritual_tracker.participation_states[ritual_id_3]
    )

    check_participation_state(
        active_ritual_tracker.participation_states[ritual_id_1],
        expected_participating=True,
        expected_already_posted_transcript=True,
    )
    check_participation_state(
        active_ritual_tracker.participation_states[ritual_id_2],
        expected_participating=True,
        expected_already_posted_transcript=True,
    )
    check_participation_state(
        active_ritual_tracker.participation_states[ritual_id_3],
        expected_participating=True,
        expected_already_posted_transcript=True,
        expected_already_posted_aggregate=True,
    )
    check_participation_state(active_ritual_tracker.participation_states[ritual_id_4])

    #
    # Receive AggregationPosted for ritual id 4
    #
    event_type = agent.contract.events.AggregationPosted
    event_data = AttributeDict(
        {
            "args": AttributeDict(
                {"ritualId": ritual_id_4, "node": ursula.checksum_address}
            )
        }
    )
    participation_state = active_ritual_tracker._get_participation_state(
        event_data, event_type
    )
    assert (
        participation_state == active_ritual_tracker.participation_states[ritual_id_4]
    )

    check_participation_state(
        active_ritual_tracker.participation_states[ritual_id_1],
        expected_participating=True,
        expected_already_posted_transcript=True,
    )
    check_participation_state(
        active_ritual_tracker.participation_states[ritual_id_2],
        expected_participating=True,
        expected_already_posted_transcript=True,
    )
    check_participation_state(
        active_ritual_tracker.participation_states[ritual_id_3],
        expected_participating=True,
        expected_already_posted_transcript=True,
        expected_already_posted_aggregate=True,
    )
    check_participation_state(active_ritual_tracker.participation_states[ritual_id_4])

    #
    # EndRitual received for ritual id 2
    #
    event_type = agent.contract.events.EndRitual
    event_data = AttributeDict(
        {
            "args": AttributeDict(
                {
                    "ritualId": ritual_id_2,
                    "successful": True,
                }
            )
        }
    )
    participation_state = active_ritual_tracker._get_participation_state(
        event_data, event_type
    )
    # no longer tracking ritual 2 since all done
    assert participation_state not in active_ritual_tracker.participation_states
    check_participation_state(
        participation_state,
        expected_participating=True,
        expected_already_posted_transcript=True,
        expected_already_posted_aggregate=True,
    )

    check_participation_state(
        active_ritual_tracker.participation_states[ritual_id_1],
        expected_participating=True,
        expected_already_posted_transcript=True,
    )
    check_participation_state(
        active_ritual_tracker.participation_states[ritual_id_3],
        expected_participating=True,
        expected_already_posted_transcript=True,
        expected_already_posted_aggregate=True,
    )
    check_participation_state(active_ritual_tracker.participation_states[ritual_id_4])


def verify_non_participation_flow(
    active_ritual_tracker: ActiveRitualTracker,
    event_data: AttributeDict,
    event_type: Type[ContractEvent],
):
    ritual_id = event_data.args.ritualId

    participation_state = active_ritual_tracker._get_participation_state(
        event_data, event_type
    )
    check_participation_state(participation_state)

    # new participation state stored
    assert len(active_ritual_tracker.participation_states) == 1
    assert active_ritual_tracker.participation_states[ritual_id] == participation_state

    # check again that not participating
    participation_state = active_ritual_tracker._get_participation_state(
        event_data, event_type
    )
    check_participation_state(participation_state)

    # no new information
    assert len(active_ritual_tracker.participation_states) == 1
    assert active_ritual_tracker.participation_states[ritual_id] == participation_state


def verify_participation_flow(
    active_ritual_tracker: ActiveRitualTracker,
    event_data: AttributeDict,
    event_type: Type[ContractEvent],
    expected_posted_transcript: bool,
    expected_posted_aggregate: bool,
):
    ritual_id = event_data.args.ritualId

    participation_state = active_ritual_tracker._get_participation_state(
        event_data, event_type
    )
    check_participation_state(
        participation_state=participation_state,
        expected_participating=True,
        expected_already_posted_transcript=expected_posted_transcript,
        expected_already_posted_aggregate=expected_posted_aggregate,
    )

    # new state stored
    assert len(active_ritual_tracker.participation_states) == 1
    assert active_ritual_tracker.participation_states[ritual_id] == participation_state

    # check again if relevant
    participation_state = active_ritual_tracker._get_participation_state(
        event_data, event_type
    )
    check_participation_state(
        participation_state=participation_state,
        expected_participating=True,
        expected_already_posted_transcript=expected_posted_transcript,
        expected_already_posted_aggregate=expected_posted_aggregate,
    )

    # no new information
    assert len(active_ritual_tracker.participation_states) == 1
    assert active_ritual_tracker.participation_states[ritual_id] == participation_state

    # pretend to lose previous information eg. restart of node etc.
    active_ritual_tracker.participation_states.clear()
    assert len(active_ritual_tracker.participation_states) == 0

    participation_state = active_ritual_tracker._get_participation_state(
        event_data, event_type
    )
    check_participation_state(
        participation_state=participation_state,
        expected_participating=True,
        expected_already_posted_transcript=expected_posted_transcript,
        expected_already_posted_aggregate=expected_posted_aggregate,
    )

    # new state stored
    assert len(active_ritual_tracker.participation_states) == 1
    assert active_ritual_tracker.participation_states[ritual_id] == participation_state


def check_event_args_match_latest_event_inputs(event: ContractEvent, args_dict: Dict):
    event_inputs = event.abi["inputs"]
    assert len(event_inputs) == len(args_dict)
    for event_input in event_inputs:
        assert event_input["name"] in args_dict


def check_participation_state(
    participation_state: ActiveRitualTracker.ParticipationState,
    expected_participating: bool = False,
    expected_already_posted_transcript: bool = False,
    expected_already_posted_aggregate: bool = False,
):
    assert participation_state.participating == expected_participating
    assert (
        participation_state.already_posted_transcript
        == expected_already_posted_transcript
    )
    assert (
        participation_state.already_posted_aggregate
        == expected_already_posted_aggregate
    )
