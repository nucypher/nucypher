import os
from typing import NamedTuple
from unittest.mock import Mock

import maya
import pytest

from nucypher.blockchain.eth.actors import Operator
from nucypher.blockchain.eth.agents import CoordinatorAgent
from nucypher.blockchain.eth.trackers.dkg import ActiveRitualTracker


# mimic blockchain block information
class BlockInfo(NamedTuple):
    number: int
    timestamp: int


@pytest.fixture(scope="function")
def ritualist(ursulas, mock_coordinator_agent) -> Operator:
    ursula = ursulas[0]
    mocked_agent = Mock(spec=CoordinatorAgent)
    mocked_agent.contract = mock_coordinator_agent.contract
    mocked_agent.get_timeout.return_value = 60  # 60s
    mocked_blockchain = Mock()
    mocked_agent.blockchain = mocked_blockchain
    mocked_w3 = Mock()
    mocked_blockchain.w3 = mocked_w3

    ursula.coordinator_agent = mocked_agent
    return ursula


def test_first_scan_start_block_number_simple(ritualist):
    mocked_agent = ritualist.coordinator_agent
    active_ritual_tracker = ActiveRitualTracker(operator=ritualist)
    now = maya.now()

    # latest block is 0 - return it
    mocked_agent.blockchain.w3.eth.get_block.return_value = BlockInfo(0, now.epoch)
    first_scan_block_number = active_ritual_tracker._get_first_scan_start_block_number()
    assert first_scan_block_number == 0

    #
    # sample window too large
    #
    latest_block_number = 90
    latest_timestamp = now.epoch

    sample_window = 100  # > latest block

    def get_block_side_effect(block_identifier):
        if block_identifier == "latest":
            return BlockInfo(latest_block_number, latest_timestamp)

        return 0

    mocked_agent.blockchain.w3.eth.get_block.side_effect = get_block_side_effect
    first_scan_block_number = active_ritual_tracker._get_first_scan_start_block_number(
        sample_window_size=sample_window
    )
    assert first_scan_block_number == 0


def test_first_scan_start_block_calc_is_perfect(ritualist):
    mocked_agent = ritualist.coordinator_agent
    active_ritual_tracker = ActiveRitualTracker(operator=ritualist)
    now = maya.now()

    #
    # case where we go back sufficient blocks based on calc
    #
    latest_block_number = 36279071
    latest_timestamp = now.epoch

    sample_window = 100

    sample_base_block_number = latest_block_number - sample_window
    # timeout
    ritual_timeout = 60 * 60 * 24  # 24 hours
    mocked_agent.get_timeout.return_value = ritual_timeout
    target_average_block_time = 8  # 8s block time
    sample_base_block_timestamp = now.subtract(
        seconds=target_average_block_time * sample_window
    ).epoch

    expected_number_blocks_in_past = (int)(ritual_timeout / target_average_block_time)
    expected_first_scan_block_number = (
        latest_block_number - expected_number_blocks_in_past
    )
    expected_first_scan_block_timestamp = now.subtract(
        seconds=expected_number_blocks_in_past * target_average_block_time
    ).epoch

    calls_to_get_block = []

    def get_block_side_effect(block_identifier):
        calls_to_get_block.append(block_identifier)
        if block_identifier == "latest":
            return BlockInfo(latest_block_number, latest_timestamp)
        elif block_identifier == sample_base_block_number:
            return BlockInfo(sample_base_block_number, sample_base_block_timestamp)
        elif block_identifier == expected_first_scan_block_number:
            return BlockInfo(
                expected_first_scan_block_number, expected_first_scan_block_timestamp
            )

        raise ValueError(
            f"unexpected block identifier, {block_identifier}, used during test"
        )

    mocked_agent.blockchain.w3.eth.get_block.side_effect = get_block_side_effect
    first_scan_block_number = active_ritual_tracker._get_first_scan_start_block_number(
        sample_window_size=sample_window
    )

    # create expected calls list of block ids
    expected_calls_to_get_block = [
        "latest",
        sample_base_block_number,
        expected_first_scan_block_number,
    ]

    assert len(calls_to_get_block) == len(expected_calls_to_get_block)
    assert calls_to_get_block == expected_calls_to_get_block

    # returns the block before to be sure
    assert first_scan_block_number == expected_first_scan_block_number - 1


def test_first_scan_start_block_calc_is_not_perfect_go_back_more_blocks(ritualist):
    mocked_agent = ritualist.coordinator_agent
    active_ritual_tracker = ActiveRitualTracker(operator=ritualist)
    now = maya.now()

    #
    # case where we go back sufficient blocks based on calc but calc comes up short
    # so we need to go further back
    #
    latest_block_number = 36279076
    latest_timestamp = now.epoch

    sample_window = 100

    sample_base_block_number = latest_block_number - sample_window
    # timeout
    ritual_timeout = 60 * 60 * 24  # 24 hours
    mocked_agent.get_timeout.return_value = ritual_timeout

    target_average_block_time = 12  # 12s block tim4e
    sample_base_block_timestamp = now.subtract(
        seconds=target_average_block_time * sample_window
    ).epoch

    expected_number_blocks_in_past = (int)(ritual_timeout / target_average_block_time)
    expected_timestamp = now.subtract(seconds=ritual_timeout).epoch

    initial_calc_potential_first_scan_block_number = (
        latest_block_number - expected_number_blocks_in_past
    )
    # pretend initial calc using sample window is short based on timestamp
    # i.e. average block time used wasn't perfect
    # make timestamp short by equivalent number of blocks
    initial_calc_short_by_blocks = 10  # short by 10 blocks
    initial_calc_potential_first_scan_block_timestamp = expected_timestamp + (
        initial_calc_short_by_blocks * target_average_block_time
    )

    correct_first_scan_block_number = (
        initial_calc_potential_first_scan_block_number - initial_calc_short_by_blocks
    )
    correct_first_scan_block_timestamp = (
        initial_calc_potential_first_scan_block_timestamp
        - (initial_calc_short_by_blocks * target_average_block_time)
    )

    calls_to_get_block = []

    def get_block_side_effect(block_identifier):
        calls_to_get_block.append(block_identifier)

        if block_identifier == "latest":
            return BlockInfo(latest_block_number, latest_timestamp)
        elif block_identifier == sample_base_block_number:
            return BlockInfo(sample_base_block_number, sample_base_block_timestamp)
        elif block_identifier == initial_calc_potential_first_scan_block_number:
            return BlockInfo(
                number=initial_calc_potential_first_scan_block_number,
                timestamp=initial_calc_potential_first_scan_block_timestamp,
            )

        # this is us continuously going back block by block because the timestamp was not
        # far back enough for the timeout
        elif (
            correct_first_scan_block_number
            < block_identifier
            < initial_calc_potential_first_scan_block_number
        ):
            short_by_blocks = (
                initial_calc_potential_first_scan_block_number - block_identifier
            )
            return BlockInfo(
                number=initial_calc_potential_first_scan_block_number - short_by_blocks,
                timestamp=initial_calc_potential_first_scan_block_timestamp
                - (short_by_blocks * target_average_block_time),
            )

        # now we are at the expected block
        elif block_identifier == correct_first_scan_block_number:
            return BlockInfo(
                correct_first_scan_block_number, correct_first_scan_block_timestamp
            )

        # unexpected scenario - fail here
        raise ValueError(
            f"unexpected block identifier, {block_identifier}, used during test"
        )

    mocked_agent.blockchain.w3.eth.get_block.side_effect = get_block_side_effect
    first_scan_block_number = active_ritual_tracker._get_first_scan_start_block_number(
        sample_window_size=sample_window
    )

    # create expected calls list of block ids
    expected_calls_to_get_block = [
        "latest",
        sample_base_block_number,
        initial_calc_potential_first_scan_block_number,
    ]
    for i in range(1, initial_calc_short_by_blocks):
        # include blocks when algorithm went further back
        expected_calls_to_get_block.append(
            initial_calc_potential_first_scan_block_number - i
        )
    expected_calls_to_get_block.append(correct_first_scan_block_number)

    # ensure calls were expected
    assert len(calls_to_get_block) == len(expected_calls_to_get_block)
    assert calls_to_get_block == expected_calls_to_get_block

    # returns the block before to be sure
    assert first_scan_block_number == correct_first_scan_block_number - 1


def test_get_ritual_participant_info(ritualist, get_random_checksum_address):
    mocked_agent = ritualist.coordinator_agent
    active_ritual_tracker = ActiveRitualTracker(operator=ritualist)

    participants = []
    # random participants
    for i in range(0, 3):
        participant = CoordinatorAgent.Ritual.Participant(
            provider=get_random_checksum_address()
        )
        participants.append(participant)
    mocked_agent.get_participants.return_value = participants

    # operator not in participants list
    participant_info = active_ritual_tracker._get_ritual_participant_info(ritual_id=0)
    assert participant_info is None

    # add operator to participants list
    participant = CoordinatorAgent.Ritual.Participant(
        provider=ritualist.checksum_address
    )
    participants.append(participant)

    # operator in participants list
    participant_info = active_ritual_tracker._get_ritual_participant_info(ritual_id=0)
    assert participant_info
    assert participant_info.provider == ritualist.checksum_address


def test_get_participation_state_values_from_contract(
    ritualist, get_random_checksum_address
):
    mocked_agent = ritualist.coordinator_agent
    active_ritual_tracker = ActiveRitualTracker(operator=ritualist)

    participants = []
    # random participants
    for i in range(0, 5):
        participant = CoordinatorAgent.Ritual.Participant(
            provider=get_random_checksum_address()
        )
        participants.append(participant)

    mocked_agent.get_participants.return_value = participants

    # not participating so everything should be False
    (
        participating,
        posted_transcript,
        posted_aggregate,
    ) = active_ritual_tracker._get_participation_state_values_from_contract(ritual_id=0)
    assert not participating
    assert not posted_transcript
    assert not posted_aggregate

    # add operator to participants list
    ritual_participant = CoordinatorAgent.Ritual.Participant(
        provider=ritualist.checksum_address
    )
    participants.append(ritual_participant)

    # participating, but nothing submitted
    (
        participating,
        posted_transcript,
        posted_aggregate,
    ) = active_ritual_tracker._get_participation_state_values_from_contract(ritual_id=0)
    assert participating
    assert not posted_transcript
    assert not posted_aggregate

    # submit transcript
    ritual_participant.transcript = os.urandom(32)
    (
        participating,
        posted_transcript,
        posted_aggregate,
    ) = active_ritual_tracker._get_participation_state_values_from_contract(ritual_id=0)
    assert participating
    assert posted_transcript
    assert not posted_aggregate

    # submit aggregate
    ritual_participant.aggregated = True
    (
        participating,
        posted_transcript,
        posted_aggregate,
    ) = active_ritual_tracker._get_participation_state_values_from_contract(ritual_id=0)
    assert participating
    assert posted_transcript
    assert posted_aggregate
