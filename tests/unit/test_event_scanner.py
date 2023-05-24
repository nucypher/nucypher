import math
import time
from datetime import datetime
from typing import List, Tuple
from unittest.mock import MagicMock, Mock

import pytest

from nucypher.utilities.events import EventScanner, EventScannerState, JSONifiedState


def test_estimate_next_chunk_size():
    scanner = EventScanner(
        web3=Mock(), contract=Mock(), state=Mock(), events=[], filters={}
    )

    # no prior events found
    current_chunk_size = 20
    while current_chunk_size < scanner.max_scan_chunk_size:
        next_chunk_size = scanner.estimate_next_chunk_size(
            current_chunk_size=current_chunk_size, event_found_count=0
        )
        assert next_chunk_size == min(
            scanner.max_scan_chunk_size,
            (current_chunk_size * scanner.chunk_size_increase),
        )
        current_chunk_size = next_chunk_size

    next_chunk_size = scanner.estimate_next_chunk_size(
        current_chunk_size=current_chunk_size, event_found_count=0
    )
    assert next_chunk_size == scanner.max_scan_chunk_size
    current_chunk_size = next_chunk_size

    # event(s) found
    for i in range(1, 10):
        next_chunk_size = scanner.estimate_next_chunk_size(
            current_chunk_size=current_chunk_size, event_found_count=i
        )
        assert next_chunk_size == scanner.min_scan_chunk_size
        current_chunk_size = next_chunk_size

    # events no longer found again
    while current_chunk_size < scanner.max_scan_chunk_size:
        next_chunk_size = scanner.estimate_next_chunk_size(
            current_chunk_size=current_chunk_size, event_found_count=0
        )
        assert next_chunk_size == min(
            scanner.max_scan_chunk_size,
            (current_chunk_size * scanner.chunk_size_increase),
        )
        current_chunk_size = next_chunk_size


def test_suggested_scan_start_block():
    state = Mock(spec=EventScannerState)

    chain_reorg_window = 10
    scanner = EventScanner(
        web3=Mock(),
        contract=Mock(),
        state=state,
        events=[],
        filters={},
        chain_reorg_rescan_window=chain_reorg_window,
    )

    # mimic start
    last_scanned_block = 0
    state.get_last_scanned_block.return_value = last_scanned_block
    assert scanner.get_suggested_scan_start_block() == 1  # first block

    # we've progressed less than change reorg
    last_scanned_block = chain_reorg_window - 4
    state.get_last_scanned_block.return_value = last_scanned_block
    assert scanner.get_suggested_scan_start_block() == 1  # still first block

    # we've progressed further
    last_scanned_blocks = [19, 100, 242341, 151552423]
    for last_scanned_block in last_scanned_blocks:
        state.get_last_scanned_block.return_value = last_scanned_block
        assert scanner.get_suggested_scan_start_block() == (
            last_scanned_block - chain_reorg_window
        )


def test_suggested_scan_end_block():
    web3 = MagicMock()

    chain_reorg_window = 10
    scanner = EventScanner(
        web3=web3,
        contract=Mock(),
        state=Mock(),
        events=[],
        filters={},
        chain_reorg_rescan_window=chain_reorg_window,
    )

    block_nums = [1, 10, 231, 12319021]
    for block_num in block_nums:
        web3.eth.block_number = block_num
        assert scanner.get_suggested_scan_end_block() == (block_num - 1)


def test_get_block_timestamp():
    web3 = MagicMock()

    scanner = EventScanner(
        web3=web3,
        contract=Mock(),
        state=Mock(),
        events=[],
        filters={},
    )

    now = time.time()
    web3.eth.get_block.return_value = {"timestamp": now}
    assert scanner.get_block_timestamp(block_num=0) == datetime.utcfromtimestamp(now)

    other_time = time.time() - 1231231
    web3.eth.get_block.return_value = {"timestamp": other_time}
    assert scanner.get_block_timestamp(block_num=21) == datetime.utcfromtimestamp(
        other_time
    )


def test_scan_invalid_start_end_block():
    scanner = EventScanner(
        web3=Mock(),
        contract=Mock(),
        state=Mock(),
        events=[],
        filters={},
        chain_reorg_rescan_window=10,
    )

    with pytest.raises(ValueError):
        # invalid: end_block > start_block
        scanner.scan(start_block=11, end_block=10)


@pytest.mark.parametrize("chunk_size", [1, 3, 5, 7, 10])
def test_scan_when_events_always_found(chunk_size):
    state = JSONifiedState(persistent=False)
    state.reset()  # TODO why is this eneded if persistent is False
    start_block = 0
    end_block = 100

    scanner = MyEventScanner(
        web3=Mock(),
        contract=Mock(),
        state=state,
        events=[],
        filters={},
        chain_reorg_rescan_window=10,
        min_chunk_scan_size=chunk_size,
        target_end_block=end_block,
    )

    expected_calls = generate_expected_scan_calls_results(
        scanner, start_block, end_block
    )

    all_processed, total_chunks_scanned = scanner.scan(
        start_block, end_block, start_chunk_size=chunk_size
    )
    assert total_chunks_scanned == len(expected_calls)
    assert scanner.scan_chunk_calls_made == expected_calls
    assert scanner.get_last_scanned_block() == end_block


@pytest.mark.parametrize("chunk_size", [2, 6, 7, 11, 15])
def test_scan_when_events_never_found(chunk_size):
    state = JSONifiedState(persistent=False)
    state.reset()  # TODO why is this eneded if persistent is False
    start_block = 0
    end_block = 999

    scanner = MyEventScanner(
        web3=Mock(),
        contract=Mock(),
        state=state,
        events=[],
        filters={},
        chain_reorg_rescan_window=10,
        min_chunk_scan_size=chunk_size,
        return_event_for_scan_chunk=False,  # min chunk size not used (but scales up)
        target_end_block=end_block,
    )

    expected_calls = generate_expected_scan_calls_results(
        scanner, start_block, end_block
    )

    all_processed, total_chunks_scanned = scanner.scan(
        start_block, end_block, start_chunk_size=chunk_size
    )

    assert total_chunks_scanned == len(expected_calls)
    assert len(all_processed) == 0  # no events processed
    assert scanner.scan_chunk_calls_made == expected_calls
    assert scanner.get_last_scanned_block() == end_block


def generate_expected_scan_calls_results(scanner, start_block, end_block):
    expected_calls = []
    current_chunk_size = scanner.min_scan_chunk_size
    while True:
        chunk_end_block = start_block + current_chunk_size
        expected_calls.append((start_block, chunk_end_block))
        start_block = chunk_end_block + 1  # next block
        current_chunk_size = (
            current_chunk_size
            if scanner.return_chunk_scan_event
            else current_chunk_size * scanner.chunk_size_increase
        )
        if start_block > end_block:
            break

    return expected_calls


class MyEventScanner(EventScanner):
    def __init__(
        self,
        target_end_block: int,
        return_event_for_scan_chunk: bool = True,
        *args,
        **kwargs
    ):
        super().__init__(*args, **kwargs)
        self.target_end_block = target_end_block
        self.chunk_calls_made = []
        self.return_chunk_scan_event = return_event_for_scan_chunk

    def scan_chunk(self, start_block, end_block) -> Tuple[int, datetime, list]:
        assert start_block < end_block
        self.chunk_calls_made.append((start_block, end_block))
        event = ["event"] if self.return_chunk_scan_event else []
        end_block = min(end_block, self.target_end_block)
        return end_block, datetime.now(), event  # results

    @property
    def scan_chunk_calls_made(self):
        return self.chunk_calls_made
