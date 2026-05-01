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

from nucypher.blockchain.eth.actors import Operator
from nucypher.blockchain.eth.models import SigningCoordinator
from nucypher.blockchain.eth.trackers.signing import SigningRitualTracker


@pytest.fixture(scope="module")
def cohort(ursulas):
    """Creates a cohort of Ursulas"""
    nodes = list(sorted(ursulas[:4], key=lambda x: int(x.checksum_address, 16)))
    assert len(nodes) == 4  # sanity check
    return nodes


def test_signing_participation_state_identifier(cohort):
    ursula = cohort[0]
    active_ritual_tracker = SigningRitualTracker(operator=ursula)
    cohort_id = 1234
    for event in active_ritual_tracker.events:
        event_data = AttributeDict(
            {
                "event": event.event_name,
                "args": AttributeDict(
                    {
                        "cohortId": cohort_id,
                    }
                ),
            }
        )
        state_identifier = active_ritual_tracker._get_identifier(event_data)
        assert state_identifier == f"signing-{cohort_id}"


def test_action_required_not_participating(cohort, get_random_checksum_address):
    ursula = cohort[0]
    agent = ursula.signing_coordinator_agent
    active_ritual_tracker = SigningRitualTracker(operator=ursula)

    participation_state = SigningRitualTracker.SigningParticipationState(
        participating=False,  # not participating
    )

    def _my_get_participation_state(*args, **kwargs):
        return participation_state

    with patch(
        "nucypher.blockchain.eth.trackers.signing.SigningRitualTracker._get_participation_state",
        _my_get_participation_state,
    ):
        for event in agent.contract.events:
            arg_values = {
                "cohortId": 23,
            }
            ritual_event = AttributeDict(
                {
                    "event": event.event_name,
                    "args": AttributeDict(arg_values),
                }
            )

            # all events are irrelevant because not participating
            assert not active_ritual_tracker._action_required(ritual_event)


def test_action_required_only_for_events_with_corresponding_actions(cohort):
    ursula = cohort[0]
    agent = ursula.signing_coordinator_agent
    active_ritual_tracker = SigningRitualTracker(operator=ursula)

    participation_state = SigningRitualTracker.SigningParticipationState(
        participating=True,  # participating
    )

    def _my_get_participation_state(*args, **kwargs):
        return participation_state

    with patch(
        "nucypher.blockchain.eth.trackers.signing.SigningRitualTracker._get_participation_state",
        _my_get_participation_state,
    ):
        for event in agent.contract.events:
            event_type = getattr(agent.contract.events, event.event_name)
            arg_values = {
                "cohortId": 23,
            }
            ritual_event = AttributeDict(
                {
                    "event": event.event_name,
                    "args": AttributeDict(arg_values),
                }
            )

            if event_type not in active_ritual_tracker.actions:
                assert not active_ritual_tracker._action_required(ritual_event)
            else:
                # actionable events - both actions required since transcript/aggregate not posted
                assert active_ritual_tracker._action_required(ritual_event)


def test_action_required_depending_on_signing_participation_state(
    cohort, get_random_checksum_address
):
    ursula = cohort[0]
    agent = ursula.signing_coordinator_agent
    active_ritual_tracker = SigningRitualTracker(operator=ursula)

    participation_state = SigningRitualTracker.SigningParticipationState(
        participating=True,
    )

    def _my_get_participation_state(*args, **kwargs):
        return participation_state

    with patch(
        "nucypher.blockchain.eth.trackers.signing.SigningRitualTracker._get_participation_state",
        _my_get_participation_state,
    ):
        # address included in initiate cohort event - action required
        initiate_cohort_event = AttributeDict(
            {
                "event": agent.contract.events.InitiateSigningCohort.event_name,
                "args": AttributeDict(
                    {
                        "cohortId": 23,
                        "chainId": 1,
                        "authority": get_random_checksum_address(),
                        "participants": [u.checksum_address for u in cohort],
                    }
                ),
            }
        )
        assert (
            agent.contract.events.InitiateSigningCohort in active_ritual_tracker.actions
        )
        assert active_ritual_tracker._action_required(initiate_cohort_event)

        # already posted signature - action not required
        participation_state.already_posted_signature = True
        assert not active_ritual_tracker._action_required(initiate_cohort_event)


def test_get_participation_state_initiate_signing_cohort(
    cohort, get_random_checksum_address
):
    args_dict = {
        "cohortId": 12,
        "chainId": 1,
        "authority": get_random_checksum_address(),
        "participants": [
            get_random_checksum_address(),
            get_random_checksum_address(),
            get_random_checksum_address(),
        ],  # not included by default
    }
    ursula = cohort[0]
    agent = ursula.signing_coordinator_agent
    active_ritual_tracker = SigningRitualTracker(operator=ursula)

    # InitiateSigningCohort event
    initiate_signing_cohort = agent.contract.events.InitiateSigningCohort()

    # Ensure that test matches latest event information
    check_event_args_match_latest_event_inputs(
        event=initiate_signing_cohort, args_dict=args_dict
    )

    event_data = AttributeDict(
        {"event": initiate_signing_cohort.event_name, "args": AttributeDict(args_dict)}
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
        {"event": initiate_signing_cohort.event_name, "args": AttributeDict(args_dict)}
    )

    verify_participation_flow(
        active_ritual_tracker,
        event_data,
        expected_posted_signature=False,
    )


def test_get_participation_state_signing_cohort_deployed_participation_not_already_tracked(
    cohort,
):
    args_dict = {"cohortId": 12, "chainId": 1}
    ursula = cohort[0]
    agent = ursula.signing_coordinator_agent
    active_ritual_tracker = SigningRitualTracker(operator=ursula)

    cohort_deployed_event = agent.contract.events.SigningCohortDeployed()

    # ensure that test matches latest event information
    check_event_args_match_latest_event_inputs(
        event=cohort_deployed_event, args_dict=args_dict
    )
    event_data = AttributeDict(
        {"event": cohort_deployed_event.event_name, "args": AttributeDict(args_dict)}
    )

    with patch.object(agent, "is_signer", return_value=False):
        verify_non_participation_flow(active_ritual_tracker, event_data)

    #
    # clear prior information
    #
    active_ritual_tracker._participation_states.clear()

    #
    # actually participating now: signing cohort ritual successful
    #
    def participating(*args, **kwargs):
        participant = SigningCoordinator.SigningCohortParticipant(
            provider=ChecksumAddress(ursula.checksum_address),
            signer_address=ChecksumAddress(ursula.threshold_signing_power.account),
        )

        return participant

    with patch.object(agent, "is_signer", return_value=True):
        with patch.object(agent, "get_signer", side_effect=participating):
            verify_participation_flow(
                active_ritual_tracker,
                event_data,
                expected_posted_signature=True,
            )


def test_get_participation_state_signing_cohort_deployed_participation_already_tracked(
    cohort, get_random_checksum_address
):
    args_dict = {"cohortId": 12, "chainId": 1}
    ursula = cohort[0]
    agent = ursula.signing_coordinator_agent
    active_ritual_tracker = SigningRitualTracker(operator=ursula)

    cohort_deployed_event = agent.contract.events.SigningCohortDeployed()

    # ensure that test matches latest event information
    check_event_args_match_latest_event_inputs(
        event=cohort_deployed_event, args_dict=args_dict
    )
    event_data = AttributeDict(
        {"event": cohort_deployed_event.event_name, "args": AttributeDict(args_dict)}
    )

    state_identifier = active_ritual_tracker._get_identifier(event_data)

    #
    # not participating
    #

    # mimic already tracked prior state: not participating
    active_ritual_tracker._participation_states[state_identifier] = (
        active_ritual_tracker.SigningParticipationState(False, False)
    )

    verify_non_participation_flow(active_ritual_tracker, event_data)
    # no additional entry
    assert len(active_ritual_tracker._participation_states) == 1

    #
    # actually participating now
    #

    # mimic already tracked prior state: participating
    active_ritual_tracker._participation_states[state_identifier] = (
        active_ritual_tracker.SigningParticipationState(True, False)
    )

    participation_state = active_ritual_tracker._get_participation_state(event_data)
    check_participation_state(
        participation_state,
        expected_participating=True,
        expected_already_posted_signature=True,
    )

    # no additional entry
    assert (
        active_ritual_tracker._participation_states[state_identifier]
        == participation_state
    )
    assert len(active_ritual_tracker._participation_states) == 1


def test_get_participation_state_unexpected_event_without_cohort_id_arg(cohort):
    ursula = cohort[0]
    agent = ursula.signing_coordinator_agent
    active_ritual_tracker = SigningRitualTracker(operator=ursula)

    # MaxDkgSizeChanged
    max_dkg_size_changed = agent.contract.events.MaxCohortSizeChanged()

    # create args data
    args_dict = {"oldSize": 24, "newSize": 30}

    # ensure that test matches latest event information
    check_event_args_match_latest_event_inputs(
        event=max_dkg_size_changed, args_dict=args_dict
    )

    event_data = AttributeDict(
        {"event": max_dkg_size_changed.event_name, "args": AttributeDict(args_dict)}
    )

    with pytest.raises(RuntimeError):
        active_ritual_tracker._get_participation_state(event_data)


def test_get_participation_state_unexpected_event_with_cohort_id_arg(
    cohort, get_random_checksum_address
):
    ursula = cohort[0]
    agent = ursula.signing_coordinator_agent
    active_ritual_tracker = SigningRitualTracker(operator=ursula)

    # create args data - faked to include ritual id arg
    args_dict = {
        "cohortId": 0,
        "provider": get_random_checksum_address(),
        "signature": os.urandom(32),
    }

    # MaxDkgSizeChanged event
    event_data = AttributeDict(
        {
            # this is an event we don't track but has cohortId
            "event": agent.contract.events.SigningCohortSignaturePosted.event_name,
            "args": AttributeDict(args_dict),
        }
    )

    with pytest.raises(RuntimeError):
        active_ritual_tracker._get_participation_state(event_data)


def test_get_participation_state_purge_expired_cache_entries(
    cohort, get_random_checksum_address
):
    cohort_id_1 = 1  # participation
    cohort_id_2 = 2  # non participation

    state_identifier_1 = None
    state_identifier_2 = None

    chain_id = 1234

    ursula = cohort[0]
    agent = ursula.signing_coordinator_agent

    # This test hinges on the relationship between ritual timeout and the purge interval
    # This relationship should hold: ritual timeout (ttl) + buffer == to the purge
    # interval for ease of testing; so fake the ritual timeout
    faked_ritual_timeout = SigningRitualTracker._PARTICIPATION_STATES_PURGE_INTERVAL - (
        SigningRitualTracker._TIMEOUT_ADDITIONAL_TTL_BUFFER
    )

    with patch.object(agent, "get_timeout", return_value=faked_ritual_timeout):
        # fake timeout only needed for initialization
        active_ritual_tracker = SigningRitualTracker(operator=ursula)

    now = maya.now()

    initiate_signing_cohort = agent.contract.events.InitiateSigningCohort()
    args_dict = {
        "cohortId": cohort_id_1,
        "chainId": chain_id,
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
            {
                "event": initiate_signing_cohort.event_name,
                "args": AttributeDict(args_dict),
            }
        )
        state_identifier_1 = active_ritual_tracker._get_identifier(event_data)
        participation_state = active_ritual_tracker._get_participation_state(event_data)
        check_participation_state(participation_state, expected_participating=True)

        # not enough time passed for purge_expired() to be called
        mock_wrapped_purge_expired.assert_not_called()

    assert len(active_ritual_tracker._participation_states) == 1

    # modify the time that ritual id 2 is processed later on
    def maya_now_for_ritual_2():
        return now.add(
            seconds=SigningRitualTracker._PARTICIPATION_STATES_PURGE_INTERVAL / 2
        )

    with patch.object(
        active_ritual_tracker._participation_states,
        "purge_expired",
        wraps=active_ritual_tracker._participation_states.purge_expired,
    ) as mock_wrapped_purge_expired:
        with patch("maya.now", maya_now_for_ritual_2):
            # start ritual event for ritual 2 (not participating)
            args_dict["cohortId"] = cohort_id_2
            args_dict["participants"] = [
                get_random_checksum_address(),
                get_random_checksum_address(),
                get_random_checksum_address(),
            ]

            event_data = AttributeDict(
                {
                    "event": initiate_signing_cohort.event_name,
                    "args": AttributeDict(args_dict),
                }
            )
            state_identifier_2 = active_ritual_tracker._get_identifier(event_data)
            participation_state = active_ritual_tracker._get_participation_state(
                event_data
            )
            check_participation_state(participation_state)

        # not enough time passed for purge_expired() to be called
        mock_wrapped_purge_expired.assert_not_called()

    assert len(active_ritual_tracker._participation_states) == 2
    # be sure that the states are properly stored
    check_participation_state(
        active_ritual_tracker._participation_states[state_identifier_1],
        expected_participating=True,
    )
    check_participation_state(
        active_ritual_tracker._participation_states[state_identifier_2]
    )

    # modify time so that purge occurs when another event is received
    # fake event for ritual 2
    def maya_now_for_purge_interval():
        return now.add(
            seconds=SigningRitualTracker._PARTICIPATION_STATES_PURGE_INTERVAL + 1
        )

    with patch.object(
        active_ritual_tracker._participation_states,
        "purge_expired",
        wraps=active_ritual_tracker._participation_states.purge_expired,
    ) as mock_wrapped_purge_expired:
        with patch("maya.now", maya_now_for_purge_interval):
            # Receive SigningCohortDeployed for cohort_id 2
            event_data = AttributeDict(
                {
                    "event": "SigningCohortDeployed",
                    "blockNumber": 1234567,
                    "args": AttributeDict(
                        {
                            "cohortId": cohort_id_2,
                            "chainId": chain_id,
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
    assert active_ritual_tracker._participation_states[state_identifier_1] is None
    check_participation_state(
        active_ritual_tracker._participation_states[state_identifier_2]
    )


@pytest_twisted.inlineCallbacks()
def test_handle_event_multiple_concurrent_signing_rituals(
    cohort, get_random_checksum_address
):
    # test overall processing of events

    # let's pretend that rituals 1, 2, 3, 4 are being tracked at the same time
    cohort_id_1 = 1
    cohort_id_2 = 2
    cohort_id_3 = 3
    cohort_id_4 = 4  # ritual #4 is not being participated in

    cohort_ids = [cohort_id_1, cohort_id_2, cohort_id_3, cohort_id_4]
    state_identifiers = {}

    ursula = cohort[0]

    operator = Mock(spec=Operator)
    operator.checksum_address = ursula.checksum_address
    operator.signing_coordinator_agent = ursula.signing_coordinator_agent

    active_ritual_tracker = SigningRitualTracker(operator=operator)

    block_number = 17692417  # random block number - value doesn't matter

    def get_block_when(*args, **kwargs) -> datetime.datetime:
        return datetime.datetime.now()

    #
    # InitiateSigningCohort
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

    chain_id = 1234
    authority = get_random_checksum_address()

    # create list of events and use appropriately
    for i, c_id in enumerate(cohort_ids):
        event_data = AttributeDict(
            {
                "event": "InitiateSigningCohort",
                "blockNumber": block_number,
                "args": AttributeDict(
                    {
                        "cohortId": c_id,
                        "chainId": chain_id,
                        "authority": authority,
                        "participants": (
                            participants_when_participating
                            if c_id != cohort_id_4
                            else participants_when_not_participating
                        ),
                    }
                ),
            }
        )
        state_identifiers[c_id] = active_ritual_tracker._get_identifier(event_data)
        d = active_ritual_tracker._handle_event(event_data, get_block_when)
        yield d

        assert len(active_ritual_tracker._participation_states) == (i + 1)
        participation_state = active_ritual_tracker._participation_states[
            state_identifiers[c_id]
        ]
        if c_id != cohort_id_4:
            operator.perform_post_signature.assert_called_with(
                cohort_id=c_id,
                chain_id=chain_id,
                authority=authority,
                participants=participants_when_participating,
                timestamp=ANY,
            )
            check_participation_state(participation_state, expected_participating=True)
        else:
            check_participation_state(participation_state, expected_participating=False)

    assert (
        operator.perform_post_signature.call_count == 3
    )  # participation and action required
    assert len(active_ritual_tracker._participation_states) == 4

    #
    # Receive SigningCohortDeployed for cohort_id 2
    #
    event_data = AttributeDict(
        {
            "event": "SigningCohortDeployed",
            "blockNumber": block_number,
            "args": AttributeDict(
                {
                    "cohortId": cohort_id_2,
                    "chainId": chain_id,
                }
            ),
        }
    )
    d = active_ritual_tracker._handle_event(event_data, get_block_when)
    yield d

    assert operator.perform_post_signature.call_count == 3  # same count as before
    assert len(active_ritual_tracker._participation_states) == 4

    check_participation_state(
        active_ritual_tracker._participation_states[state_identifiers[cohort_id_1]],
        expected_participating=True,
    )
    check_participation_state(
        active_ritual_tracker._participation_states[state_identifiers[cohort_id_2]],
        expected_participating=True,
        expected_already_posted_signature=True,
    )
    check_participation_state(
        active_ritual_tracker._participation_states[state_identifiers[cohort_id_3]],
        expected_participating=True,
    )
    check_participation_state(
        active_ritual_tracker._participation_states[state_identifiers[cohort_id_4]]
    )

    #
    # Receive SigningCohortDeployed for cohort_id 4
    #
    event_data = AttributeDict(
        {
            "event": "SigningCohortDeployed",
            "blockNumber": block_number,
            "args": AttributeDict(
                {
                    "cohortId": cohort_id_4,
                    "chainId": chain_id,
                }
            ),
        }
    )
    d = active_ritual_tracker._handle_event(event_data, get_block_when)
    yield d

    assert operator.perform_post_signature.call_count == 3  # same count as before
    assert len(active_ritual_tracker._participation_states) == 4

    check_participation_state(
        active_ritual_tracker._participation_states[state_identifiers[cohort_id_1]],
        expected_participating=True,
    )
    check_participation_state(
        active_ritual_tracker._participation_states[state_identifiers[cohort_id_2]],
        expected_participating=True,
        expected_already_posted_signature=True,
    )
    check_participation_state(
        active_ritual_tracker._participation_states[state_identifiers[cohort_id_3]],
        expected_participating=True,
    )

    # don't care about ritual 4 since not participating - so no new information stored
    check_participation_state(
        active_ritual_tracker._participation_states[state_identifiers[cohort_id_4]]
    )

    #
    # SigningCohortDeployed received for cohort id 3
    #
    event_data = AttributeDict(
        {
            "event": "SigningCohortDeployed",
            "blockNumber": block_number,
            "args": AttributeDict(
                {
                    "cohortId": cohort_id_3,
                    "chainId": chain_id,
                }
            ),
        }
    )
    d = active_ritual_tracker._handle_event(event_data, get_block_when)
    yield d

    assert operator.perform_post_signature.call_count == 3  # same as before
    assert len(active_ritual_tracker._participation_states) == 4

    check_participation_state(
        active_ritual_tracker._participation_states[state_identifiers[cohort_id_1]],
        expected_participating=True,
    )
    check_participation_state(
        active_ritual_tracker._participation_states[state_identifiers[cohort_id_2]],
        expected_participating=True,
        expected_already_posted_signature=True,
    )
    check_participation_state(
        active_ritual_tracker._participation_states[state_identifiers[cohort_id_3]],
        expected_participating=True,
        expected_already_posted_signature=True,
    )

    check_participation_state(
        active_ritual_tracker._participation_states[state_identifiers[cohort_id_4]]
    )


def verify_non_participation_flow(
    active_ritual_tracker: SigningRitualTracker,
    event_data: AttributeDict,
):
    state_identifier = active_ritual_tracker._get_identifier(event_data)

    participation_state = active_ritual_tracker._get_participation_state(event_data)
    check_participation_state(participation_state)

    # new participation state stored
    assert len(active_ritual_tracker._participation_states) == 1
    assert (
        active_ritual_tracker._participation_states[state_identifier]
        == participation_state
    )

    # check again that not participating
    participation_state = active_ritual_tracker._get_participation_state(event_data)
    check_participation_state(participation_state)

    # no new information
    assert len(active_ritual_tracker._participation_states) == 1
    assert (
        active_ritual_tracker._participation_states[state_identifier]
        == participation_state
    )


def verify_participation_flow(
    active_ritual_tracker: SigningRitualTracker,
    event_data: AttributeDict,
    expected_posted_signature: bool,
):
    state_identifier = active_ritual_tracker._get_identifier(event_data)

    participation_state = active_ritual_tracker._get_participation_state(event_data)
    check_participation_state(
        participation_state=participation_state,
        expected_participating=True,
        expected_already_posted_signature=expected_posted_signature,
    )

    # new state stored
    assert len(active_ritual_tracker._participation_states) == 1
    assert (
        active_ritual_tracker._participation_states[state_identifier]
        == participation_state
    )

    # check again if relevant
    participation_state = active_ritual_tracker._get_participation_state(event_data)
    check_participation_state(
        participation_state=participation_state,
        expected_participating=True,
        expected_already_posted_signature=expected_posted_signature,
    )

    # no new information
    assert len(active_ritual_tracker._participation_states) == 1
    assert (
        active_ritual_tracker._participation_states[state_identifier]
        == participation_state
    )

    # pretend to lose previous information eg. restart of node etc.
    active_ritual_tracker._participation_states.clear()
    assert len(active_ritual_tracker._participation_states) == 0

    participation_state = active_ritual_tracker._get_participation_state(event_data)
    check_participation_state(
        participation_state=participation_state,
        expected_participating=True,
        expected_already_posted_signature=expected_posted_signature,
    )

    # new state stored
    assert len(active_ritual_tracker._participation_states) == 1
    assert (
        active_ritual_tracker._participation_states[state_identifier]
        == participation_state
    )


def check_event_args_match_latest_event_inputs(event: ContractEvent, args_dict: Dict):
    """Ensures that we are testing with actual event arguments."""
    event_inputs = event.abi["inputs"]
    assert len(event_inputs) == len(
        args_dict
    ), "test events don't match latest SigningCoordinator contract events"
    for event_input in event_inputs:
        assert (
            event_input["name"] in args_dict
        ), "test events don't match latest SigningCoordinator contract events"


def check_participation_state(
    participation_state: SigningRitualTracker.SigningParticipationState,
    expected_participating: bool = False,
    expected_already_posted_signature: bool = False,
):
    assert participation_state.participating == expected_participating
    assert (
        participation_state.already_posted_signature
        == expected_already_posted_signature
    )
