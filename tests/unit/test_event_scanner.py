import copy
import json
import math
import time
from datetime import datetime, timezone
from typing import Tuple
from unittest.mock import MagicMock, Mock

import pytest
import requests
from requests import HTTPError

from nucypher.blockchain.eth.trackers.dkg import DkgRitualTracker
from nucypher.blockchain.eth.trackers.events import EventScannerTask
from nucypher.utilities.events import (
    ALCHEMY_FREE_TIER_MAX_CHUNK_NUM_BLOCKS,
    MAX_CHUNK_NUM_BLOCKS,
    MIN_CHUNK_NUM_BLOCKS,
    EventScanner,
    EventScannerState,
    JSONifiedState,
    is_alchemy_free_tier,
)

CHAIN_REORG_WINDOW = DkgRitualTracker.CHAIN_REORG_SCAN_WINDOW


def test_min_scan_chunk_size_enforcement():
    with pytest.raises(ValueError, match="Min scan chunk size must be at least"):
        _ = EventScanner(
            web3=Mock(),
            contract=Mock(),
            state=Mock(),
            events=[],
            min_chunk_scan_size=MIN_CHUNK_NUM_BLOCKS - 1,
        )


def test_max_scan_chunk_size_enforcement():
    with pytest.raises(ValueError, match="Max scan chunk size must be at most"):
        _ = EventScanner(
            web3=Mock(),
            contract=Mock(),
            state=Mock(),
            events=[],
            max_chunk_scan_size=MAX_CHUNK_NUM_BLOCKS + 1,
        )


@pytest.mark.parametrize("factor", [0, 1, 1.5, 2.24])
def test_chunk_size_decrease_factor_enforcement(factor):
    with pytest.raises(ValueError, match="Chunk size decrease factor must be between"):
        _ = EventScanner(
            web3=Mock(),
            contract=Mock(),
            state=Mock(),
            events=[],
            chunk_size_decrease_factor=factor,
        )


@pytest.mark.parametrize("factor", [0.1, 0.5, 0.999, 1])
def test_chunk_size_increase_factor_enforcement(factor):
    with pytest.raises(ValueError, match="Chunk size increase factor must be greater"):
        _ = EventScanner(
            web3=Mock(),
            contract=Mock(),
            state=Mock(),
            events=[],
            chunk_size_increase_factor=factor,
        )

def test_estimate_next_chunk_size():
    scanner = EventScanner(web3=Mock(), contract=Mock(), state=Mock(), events=[])

    # no prior events found
    current_chunk_size = 20
    while current_chunk_size < scanner.max_scan_chunk_size:
        next_chunk_size = scanner.estimate_next_chunk_size(
            current_chunk_size=current_chunk_size, event_found_count=0
        )
        assert next_chunk_size == min(
            scanner.max_scan_chunk_size,
            (current_chunk_size * scanner.chunk_size_increase_factor),
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
            (current_chunk_size * scanner.chunk_size_increase_factor),
        )
        current_chunk_size = next_chunk_size


def test_suggested_scan_start_block():
    state = Mock(spec=EventScannerState)

    scanner = EventScanner(
        web3=Mock(),
        contract=Mock(),
        state=state,
        events=[],
        chain_reorg_rescan_window=CHAIN_REORG_WINDOW,
    )

    # mimic start
    last_scanned_block = 0
    state.get_last_scanned_block.return_value = last_scanned_block
    assert scanner.get_suggested_scan_start_block() == 1  # first block

    # we've progressed less than change reorg
    last_scanned_block = CHAIN_REORG_WINDOW - 4
    state.get_last_scanned_block.return_value = last_scanned_block
    assert scanner.get_suggested_scan_start_block() == 1  # still first block

    # we've progressed further
    last_scanned_blocks = [19, 100, 242341, 151552423]
    for last_scanned_block in last_scanned_blocks:
        state.get_last_scanned_block.return_value = last_scanned_block
        assert scanner.get_suggested_scan_start_block() == max(
            1, last_scanned_block - CHAIN_REORG_WINDOW
        )


def test_suggested_scan_end_block():
    web3 = MagicMock()

    scanner = EventScanner(
        web3=web3,
        contract=Mock(),
        state=Mock(),
        events=[],
        chain_reorg_rescan_window=CHAIN_REORG_WINDOW,
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
    )

    now = time.time()
    web3.eth.get_block.return_value = {"timestamp": now}
    assert scanner.get_block_timestamp(block_num=0) == datetime.fromtimestamp(
        now, tz=timezone.utc
    )

    other_time = time.time() - 1231231
    web3.eth.get_block.return_value = {"timestamp": other_time}
    assert scanner.get_block_timestamp(block_num=21) == datetime.fromtimestamp(
        other_time, tz=timezone.utc
    )


def test_scan_invalid_start_end_block():
    scanner = EventScanner(
        web3=Mock(),
        contract=Mock(),
        state=Mock(),
        events=[],
        chain_reorg_rescan_window=CHAIN_REORG_WINDOW,
    )

    with pytest.raises(ValueError):
        # invalid: end_block > start_block
        scanner.scan(start_block=11, end_block=10)


@pytest.mark.parametrize("chunk_size", [11, 13, 15, 17, 20])
def test_scan_when_events_always_found(chunk_size):
    state = JSONifiedState(persistent=False)
    state.reset()  # TODO why is this needed if persistent is False
    start_block = 0
    end_block = 100

    scanner = MyEventScanner(
        web3=Mock(),
        contract=Mock(),
        state=state,
        events=[],
        chain_reorg_rescan_window=CHAIN_REORG_WINDOW,
        min_chunk_scan_size=chunk_size,
        target_end_block=end_block,
    )

    expected_calls = generate_expected_scan_calls_results(
        scanner, start_block, end_block
    )

    all_processed, total_chunks_scanned = scanner.scan(start_block, end_block)
    assert total_chunks_scanned == len(expected_calls)
    assert scanner.scan_chunk_calls_made == expected_calls
    assert scanner.get_last_scanned_block() == end_block

    # check value for next scan
    assert scanner.get_suggested_scan_start_block() == (end_block - CHAIN_REORG_WINDOW)


@pytest.mark.parametrize("chunk_size", [12, 16, 17, 21, 25, 30])
def test_scan_when_events_never_found(chunk_size):
    state = JSONifiedState(persistent=False)
    state.reset()  # TODO why is this needed if persistent is False
    start_block = 0
    end_block = 999

    scanner = MyEventScanner(
        web3=Mock(),
        contract=Mock(),
        state=state,
        events=[],
        chain_reorg_rescan_window=CHAIN_REORG_WINDOW,
        min_chunk_scan_size=chunk_size,
        return_event_for_scan_chunk=False,  # min chunk size not used (but scales up)
        target_end_block=end_block,
    )

    expected_calls = generate_expected_scan_calls_results(
        scanner, start_block, end_block
    )

    all_processed, total_chunks_scanned = scanner.scan(start_block, end_block)

    assert total_chunks_scanned == len(expected_calls)
    assert len(all_processed) == 0  # no events processed
    assert scanner.scan_chunk_calls_made == expected_calls
    assert len(scanner.scan_chunk_calls_made) <= math.ceil(
        (end_block - start_block) / chunk_size
    )
    assert scanner.get_last_scanned_block() == end_block

    # check value for next scan
    assert scanner.get_suggested_scan_start_block() == (end_block - CHAIN_REORG_WINDOW)


def test_scan_when_events_never_found_super_large_chunk_sizes():
    state = JSONifiedState(persistent=False)
    state.reset()  # TODO why is this needed if persistent is False
    start_block = 0
    end_block = 1320000

    min_chunk_size = 150
    max_chunk_size = MAX_CHUNK_NUM_BLOCKS

    scanner = MyEventScanner(
        web3=Mock(),
        contract=Mock(),
        state=state,
        events=[],
        chain_reorg_rescan_window=CHAIN_REORG_WINDOW,
        min_chunk_scan_size=min_chunk_size,
        max_chunk_scan_size=max_chunk_size,
        return_event_for_scan_chunk=False,  # min chunk size not used (but scales up)
        target_end_block=end_block,
    )

    expected_calls = generate_expected_scan_calls_results(
        scanner, start_block, end_block
    )

    all_processed, total_chunks_scanned = scanner.scan(start_block, end_block)

    assert total_chunks_scanned == len(expected_calls)
    assert len(all_processed) == 0  # no events processed
    assert scanner.scan_chunk_calls_made == expected_calls
    assert scanner.get_last_scanned_block() == end_block

    # check value for next scan
    assert scanner.get_suggested_scan_start_block() == (end_block - CHAIN_REORG_WINDOW)


def generate_expected_scan_calls_results(scanner, start_block, end_block):
    expected_calls = []
    current_chunk_size = scanner.min_scan_chunk_size
    while True:
        chunk_end_block = min(start_block + current_chunk_size, end_block)
        expected_calls.append((start_block, chunk_end_block))
        start_block = chunk_end_block + 1  # next block
        if not scanner.return_chunk_scan_event:
            current_chunk_size = min(
                scanner.max_scan_chunk_size,
                current_chunk_size * scanner.chunk_size_increase_factor,
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
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.target_end_block = target_end_block
        self.chunk_calls_made = []
        self.return_chunk_scan_event = return_event_for_scan_chunk

    def scan_chunk(self, start_block, end_block) -> Tuple[int, list]:
        assert start_block <= end_block
        assert end_block <= self.target_end_block
        self.chunk_calls_made.append((start_block, end_block))
        event = ["event"] if self.return_chunk_scan_event else []
        return end_block, event  # results

    @property
    def scan_chunk_calls_made(self):
        return self.chunk_calls_made


def test_event_scanner_task():
    scanner = EventScanner(
        web3=Mock(),
        contract=Mock(),
        state=Mock(),
        events=[],
        chain_reorg_rescan_window=CHAIN_REORG_WINDOW,
    )
    task = EventScannerTask(scanner.scan)

    assert task.interval == EventScannerTask.INTERVAL
    assert task.scanner == scanner.scan


ALCHEMY_FREE_TIER_RESPONSE_DICT = {
    "jsonrpc": "2.0",
    "id": 6,
    "error": {
        "code": -32600,
        "message": "Under the Free tier plan, you can make eth_getLogs requests with up to a 10 block range. Based on your parameters, this block range should work: [0x48af181, 0x48af18a]. Upgrade to PAYG for expanded block range.",
    },
}


def test_is_alchemy_free_tier(mocker):
    web3 = mocker.Mock()

    http_error = mocker.Mock(spec=HTTPError)
    http_error.response = mocker.Mock()
    http_error.response.json.return_value = ALCHEMY_FREE_TIER_RESPONSE_DICT

    # endpoint does not include 'alchemy'
    web3.provider.endpoint_uri = "https://polygon-mainnet.infura.io/v3/1234567890abcdef"
    assert is_alchemy_free_tier(web3, http_error) is False
    web3.provider.endpoint_uri = (
        "https://polygon-mainnet.g.alchemy.com/v2/1234567890abcdef"  # correct endpoint
    )

    # response is not 400
    for error_code in [200, 300, 404, 500]:
        http_error.response.status_code = error_code
        assert is_alchemy_free_tier(web3, http_error) is False
    http_error.response.status_code = 400  # correct code

    # json raises error
    http_error.response.json.side_effect = ValueError("some error")
    assert is_alchemy_free_tier(web3, http_error) is False
    http_error.response.json.side_effect = None  # no json error raised

    # response json does not have error
    http_error.response.json.return_value = {"some": "other"}
    assert is_alchemy_free_tier(web3, http_error) is False

    # message is not about alchemy free tier
    not_about_free_tier = copy.deepcopy(ALCHEMY_FREE_TIER_RESPONSE_DICT)
    not_about_free_tier["error"]["message"] = "some other message"
    http_error.response.json.return_value = not_about_free_tier
    assert is_alchemy_free_tier(web3, http_error) is False

    # message does not have correct error code
    incorrect_error_code = copy.deepcopy(ALCHEMY_FREE_TIER_RESPONSE_DICT)
    incorrect_error_code["error"]["code"] = -3200
    http_error.response.json.return_value = incorrect_error_code
    assert is_alchemy_free_tier(web3, http_error) is False

    # ok - alchemy free tier
    http_error.response.json.return_value = copy.deepcopy(
        ALCHEMY_FREE_TIER_RESPONSE_DICT
    )
    assert is_alchemy_free_tier(web3, http_error) is True


def test_scan_chunk_alchemy_free_tier(mocker, get_random_checksum_address):
    web3 = mocker.Mock()
    web3.eth = mocker.Mock()
    web3.eth.get_block.return_value = {"timestamp": time.time()}
    web3.provider.endpoint_uri = (
        "https://polygon-mainnet.g.alchemy.com/v2/1234567890abcdef"
    )

    # configure for alchemy free tier error
    bad_request_response = requests.Response()
    bad_request_response.status_code = 400
    bad_request_response._content = json.dumps(ALCHEMY_FREE_TIER_RESPONSE_DICT).encode(
        "utf-8"
    )
    http_error = requests.HTTPError("my error", response=bad_request_response)

    web3.eth.get_logs.side_effect = [
        http_error,
        [],
    ]  # first call raises error, second returns empty list

    contract_address = get_random_checksum_address()
    contract = mocker.Mock()
    contract.address = contract_address
    from_block = 100
    to_block = 200
    max_retries = 3
    retry_delay = 0.1
    retry_chunk_decrease_factor = 0.5

    scanner = EventScanner(
        web3=web3,
        contract=contract,
        state=Mock(),
        events=[],
        max_request_retries=max_retries,
        request_retry_delay_seconds=retry_delay,
        chunk_size_decrease_factor=retry_chunk_decrease_factor,
    )

    get_logs_spy = mocker.spy(web3.eth, "get_logs")

    actual_end_block, events = scanner.scan_chunk(from_block, to_block)

    assert events == []
    assert get_logs_spy.call_count == 2  # first raises error, second returns empty list
    get_logs_spy.assert_called_with(
        {
            "fromBlock": from_block,
            "toBlock": from_block + ALCHEMY_FREE_TIER_MAX_CHUNK_NUM_BLOCKS,
            "address": contract_address,
            "topics": [[]],
        }
    )
    assert (
        actual_end_block == from_block + ALCHEMY_FREE_TIER_MAX_CHUNK_NUM_BLOCKS
    )  # only alchemy free tier max chunk size was scanned

    web3.eth.get_logs.side_effect = [
        http_error,
        http_error,
    ]  # first two calls raise error - alchemy free tier only retries once
    get_logs_spy.reset_mock()
    with pytest.raises(HTTPError, match="my error"):
        _ = scanner.scan_chunk(from_block, to_block)
    assert (
        get_logs_spy.call_count == 2
    )  # 2nd call raises error since alchemy free tier only retries once
    # first call
    get_logs_spy.assert_called_with(
        {
            "fromBlock": from_block,
            "toBlock": from_block + ALCHEMY_FREE_TIER_MAX_CHUNK_NUM_BLOCKS,
            "address": contract_address,
            "topics": [[]],
        }
    )


def test_scan_chunk_not_alchemy_free_tier(mocker, get_random_checksum_address):
    web3 = mocker.Mock()
    web3.eth = mocker.Mock()
    web3.eth.get_block.return_value = {"timestamp": time.time()}
    web3.provider.endpoint_uri = "https://polygon-mainnet.infura.io/v3/1234567890abcdef"

    # configure for alchemy free tier error
    bad_request_response = requests.Response()
    bad_request_response.status_code = 400
    bad_request_response._content = b"not a free tier error"
    http_error = requests.HTTPError("my error", response=bad_request_response)

    contract_address = get_random_checksum_address()
    contract = mocker.Mock()
    contract.address = contract_address
    max_retries = 3
    retry_delay = 0.1
    retry_chunk_decrease_factor = 0.5

    scanner = EventScanner(
        web3=web3,
        contract=contract,
        state=Mock(),
        events=[],
        max_request_retries=max_retries,
        request_retry_delay_seconds=retry_delay,
        chunk_size_decrease_factor=retry_chunk_decrease_factor,
    )

    get_logs_spy = mocker.spy(web3.eth, "get_logs")

    from_block = 100
    to_block = 228  # need a number here where (to_block - from_block) is a power of 2 to make the math easier

    # no decreases
    web3.eth.get_logs.side_effect = [[]]  # everything works, returns empty list
    actual_end_block, events = scanner.scan_chunk(
        from_block,
        to_block,
    )
    assert get_logs_spy.call_count == 1
    assert events == []
    assert actual_end_block == to_block
    get_logs_spy.assert_called_with(
        {
            "fromBlock": from_block,
            "toBlock": to_block,
            "address": contract_address,
            "topics": [[]],
        }
    )

    # chunk size decreased by factor 1x
    web3.eth.get_logs.side_effect = [
        http_error,
        [],
    ]  # first call raises error, second returns empty list
    get_logs_spy.reset_mock()
    actual_end_block, events = scanner.scan_chunk(
        from_block,
        to_block,
    )
    assert get_logs_spy.call_count == 2
    assert events == []
    assert actual_end_block == from_block + math.floor(
        (to_block - from_block) * retry_chunk_decrease_factor
    )  # chunk size decreased once
    get_logs_spy.assert_called_with(
        {
            "fromBlock": from_block,
            "toBlock": actual_end_block,
            "address": contract_address,
            "topics": [[]],
        }
    )

    # chunk size decreased by factor 2x
    web3.eth.get_logs.side_effect = [
        http_error,
        http_error,
        [],
    ]  # first two calls raises error, third returns empty list
    get_logs_spy.reset_mock()
    actual_end_block, events = scanner.scan_chunk(
        from_block,
        to_block,
    )
    assert get_logs_spy.call_count == 3
    assert events == []
    assert actual_end_block == from_block + math.floor(
        (to_block - from_block)
        * retry_chunk_decrease_factor
        * retry_chunk_decrease_factor
    )  # chunk size decreased twice
    get_logs_spy.assert_called_with(
        {
            "fromBlock": from_block,
            "toBlock": actual_end_block,
            "address": contract_address,
            "topics": [[]],
        }
    )

    # >= max retries - so only two decreases
    web3.eth.get_logs.side_effect = [
        http_error,
        http_error,
        http_error,
    ]  # first three calls raises error which exceeds number of retries
    get_logs_spy.reset_mock()
    with pytest.raises(HTTPError, match="my error"):
        _ = scanner.scan_chunk(
            from_block,
            to_block,
        )
    assert get_logs_spy.call_count == 3  # first raises error, second returns empty list
    actual_end_block = from_block + math.floor(
        (to_block - from_block)
        * retry_chunk_decrease_factor
        * retry_chunk_decrease_factor
    )
    get_logs_spy.assert_called_with(
        {
            "fromBlock": from_block,
            "toBlock": actual_end_block,
            "address": contract_address,
            "topics": [[]],
        }
    )

    # chunk size decrease 2x - BUT final decrease would go below from_block, so should stop at from_block
    to_block = (
        from_block + (MIN_CHUNK_NUM_BLOCKS - 2) * 2**2
    )  # 2 decreases will go below MIN_CHUNK_NUM_BLOCKS
    web3.eth.get_logs.side_effect = [
        http_error,
        http_error,
        [],
    ]  # first two calls raise exception but last call uses MIN_CHUNK_NUM_BLOCKS instead of lower value from calc
    get_logs_spy.reset_mock()
    actual_end_block, events = scanner.scan_chunk(
        from_block,
        to_block,
    )
    assert get_logs_spy.call_count == 3
    assert events == []
    assert actual_end_block == from_block + MIN_CHUNK_NUM_BLOCKS
    get_logs_spy.assert_called_with(
        {
            "fromBlock": from_block,
            "toBlock": actual_end_block,
            "address": contract_address,
            "topics": [[]],
        }
    )


def test_scan_chunk_connection_error(mocker, get_random_checksum_address):
    web3 = mocker.Mock()
    web3.eth = mocker.Mock()
    web3.eth.get_block.return_value = {"timestamp": time.time()}
    web3.provider.endpoint_uri = (
        "https://polygon-mainnet.g.alchemy.com/v2/1234567890abcdef"
    )

    # configure for endpoint's server error
    bad_request_response = requests.Response()
    bad_request_response.status_code = 502  # Bad Gateway error
    http_error = requests.HTTPError("my error", response=bad_request_response)

    max_retries = 10

    web3.eth.get_logs.side_effect = http_error
    contract_address = get_random_checksum_address()
    contract = mocker.Mock()
    contract.address = contract_address
    from_block = 100
    to_block = 200
    retry_delay = 0.1
    retry_chunk_decrease_factor = 0.5

    scanner = EventScanner(
        web3=web3,
        contract=contract,
        state=Mock(),
        events=[],
        max_request_retries=max_retries,
        request_retry_delay_seconds=retry_delay,
        chunk_size_decrease_factor=retry_chunk_decrease_factor,
    )

    get_logs_spy = mocker.spy(web3.eth, "get_logs")

    with pytest.raises(HTTPError, match="my error"):
        _ = scanner.scan_chunk(
            from_block,
            to_block,
        )
    assert get_logs_spy.call_count == max_retries


def test_scan_use_reduced_chunk_size_for_remaining_chunks_after_reduction(
    mocker, get_random_checksum_address
):
    web3 = mocker.Mock()
    web3.eth = mocker.Mock()
    web3.eth.get_block.return_value = {"timestamp": time.time()}
    web3.provider.endpoint_uri = (
        "https://polygon-mainnet.g.alchemy.com/v2/1234567890abcdef"
    )

    contract_address = get_random_checksum_address()
    contract = mocker.Mock()
    contract.address = contract_address
    max_retries = 3
    retry_delay = 0.1

    # configure for endpoint's server error
    bad_request_response = requests.Response()
    bad_request_response.status_code = 502  # Bad Gateway error
    http_error = requests.HTTPError("my error", response=bad_request_response)

    num_failures = max_retries - 1

    call_count = {"n": 0}

    def mock_get_logs(params):
        # first two calls raise error, subsequent calls return empty list
        call_count["n"] += 1
        if call_count["n"] <= num_failures:
            raise http_error
        else:
            return []

    web3.eth.get_logs.side_effect = mock_get_logs

    # need numbers here that work well together i.e. produce whole number of calls after reductions
    from_block = 100
    to_block = 1000
    start_chunk_size = 200
    retry_chunk_decrease_factor = 0.5

    scanner = EventScanner(
        web3=web3,
        contract=contract,
        state=Mock(),
        events=[],
        max_request_retries=max_retries,
        request_retry_delay_seconds=retry_delay,
        chunk_size_decrease_factor=retry_chunk_decrease_factor,
    )

    get_logs_spy = mocker.spy(web3.eth, "get_logs")

    scanner.scan(from_block, to_block, start_chunk_size=start_chunk_size)
    num_successes = (to_block - from_block) // (
        start_chunk_size * (retry_chunk_decrease_factor**num_failures)
    )
    assert get_logs_spy.call_count == (num_failures + num_successes)
