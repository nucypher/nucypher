from unittest.mock import Mock

from nucypher.utilities.events import EventScanner


def test_estimate_next_chunk_size():
    web3 = Mock()
    contract = Mock()
    state = Mock()

    scanner = EventScanner(
        web3=web3, contract=contract, state=state, events=[], filters={}
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
