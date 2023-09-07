import datetime
import os
from typing import Dict
from unittest.mock import ANY, Mock, patch

import maya
import pytest
import pytest_twisted
from eth_typing import ChecksumAddress
from web3.contract.contract import ContractEvent
from web3.datastructures import AttributeDict

from nucypher.blockchain.eth.actors import Ritualist
from nucypher.blockchain.eth.agents import CoordinatorAgent
from nucypher.blockchain.eth.trackers.dkg import ActiveRitualTracker


@pytest.fixture(scope="module")
def cohort(ursulas):
    """Creates a cohort of Ursulas"""
    nodes = list(sorted(ursulas[:4], key=lambda x: int(x.checksum_address, 16)))
    assert len(nodes) == 4  # sanity check
    return nodes


def test_action_required_not_participating(cohort):
    ursula = cohort[0]
    agent = ursula.coordinator_agent
    active_ritual_tracker = ActiveRitualTracker(ritualist=ursula)

    participation_state = ActiveRitualTracker.ParticipationState(
        participating=False,  # not participating
        already_posted_transcript=False,
        already_posted_aggregate=False,
    )

    def _my_get_participation_state(*args, **kwargs):
        return participation_state

    with patch(
        "nucypher.blockchain.eth.trackers.dkg.ActiveRitualTracker._get_participation_state",
        _my_get_participation_state,
    ):
        for event in agent.contract.events:
            ritual_event = AttributeDict(
                {
                    "event": event.event_name,
                    "args": AttributeDict(
                        {
                            "ritualId": 23,
                        }
                    ),
                }
            )
            # all events are irrelevant because not participating
            assert not active_ritual_tracker._action_required(ritual_event)


def test_action_required_only_for_events_with_corresponding_actions(cohort):
    ursula = cohort[0]
    agent = ursula.coordinator_agent
    active_ritual_tracker = ActiveRitualTracker(ritualist=ursula)

    participation_state = ActiveRitualTracker.ParticipationState(
        participating=True,  # participating
        already_posted_transcript=False,
        already_posted_aggregate=False,
    )

    def _my_get_participation_state(*args, **kwargs):
        return participation_state

    with patch(
        "nucypher.blockchain.eth.trackers.dkg.ActiveRitualTracker._get_participation_state",
        _my_get_participation_state,
    ):
        for event in agent.contract.events:
            event_type = getattr(agent.contract.events, event.event_name)
            ritual_event = AttributeDict(
                {
                    "event": event.event_name,
                    "args": AttributeDict(
                        {
                            "ritualId": 23,
                        }
                    ),
                }
            )

            if event_type not in active_ritual_tracker.actions:
                assert not active_ritual_tracker._action_required(ritual_event)
            else:
                # actionable events - both actions required since transcript/aggregate not posted
                assert active_ritual_tracker._action_required(ritual_event)


def test_action_required_depending_on_participation_state(cohort):
    ursula = cohort[0]
    agent = ursula.coordinator_agent
    active_ritual_tracker = ActiveRitualTracker(ritualist=ursula)

    participation_state = ActiveRitualTracker.ParticipationState(
        participating=True,
        already_posted_transcript=False,
        already_posted_aggregate=False,
    )

    def _my_get_participation_state(*args, **kwargs):
        return participation_state

    with patch(
        "nucypher.blockchain.eth.trackers.dkg.ActiveRitualTracker._get_participation_state",
        _my_get_participation_state,
    ):
        # actionable events
        start_ritual_event = AttributeDict(
            {
                "event": agent.contract.events.StartRitual.event_name,
                "args": AttributeDict(
                    {
                        "ritualId": 23,
                    }
                ),
            }
        )
        assert agent.contract.events.StartRitual in active_ritual_tracker.actions
        start_aggregation_event = AttributeDict(
            {
                "event": agent.contract.events.StartAggregationRound.event_name,
                "args": AttributeDict(
                    {
                        "ritualId": 23,
                    }
                ),
            }
        )
        assert (
            agent.contract.events.StartAggregationRound in active_ritual_tracker.actions
        )
        assert (
            len(active_ritual_tracker.actions) == 2
        ), "untested event with corresponding action"

        #
        # already posted transcript - action only required for aggregation
        #
        participation_state.already_posted_transcript = True
        assert not active_ritual_tracker._action_required(start_ritual_event)
        assert active_ritual_tracker._action_required(start_aggregation_event)

        #
        # already posted aggregate - no action required for both event types
        #
        participation_state.already_posted_aggregate = True
        assert not active_ritual_tracker._action_required(start_ritual_event)
        assert not active_ritual_tracker._action_required(start_aggregation_event)


def test_get_participation_state_start_ritual(cohort, get_random_checksum_address):
    ritual_id = 12
    args_dict = {"ritualId": ritual_id}
    ursula = cohort[0]
    agent = ursula.coordinator_agent
    active_ritual_tracker = ActiveRitualTracker(ritualist=ursula)

    # StartRitual
    start_ritual_event = agent.contract.events.StartRitual()

    # create args data
    args_dict["authority"] = get_random_checksum_address()
    args_dict["participants"] = [
        get_random_checksum_address(),
        get_random_checksum_address(),
        get_random_checksum_address(),
    ]  # not included by default

    # Ensure that test matches latest event information
    check_event_args_match_latest_event_inputs(
        event=start_ritual_event, args_dict=args_dict
    )

    event_data = AttributeDict(
        {"event": start_ritual_event.event_name, "args": AttributeDict(args_dict)}
    )

    #
    # not participating
    #
    verify_non_participation_flow(active_ritual_tracker, event_data)

    #
    # clear prior information
    #
    active_ritual_tracker._participation_states.clear()

    #
    # actually participating now
    #
    args_dict["participants"] = [
        u.checksum_address for u in cohort
    ]  # ursula address included
    event_data = AttributeDict(
        {"event": start_ritual_event.event_name, "args": AttributeDict(args_dict)}
    )

    verify_participation_flow(
        active_ritual_tracker,
        event_data,
        expected_posted_transcript=False,
        expected_posted_aggregate=False,
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

    # ensure that test matches latest event information
    check_event_args_match_latest_event_inputs(
        event=start_aggregation_round_event, args_dict=args_dict
    )
    event_data = AttributeDict(
        {
            "event": start_aggregation_round_event.event_name,
            "args": AttributeDict(args_dict),
        }
    )

    def not_participating(*args, **kwargs):
        return None

    #
    # not participating
    #
    with patch(
        "nucypher.blockchain.eth.trackers.dkg.ActiveRitualTracker._get_ritual_participant_info",
        not_participating,
    ):
        verify_non_participation_flow(active_ritual_tracker, event_data)

    #
    # clear prior information
    #
    active_ritual_tracker._participation_states.clear()

    #
    # actually participating now
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
        "nucypher.blockchain.eth.trackers.dkg.ActiveRitualTracker._get_ritual_participant_info",
        participating,
    ):
        verify_participation_flow(
            active_ritual_tracker,
            event_data,
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

    # ensure that test matches latest event information
    check_event_args_match_latest_event_inputs(
        event=start_aggregation_round_event, args_dict=args_dict
    )
    event_data = AttributeDict(
        {
            "event": start_aggregation_round_event.event_name,
            "args": AttributeDict(args_dict),
        }
    )

    #
    # not participating
    #

    # mimic already tracked prior state: not participating
    active_ritual_tracker._participation_states[
        ritual_id
    ] = active_ritual_tracker.ParticipationState(False, False, False)

    verify_non_participation_flow(active_ritual_tracker, event_data)

    #
    # actually participating now
    #

    # mimic already tracked prior state: participating
    active_ritual_tracker._participation_states[
        ritual_id
    ] = active_ritual_tracker.ParticipationState(True, False, False)

    participation_state = active_ritual_tracker._get_participation_state(event_data)
    check_participation_state(
        participation_state,
        expected_participating=True,
        expected_already_posted_transcript=True,
    )

    # new state stored
    assert len(active_ritual_tracker._participation_states) == 1
    assert active_ritual_tracker._participation_states[ritual_id] == participation_state

    # check again
    participation_state = active_ritual_tracker._get_participation_state(event_data)
    check_participation_state(
        participation_state,
        expected_participating=True,
        expected_already_posted_transcript=True,
    )

    # no new state information
    assert len(active_ritual_tracker._participation_states) == 1
    assert active_ritual_tracker._participation_states[ritual_id] == participation_state


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

    # create args data
    args_dict["successful"] = True

    # ensure that test matches latest event information
    check_event_args_match_latest_event_inputs(
        event=end_ritual_event, args_dict=args_dict
    )
    event_data = AttributeDict(
        {"event": end_ritual_event.event_name, "args": AttributeDict(args_dict)}
    )

    #
    # not participating
    #
    def not_participating(*args, **kwargs):
        return None

    with patch(
        "nucypher.blockchain.eth.trackers.dkg.ActiveRitualTracker._get_ritual_participant_info",
        not_participating,
    ):
        verify_non_participation_flow(active_ritual_tracker, event_data)

    #
    # clear prior information
    #
    active_ritual_tracker._participation_states.clear()

    #
    # actually participating now: ritual successful
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
        "nucypher.blockchain.eth.trackers.dkg.ActiveRitualTracker._get_ritual_participant_info",
        participating,
    ):
        verify_participation_flow(
            active_ritual_tracker,
            event_data,
            expected_posted_transcript=True,
            expected_posted_aggregate=True,
        )

    #
    # clear prior information
    #
    active_ritual_tracker._participation_states.clear()

    #
    # actually participating now: ritual not successful - transcript and aggregate not posted
    #
    def participating(*args, **kwargs):
        participant = CoordinatorAgent.Ritual.Participant(
            provider=ChecksumAddress(ursula.checksum_address),
            aggregated=False,
            transcript=bytes(),
            decryption_request_static_key=os.urandom(42),
        )

        return participant

    with patch(
        "nucypher.blockchain.eth.trackers.dkg.ActiveRitualTracker._get_ritual_participant_info",
        participating,
    ):
        args_dict["successful"] = False
        event_data = AttributeDict(
            {"event": end_ritual_event.event_name, "args": AttributeDict(args_dict)}
        )
        verify_participation_flow(
            active_ritual_tracker,
            event_data,
            expected_posted_transcript=False,
            expected_posted_aggregate=False,
        )

    #
    # clear prior information
    #
    active_ritual_tracker._participation_states.clear()

    #
    # actually participating now: not successful - transcript posted, aggregate not posted
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
        "nucypher.blockchain.eth.trackers.dkg.ActiveRitualTracker._get_ritual_participant_info",
        participating,
    ):
        args_dict["successful"] = False
        event_data = AttributeDict(
            {"event": end_ritual_event.event_name, "args": AttributeDict(args_dict)}
        )
        verify_participation_flow(
            active_ritual_tracker,
            event_data,
            expected_posted_transcript=True,
            expected_posted_aggregate=False,
        )


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

    # create args data
    args_dict["successful"] = True

    # ensure that test matches latest event information
    check_event_args_match_latest_event_inputs(
        event=end_ritual_event, args_dict=args_dict
    )
    event_data = AttributeDict(
        {"event": end_ritual_event.event_name, "args": AttributeDict(args_dict)}
    )

    #
    # not participating
    #

    # mimic already tracked prior state: not participating
    active_ritual_tracker._participation_states[
        ritual_id
    ] = active_ritual_tracker.ParticipationState(False, False, False)

    verify_non_participation_flow(active_ritual_tracker, event_data)
    # no additional entry
    assert len(active_ritual_tracker._participation_states) == 1

    #
    # actually participating now
    #

    # mimic already tracked prior state: participating
    active_ritual_tracker._participation_states[
        ritual_id
    ] = active_ritual_tracker.ParticipationState(True, False, False)

    participation_state = active_ritual_tracker._get_participation_state(event_data)
    check_participation_state(
        participation_state,
        expected_participating=True,
        expected_already_posted_transcript=True,
        expected_already_posted_aggregate=True,
    )

    # no additional entry
    assert active_ritual_tracker._participation_states[ritual_id] == participation_state
    assert len(active_ritual_tracker._participation_states) == 1


def test_get_participation_state_unexpected_event_without_ritual_id_arg(cohort):
    ursula = cohort[0]
    agent = ursula.coordinator_agent
    active_ritual_tracker = ActiveRitualTracker(ritualist=ursula)

    # TimeoutChanged
    timeout_changed_event = agent.contract.events.TimeoutChanged()

    # create args data
    args_dict = {"oldTimeout": 1, "newTimeout": 2}

    # ensure that test matches latest event information
    check_event_args_match_latest_event_inputs(
        event=timeout_changed_event, args_dict=args_dict
    )

    event_data = AttributeDict(
        {"event": timeout_changed_event.event_name, "args": AttributeDict(args_dict)}
    )

    with pytest.raises(RuntimeError):
        active_ritual_tracker._get_participation_state(event_data)


def test_get_participation_state_unexpected_event_with_ritual_id_arg(cohort):
    ursula = cohort[0]
    agent = ursula.coordinator_agent
    active_ritual_tracker = ActiveRitualTracker(ritualist=ursula)

    # create args data - faked to include ritual id arg
    args_dict = {"ritualId": 0, "oldTimeout": 1, "newTimeout": 2}

    # TimeoutChanged event
    event_data = AttributeDict(
        {
            "event": agent.contract.events.TimeoutChanged.event_name,
            "args": AttributeDict(args_dict),
        }
    )

    with pytest.raises(RuntimeError):
        active_ritual_tracker._get_participation_state(event_data)


def test_get_participation_state_purge_expired_cache_entries(
    cohort, get_random_checksum_address
):
    ritual_id_1 = 1
    ritual_id_2 = 2

    ursula = cohort[0]
    agent = ursula.coordinator_agent

    # This test hinges on the relationship between ritual timeout and the purge interval
    # This relationship should hold: ritual timeout (ttl) + buffer == to the purge
    # interval for ease of testing; so fake the ritual timeout
    faked_ritual_timeout = ActiveRitualTracker._PARTICIPATION_STATES_PURGE_INTERVAL - (
        ActiveRitualTracker._RITUAL_TIMEOUT_ADDITIONAL_TTL_BUFFER
    )

    with patch.object(agent, "get_timeout", return_value=faked_ritual_timeout):
        # fake timeout only needed for initialization
        active_ritual_tracker = ActiveRitualTracker(ritualist=ursula)

    now = maya.now()

    start_ritual_event = agent.contract.events.StartRitual()
    args_dict = {
        "ritualId": ritual_id_1,
        "authority": get_random_checksum_address(),
        "participants": [
            get_random_checksum_address(),
            get_random_checksum_address(),
            ursula.checksum_address,  # participating
        ],
    }

    with patch.object(
        active_ritual_tracker._participation_states,
        "purge_expired",
        wraps=active_ritual_tracker._participation_states.purge_expired,
    ) as mock_wrapped_purge_expired:
        # start ritual event for ritual 1 (participating)
        event_data = AttributeDict(
            {"event": start_ritual_event.event_name, "args": AttributeDict(args_dict)}
        )
        participation_state = active_ritual_tracker._get_participation_state(event_data)
        check_participation_state(participation_state, expected_participating=True)

        # not enough time passed for purge_expired() to be called
        mock_wrapped_purge_expired.assert_not_called()

    assert len(active_ritual_tracker._participation_states) == 1

    # modify the time that ritual id 2 is processed later on
    def maya_now_for_ritual_2():
        return now.add(
            seconds=ActiveRitualTracker._PARTICIPATION_STATES_PURGE_INTERVAL / 2
        )

    with patch.object(
        active_ritual_tracker._participation_states,
        "purge_expired",
        wraps=active_ritual_tracker._participation_states.purge_expired,
    ) as mock_wrapped_purge_expired:
        with patch("maya.now", maya_now_for_ritual_2):
            # start ritual event for ritual 2 (not participating)
            args_dict["ritualId"] = ritual_id_2
            args_dict["participants"] = [
                get_random_checksum_address(),
                get_random_checksum_address(),
                get_random_checksum_address(),
            ]

            event_data = AttributeDict(
                {
                    "event": start_ritual_event.event_name,
                    "args": AttributeDict(args_dict),
                }
            )
            participation_state = active_ritual_tracker._get_participation_state(
                event_data
            )
            check_participation_state(participation_state)

        # not enough time passed for purge_expired() to be called
        mock_wrapped_purge_expired.assert_not_called()

    assert len(active_ritual_tracker._participation_states) == 2
    # be sure that the states are properly stored
    check_participation_state(
        active_ritual_tracker._participation_states[ritual_id_1],
        expected_participating=True,
    )
    check_participation_state(active_ritual_tracker._participation_states[ritual_id_2])

    # modify time so that purge occurs when another event is received
    # fake event for ritual 2
    def maya_now_for_purge_interval():
        return now.add(
            seconds=ActiveRitualTracker._PARTICIPATION_STATES_PURGE_INTERVAL + 1
        )

    with patch.object(
        active_ritual_tracker._participation_states,
        "purge_expired",
        wraps=active_ritual_tracker._participation_states.purge_expired,
    ) as mock_wrapped_purge_expired:
        with patch("maya.now", maya_now_for_purge_interval):
            # Receive StartAggregationRound for ritual_id 2
            event_data = AttributeDict(
                {
                    "event": "StartAggregationRound",
                    "blockNumber": 1234567,
                    "args": AttributeDict(
                        {
                            "ritualId": ritual_id_2,
                        }
                    ),
                }
            )

            participation_state = active_ritual_tracker._get_participation_state(
                event_data
            )
            check_participation_state(participation_state)

        # ensure that purge_expired called - enough time has passed
        # len(states) below can call purge_expired, so this is the way
        # to be sure it's called
        mock_wrapped_purge_expired.assert_called()

    assert len(active_ritual_tracker._participation_states) == 1
    assert active_ritual_tracker._participation_states[ritual_id_1] is None
    check_participation_state(active_ritual_tracker._participation_states[ritual_id_2])


@pytest_twisted.inlineCallbacks()
def test_handle_event_multiple_concurrent_rituals(cohort, get_random_checksum_address):
    # test overall processing of events

    # let's pretend that rituals 1, 2, 3, 4 are being tracked at the same time
    ritual_id_1 = 1
    ritual_id_2 = 2
    ritual_id_3 = 3
    ritual_id_4 = 4  # ritual #4 is not being participated in

    ritual_ids = [ritual_id_1, ritual_id_2, ritual_id_3, ritual_id_4]

    ursula = cohort[0]

    ritualist = Mock(spec=Ritualist)
    ritualist.checksum_address = ursula.checksum_address
    ritualist.coordinator_agent = ursula.coordinator_agent

    active_ritual_tracker = ActiveRitualTracker(ritualist=ritualist)

    block_number = 17692417  # random block number - value doesn't matter

    def get_block_when(*args, **kwargs) -> datetime.datetime:
        return datetime.datetime.now()

    #
    # StartRitual
    #
    participants_when_participating = [
        get_random_checksum_address(),
        get_random_checksum_address(),
        get_random_checksum_address(),
        ursula.checksum_address,
    ]
    participants_when_not_participating = [
        get_random_checksum_address(),
        get_random_checksum_address(),
        get_random_checksum_address(),
    ]

    # create list of events and use appropriately
    for i, r_id in enumerate(ritual_ids):
        event_data = AttributeDict(
            {
                "event": "StartRitual",
                "blockNumber": block_number,
                "args": AttributeDict(
                    {
                        "ritualId": r_id,
                        "initiator": get_random_checksum_address(),
                        "participants": participants_when_participating
                        if r_id != ritual_id_4
                        else participants_when_not_participating,
                    }
                ),
            }
        )
        d = active_ritual_tracker._handle_ritual_event(event_data, get_block_when)
        yield d

        assert len(active_ritual_tracker._participation_states) == (i + 1)
        participation_state = active_ritual_tracker._participation_states[r_id]
        if r_id != ritual_id_4:
            ritualist.perform_round_1.assert_called_with(
                ritual_id=r_id, initiator=ANY, participants=ANY, timestamp=ANY
            )
            check_participation_state(participation_state, expected_participating=True)
        else:
            check_participation_state(participation_state, expected_participating=False)

    assert (
        ritualist.perform_round_1.call_count == 3
    )  # participation and action required
    assert ritualist.perform_round_2.call_count == 0  # nothing to do here
    assert len(active_ritual_tracker._participation_states) == 4

    #
    # Receive StartAggregationRound for ritual_id 2
    #
    event_data = AttributeDict(
        {
            "event": "StartAggregationRound",
            "blockNumber": block_number,
            "args": AttributeDict(
                {
                    "ritualId": ritual_id_2,
                }
            ),
        }
    )
    d = active_ritual_tracker._handle_ritual_event(event_data, get_block_when)
    yield d

    assert ritualist.perform_round_1.call_count == 3  # same count as before
    assert ritualist.perform_round_2.call_count == 1  # nothing to do here
    ritualist.perform_round_2.assert_called_with(ritual_id=ritual_id_2, timestamp=ANY)

    check_participation_state(
        active_ritual_tracker._participation_states[ritual_id_1],
        expected_participating=True,
    )
    check_participation_state(
        active_ritual_tracker._participation_states[ritual_id_2],
        expected_participating=True,
        expected_already_posted_transcript=True,
    )
    check_participation_state(
        active_ritual_tracker._participation_states[ritual_id_3],
        expected_participating=True,
    )
    check_participation_state(active_ritual_tracker._participation_states[ritual_id_4])

    #
    # Receive StartAggregationRound for ritual id 4
    #
    event_data = AttributeDict(
        {
            "event": "StartAggregationRound",
            "blockNumber": block_number,
            "args": AttributeDict(
                {
                    "ritualId": ritual_id_4,
                }
            ),
        }
    )
    d = active_ritual_tracker._handle_ritual_event(event_data, get_block_when)
    yield d

    assert ritualist.perform_round_1.call_count == 3  # same as before
    assert ritualist.perform_round_2.call_count == 1  # same as before

    check_participation_state(
        active_ritual_tracker._participation_states[ritual_id_1],
        expected_participating=True,
    )
    check_participation_state(
        active_ritual_tracker._participation_states[ritual_id_2],
        expected_participating=True,
        expected_already_posted_transcript=True,
    )
    check_participation_state(
        active_ritual_tracker._participation_states[ritual_id_3],
        expected_participating=True,
    )

    # don't care about ritual 4 since not participating - so no new information stored
    check_participation_state(active_ritual_tracker._participation_states[ritual_id_4])

    #
    # EndRitual received for ritual id 3 (case where sequence
    # of events are odd; eg. node restart etc.)
    #
    event_data = AttributeDict(
        {
            "event": "EndRitual",
            "blockNumber": block_number,
            "args": AttributeDict(
                {
                    "ritualId": ritual_id_3,
                    "initiator": get_random_checksum_address(),
                    "successful": True,
                }
            ),
        }
    )
    d = active_ritual_tracker._handle_ritual_event(event_data, get_block_when)
    yield d

    assert ritualist.perform_round_1.call_count == 3  # same as before
    assert ritualist.perform_round_2.call_count == 1  # same as before

    assert len(active_ritual_tracker._participation_states) == 4

    check_participation_state(
        active_ritual_tracker._participation_states[ritual_id_1],
        expected_participating=True,
    )
    check_participation_state(
        active_ritual_tracker._participation_states[ritual_id_2],
        expected_participating=True,
        expected_already_posted_transcript=True,
    )
    check_participation_state(
        active_ritual_tracker._participation_states[ritual_id_3],
        expected_participating=True,
        expected_already_posted_transcript=True,
        expected_already_posted_aggregate=True,
    )

    check_participation_state(active_ritual_tracker._participation_states[ritual_id_4])

    #
    # EndRitual received for ritual id 4
    #
    event_data = AttributeDict(
        {
            "event": "EndRitual",
            "blockNumber": block_number,
            "args": AttributeDict(
                {
                    "ritualId": ritual_id_4,
                    "initiator": get_random_checksum_address(),
                    "successful": True,
                }
            ),
        }
    )
    d = active_ritual_tracker._handle_ritual_event(event_data, get_block_when)
    yield d

    assert ritualist.perform_round_1.call_count == 3  # same as before
    assert ritualist.perform_round_2.call_count == 1  # same as before

    check_participation_state(
        active_ritual_tracker._participation_states[ritual_id_1],
        expected_participating=True,
    )
    check_participation_state(
        active_ritual_tracker._participation_states[ritual_id_2],
        expected_participating=True,
        expected_already_posted_transcript=True,
    )

    check_participation_state(
        active_ritual_tracker._participation_states[ritual_id_3],
        expected_participating=True,
        expected_already_posted_transcript=True,
        expected_already_posted_aggregate=True,
    )

    # don't care about ritual 4 since not participating - so no new information stored
    check_participation_state(active_ritual_tracker._participation_states[ritual_id_4])


def verify_non_participation_flow(
    active_ritual_tracker: ActiveRitualTracker,
    event_data: AttributeDict,
):
    ritual_id = event_data.args.ritualId

    participation_state = active_ritual_tracker._get_participation_state(event_data)
    check_participation_state(participation_state)

    # new participation state stored
    assert len(active_ritual_tracker._participation_states) == 1
    assert active_ritual_tracker._participation_states[ritual_id] == participation_state

    # check again that not participating
    participation_state = active_ritual_tracker._get_participation_state(event_data)
    check_participation_state(participation_state)

    # no new information
    assert len(active_ritual_tracker._participation_states) == 1
    assert active_ritual_tracker._participation_states[ritual_id] == participation_state


def verify_participation_flow(
    active_ritual_tracker: ActiveRitualTracker,
    event_data: AttributeDict,
    expected_posted_transcript: bool,
    expected_posted_aggregate: bool,
):
    ritual_id = event_data.args.ritualId

    participation_state = active_ritual_tracker._get_participation_state(event_data)
    check_participation_state(
        participation_state=participation_state,
        expected_participating=True,
        expected_already_posted_transcript=expected_posted_transcript,
        expected_already_posted_aggregate=expected_posted_aggregate,
    )

    # new state stored
    assert len(active_ritual_tracker._participation_states) == 1
    assert active_ritual_tracker._participation_states[ritual_id] == participation_state

    # check again if relevant
    participation_state = active_ritual_tracker._get_participation_state(event_data)
    check_participation_state(
        participation_state=participation_state,
        expected_participating=True,
        expected_already_posted_transcript=expected_posted_transcript,
        expected_already_posted_aggregate=expected_posted_aggregate,
    )

    # no new information
    assert len(active_ritual_tracker._participation_states) == 1
    assert active_ritual_tracker._participation_states[ritual_id] == participation_state

    # pretend to lose previous information eg. restart of node etc.
    active_ritual_tracker._participation_states.clear()
    assert len(active_ritual_tracker._participation_states) == 0

    participation_state = active_ritual_tracker._get_participation_state(event_data)
    check_participation_state(
        participation_state=participation_state,
        expected_participating=True,
        expected_already_posted_transcript=expected_posted_transcript,
        expected_already_posted_aggregate=expected_posted_aggregate,
    )

    # new state stored
    assert len(active_ritual_tracker._participation_states) == 1
    assert active_ritual_tracker._participation_states[ritual_id] == participation_state


def check_event_args_match_latest_event_inputs(event: ContractEvent, args_dict: Dict):
    """Ensures that we are testing with actual event arguments."""
    event_inputs = event.abi["inputs"]
    assert len(event_inputs) == len(
        args_dict
    ), "test events don't match latest Coordinator contract events"
    for event_input in event_inputs:
        assert (
            event_input["name"] in args_dict
        ), "test events don't match latest Coordinator contract events"


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
