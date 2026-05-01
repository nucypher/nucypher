"""
Credit to the original authors for making this code example incorporated into this module found here:
https://web3py.readthedocs.io/en/stable/filters.html#example-code

A stateful event scanner for Ethereum-based blockchains using Web3.py.

With the stateful mechanism, you can do one batch scan or incremental scans,
where events are added wherever the scanner left off.
"""

import csv
import datetime
import json
import math
import os
import time
from abc import ABC, abstractmethod
from collections import OrderedDict
from http import HTTPStatus
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Tuple

import maya
from eth_abi.codec import ABICodec
from eth_typing import ChecksumAddress
from eth_utils import encode_hex
from eth_utils.abi import event_abi_to_log_topic
from requests import HTTPError
from web3 import Web3
from web3._utils.events import get_event_data
from web3.contract.contract import Contract, ContractEvent
from web3.datastructures import AttributeDict
from web3.exceptions import BlockNotFound
from web3.types import BlockIdentifier

from nucypher.blockchain.eth.agents import EthereumContractAgent
from nucypher.blockchain.eth.events import EventRecord
from nucypher.config.constants import (
    NUCYPHER_ENVVAR_ALCHEMY_FREE_TIER_MAX_CHUNK_NUM_BLOCKS,
    NUCYPHER_ENVVAR_MAX_CHUNK_NUM_BLOCKS,
    NUCYPHER_ENVVAR_MIN_CHUNK_NUM_BLOCKS,
)
from nucypher.utilities.logging import Logger

ALCHEMY_FREE_TIER_MAX_CHUNK_NUM_BLOCKS = int(
    os.environ.get(NUCYPHER_ENVVAR_ALCHEMY_FREE_TIER_MAX_CHUNK_NUM_BLOCKS, 9)
)  # they say 10, but it's really < 10
# some reasonable minimum below alchemy free tier; we don't actually want this too low
MIN_CHUNK_NUM_BLOCKS = int(os.environ.get(NUCYPHER_ENVVAR_MIN_CHUNK_NUM_BLOCKS, 9))
MAX_CHUNK_NUM_BLOCKS = int(os.environ.get(NUCYPHER_ENVVAR_MAX_CHUNK_NUM_BLOCKS, 1000))


def generate_events_csv_filepath(contract_name: str, event_name: str) -> Path:
    return Path(
        f"{contract_name}_{event_name}_{maya.now().datetime().strftime('%Y-%m-%d_%H-%M-%S')}.csv"
    )


def write_events_to_csv_file(
    csv_file: Path,
    agent: EthereumContractAgent,
    event_name: str,
    argument_filters: Dict = None,
    from_block: Optional[BlockIdentifier] = 0,
    to_block: Optional[BlockIdentifier] = "latest",
) -> bool:
    """
    Write events to csv file.
    :return: True if data written to file, False if there was no event data to write
    """
    event_type = agent.contract.events[event_name]
    entries = event_type.get_logs(
        fromBlock=from_block, toBlock=to_block, argument_filters=argument_filters
    )
    if not entries:
        return False

    with open(csv_file, mode="w") as events_file:
        events_writer = None
        for event_record in entries:
            event_record = EventRecord(event_record)
            event_row = OrderedDict()
            event_row["event_name"] = event_name
            event_row["block_number"] = event_record.block_number
            event_row["unix_timestamp"] = event_record.timestamp
            event_row["date"] = maya.MayaDT(event_record.timestamp).iso8601()
            event_row.update(dict(event_record.args.items()))
            if events_writer is None:
                events_writer = csv.DictWriter(events_file, fieldnames=event_row.keys())
                events_writer.writeheader()
            events_writer.writerow(event_row)
    return True


def is_alchemy_free_tier(web3: Web3, http_error: HTTPError) -> bool:
    try:
        # very specific error case
        rpc_response = http_error.response.json()
        is_http_400 = http_error.response.status_code == HTTPStatus.BAD_REQUEST
        is_alchemy_provider = "alchemy" in getattr(web3.provider, "endpoint_uri", "")
        is_rpc_response_error = "error" in rpc_response
        is_alchemy_free_tier_error = "Free tier" in rpc_response["error"]["message"]
        is_rpc_bad_request = rpc_response["error"]["code"] == -32600

        return all(
            [
                is_http_400,
                is_alchemy_provider,
                is_rpc_response_error,
                is_alchemy_free_tier_error,
                is_rpc_bad_request,
            ]
        )
    except (ValueError, KeyError):
        return False


logger = Logger("events")


class EventScannerState(ABC):
    """
    Application state that remembers what blocks we have scanned in the case of crash.
    """

    @abstractmethod
    def get_last_scanned_block(self) -> int:
        """Number of the last block we have scanned on the previous cycle.

        :return: 0 if no blocks scanned yet
        """

    @abstractmethod
    def start_chunk(self, block_number: int):
        """Scanner is about to ask data of multiple blocks over JSON-RPC.

        Start a database session if needed.
        """

    @abstractmethod
    def end_chunk(self, block_number: int):
        """Scanner finished a number of blocks.

        Persistent any data in your state now.
        """

    @abstractmethod
    def process_event(
        self, block_when: datetime.datetime, event: AttributeDict
    ) -> object:
        """Process incoming events.

        This function takes raw events from Web3, transforms them to your application internal
        format, then saves them in a database or some other state.

        :param block_when: When this block was mined

        :param event: Symbolic dictionary of the event data

        :return: Internal state structure that is the result of event tranformation.
        """

    @abstractmethod
    def delete_data(self, since_block: int) -> int:
        """Delete any data since this block was scanned.

        Purges any potential minor reorg data.
        """


class EventScanner:
    """Scan blockchain for events and try not to abuse JSON-RPC API too much.

    Can be used for real-time scans, as it detects minor chain reorganisation and rescans.
    Unlike the easy web3.contract.Contract, this scanner can scan events from multiple contracts at once.
    For example, you can get all transfers from all tokens in the same scan.

    You *should* disable the default `http_retry_request_middleware` on your provider for Web3,
    because it cannot correctly throttle and decrease the `eth_get_logs` block number range.
    """

    DEFAULT_CHUNK_SIZE_INCREASE_FACTOR = 2.0
    DEFAULT_CHUNK_SIZE_DECREASE_FACTOR = 1 / DEFAULT_CHUNK_SIZE_INCREASE_FACTOR
    DEFAULT_MAX_RETRIES = 3
    DEFAULT_RETRY_DELAY_SECONDS = 3.0

    def __init__(
        self,
        web3: Web3,
        contract: Contract,
        state: EventScannerState,
        events: List[ContractEvent],
        min_chunk_scan_size: int = MIN_CHUNK_NUM_BLOCKS,
        max_chunk_scan_size: int = MAX_CHUNK_NUM_BLOCKS,
        max_request_retries: int = DEFAULT_MAX_RETRIES,
        request_retry_delay_seconds: float = DEFAULT_RETRY_DELAY_SECONDS,
        chain_reorg_rescan_window: int = 0,
        chunk_size_decrease_factor: float = DEFAULT_CHUNK_SIZE_DECREASE_FACTOR,
        chunk_size_increase_factor: float = DEFAULT_CHUNK_SIZE_INCREASE_FACTOR,
    ):
        """
        :param web3: Web3 instance
        :param contract: Contract
        :param state: EventScannerState instance that stores what blocks we have scanned
        :param events: List of web3 Event we scan
        :param min_chunk_scan_size: Minimum number of blocks we try to fetch over JSON-RPC at once
        :param max_chunk_scan_size: JSON-RPC API limit in the number of blocks we query
        :param max_request_retries: retry attempts for a failed JSON-RPC request
        :param request_retry_delay_seconds: Seconds to wait before retrying a failed JSON-RPC request
        :param chain_reorg_rescan_window: Number of blocks to rescan in case of chain reorganization (to prevent missed blocks)
        :param chunk_size_decrease_factor: Factor we decrease the chunk size by if there are failures before retrying
        :param chunk_size_increase_factor: Factor we increase the chunk size by if no events are found
        """

        self.logger = Logger(self.__class__.__name__)
        self.contract = contract
        self.web3 = web3
        self.state = state
        self.events = events

        # Our JSON-RPC throttling parameters
        self.min_scan_chunk_size = min_chunk_scan_size
        if self.min_scan_chunk_size < MIN_CHUNK_NUM_BLOCKS:
            raise ValueError(
                f"Min scan chunk size must be at least {MIN_CHUNK_NUM_BLOCKS}"
            )

        self.max_scan_chunk_size = max_chunk_scan_size
        if self.max_scan_chunk_size > MAX_CHUNK_NUM_BLOCKS:
            raise ValueError(
                f"Max scan chunk size must be at most {MAX_CHUNK_NUM_BLOCKS}"
            )

        self.max_request_retries = max_request_retries
        self.request_retry_seconds = request_retry_delay_seconds
        self.chain_reorg_rescan_window = chain_reorg_rescan_window

        # Factor how fast we increase the chunk size if results are found
        # (slow down scan after starting to get hits)
        if chunk_size_decrease_factor <= 0 or chunk_size_decrease_factor >= 1:
            raise ValueError(
                "Chunk size decrease factor must be between 0 and 1 (exclusive)"
            )
        self.chunk_size_decrease_factor = chunk_size_decrease_factor

        # Factor how fast we increase chunk size if no results found
        if chunk_size_increase_factor <= 1:
            raise ValueError("Chunk size increase factor must be greater than 1")
        self.chunk_size_increase_factor = chunk_size_increase_factor

    @property
    def address(self):
        return self.contract.address

    def get_block_timestamp(self, block_num) -> datetime.datetime:
        """Get Ethereum block timestamp"""
        try:
            block_info = self.web3.eth.get_block(block_num)
        except BlockNotFound:
            # Block was not mined yet,
            # minor chain reorganisation?
            return None
        last_time = block_info["timestamp"]
        return datetime.datetime.fromtimestamp(last_time, tz=datetime.timezone.utc)

    def get_suggested_scan_start_block(self):
        """Get where we should start to scan for new token events.

        If there are no prior scans, start from block 1.
        Otherwise, start from the last end block minus chain reorg blocks.
        We rescan some previous blocks in the case there were forks to avoid
        misaccounting due to minor single block works (happens once in a hour in Ethereum).
        """

        end_block = self.get_last_scanned_block()
        if end_block:
            return max(1, end_block - self.chain_reorg_rescan_window)
        return 1

    def get_suggested_scan_end_block(self):
        """Get the last mined block on Ethereum chain we are following."""

        # Do not scan all the way to the final block, as this
        # block might not be mined yet
        return self.web3.eth.block_number - 1

    def get_last_scanned_block(self) -> int:
        return self.state.get_last_scanned_block()

    def delete_potentially_forked_block_data(self, after_block: int):
        """Purge old data in the case of blockchain reorganisation."""
        self.state.delete_data(after_block)

    def scan_chunk(self, start_block, end_block) -> Tuple[int, list]:
        """Read and process events between to block numbers.
        :return: tuple(actual end block number, processed events)
        """

        block_timestamps = {}
        get_block_timestamp = self.get_block_timestamp

        # Cache block timestamps to reduce some RPC overhead
        # Real solution might include smarter models around block
        def get_block_when(block_num) -> datetime.datetime:
            if block_num not in block_timestamps:
                block_timestamps[block_num] = get_block_timestamp(block_num)
            return block_timestamps[block_num]

        all_processed = []
        events, actual_end_block = _fetch_events_for_contract(
            web3=self.web3,
            contract=self.contract,
            events=self.events,
            from_block=start_block,
            to_block=end_block,
            max_retries=self.max_request_retries,
            retry_delay=self.request_retry_seconds,
            retry_chunk_decrease_factor=self.chunk_size_decrease_factor,
            logger=self.logger,
        )

        for evt in events:
            processed = self.process_event(event=evt, get_block_when=get_block_when)
            all_processed.append(processed)

        return actual_end_block, all_processed

    def process_event(
        self, event: AttributeDict, get_block_when: Callable[[int], datetime.datetime]
    ):
        """Process events and update internal state"""
        idx = event[
            "logIndex"
        ]  # Integer of the log index position in the block, null when its pending

        # We cannot avoid minor chain reorganisations, but
        # at least we must avoid blocks that are not mined yet
        assert idx is not None, "Somehow tried to scan a pending block"

        block_number = event["blockNumber"]

        # Get UTC time when this event happened (block mined timestamp)
        # from our in-memory cache
        block_when = get_block_when(block_number)

        self.logger.debug(
            f"Processing event {event['event']}, block: {block_number}",
        )
        processed = self.state.process_event(block_when, event)
        return processed

    def estimate_next_chunk_size(self, current_chunk_size: int, event_found_count: int):
        """Try to figure out optimal chunk size

        Our scanner might need to scan the whole blockchain for all events

        * We want to minimize API calls over empty blocks

        * We want to make sure that one scan chunk does not try to process too many entries once, as we try to control commit buffer size and potentially asynchronous busy loop

        * Do not overload node serving JSON-RPC API by asking data for too many events at a time

        Currently, Ethereum JSON-API does not have an API to tell when a first event occurred in a blockchain
        and our heuristics try to accelerate block fetching (chunk size) until we see the first event.

        These heuristics exponentially increase the scan chunk size depending on if we are seeing events or not.
        When any transfers are encountered, we are back to scanning only a few blocks at a time.
        It does not make sense to do a full chain scan starting from block 1, doing one JSON-RPC call per 20 blocks.
        """

        if event_found_count > 0:
            # When we encounter first events, reset the chunk size window
            current_chunk_size = self.min_scan_chunk_size
        else:
            current_chunk_size *= self.chunk_size_increase_factor

        current_chunk_size = max(self.min_scan_chunk_size, current_chunk_size)
        current_chunk_size = min(self.max_scan_chunk_size, current_chunk_size)
        return int(current_chunk_size)

    def scan(
        self, start_block, end_block, start_chunk_size: Optional[int] = None
    ) -> Tuple[list, int]:
        """Perform a scan for events.

        :param start_block: The first block included in the scan

        :param end_block: The last block included in the scan

        :param start_chunk_size: How many blocks we try to fetch over JSON-RPC on the first attempt; min chunk size if not specified

        :return: [All processed events, number of chunks used]
        """

        if start_block > end_block:
            raise ValueError(
                f"Start block ({start_block}) is greater than end block ({end_block})"
            )

        current_block = start_block

        # Scan in chunks, commit between
        chunk_size = start_chunk_size or self.min_scan_chunk_size
        last_scan_duration = last_logs_found = 0
        total_chunks_scanned = 0

        # All processed entries we got on this scan cycle
        all_processed = []
        chunk_size_decreased = False

        while current_block <= end_block:
            self.state.start_chunk(current_block)

            estimated_end_block = min(
                current_block + chunk_size, end_block
            )  # either entire full chunk, or we are at the last chunk
            self.logger.debug(
                f"Scanning for blocks: {current_block} - {estimated_end_block}, chunk size {chunk_size}, last chunk scan took {last_scan_duration}, last logs found {last_logs_found}"
            )

            start = time.time()
            actual_end_block, new_entries = self.scan_chunk(
                current_block, estimated_end_block
            )

            # Where does our current chunk scan ends - are we out of chain yet?
            current_end = actual_end_block

            last_scan_duration = time.time() - start
            all_processed += new_entries

            if actual_end_block < estimated_end_block:
                # original chunk size was too large; use what worked previously
                chunk_size = actual_end_block - current_block
                chunk_size_decreased = True
            elif not chunk_size_decreased:
                # Try to guess how many blocks to fetch over `eth_get_logs` API next time
                chunk_size = self.estimate_next_chunk_size(chunk_size, len(new_entries))

            # Set where the next chunk starts
            current_block = current_end + 1
            total_chunks_scanned += 1
            self.state.end_chunk(current_end)

        return all_processed, total_chunks_scanned


def _get_logs(
    web3: Web3,
    contract_address: ChecksumAddress,
    topics: List,
    from_block: int,
    to_block: int,
    max_retries: int,
    retry_delay: float,
    retry_chunk_decrease_factor: float,
    logger: Logger,
) -> Tuple[Iterable, int]:
    event_filter_params = {
        "address": contract_address,
        "topics": [topics],
        "fromBlock": from_block,
    }

    to_block_to_use = to_block
    # Call JSON-RPC API on your Ethereum node.
    # get_logs() returns raw AttributedDict entries
    for attempt in range(max_retries):
        try:
            # dynamically update toBlock value based on retries etc.
            event_filter_params["toBlock"] = to_block_to_use
            logger.debug(
                f"Querying eth_getLogs with the following parameters: {event_filter_params}"
            )
            logs = web3.eth.get_logs(event_filter_params)
            return logs, to_block_to_use
        except HTTPError as http_error:
            logger.warn(
                f"eth_getLogs API call failed for range {from_block} - {to_block_to_use} ({to_block_to_use - from_block} blocks) on attempt {attempt + 1}/{max_retries}: {http_error}"
            )

            # Assumption: the reason for http error is fetching too many blocks
            if attempt >= max_retries - 1:
                # no more retries left
                logger.warn("eth_getLogs API call failed, no more retries left")
                raise http_error

            # update to_block since range could be problematic; don't go lower than min blocks
            if is_alchemy_free_tier(web3, http_error):
                if attempt > 0:
                    # we already reduced the chunk size for Alchemy, but it did not help
                    logger.warn(
                        "Alchemy free tier reduction was unsuccessful, retrying will not help"
                    )
                    raise http_error

                # Update to_block and directly set range since alchemy free tier
                to_block_to_use = (
                    from_block + ALCHEMY_FREE_TIER_MAX_CHUNK_NUM_BLOCKS
                )  # alchemy free tier max
                logger.warn(
                    f"Alchemy free tier detected. Retrying with range {from_block} - {to_block_to_use} ({to_block_to_use - from_block} blocks)"
                )
            else:
                # reducing the chunk size by a factor
                # (we assume the original chunk size was too large)
                to_block_to_use = from_block + max(
                    math.floor(
                        (to_block_to_use - from_block) * retry_chunk_decrease_factor
                    ),
                    MIN_CHUNK_NUM_BLOCKS,
                )
                logger.warn(
                    f"Reducing range to {from_block} - {to_block_to_use} ({to_block_to_use - from_block} blocks) and retrying in {retry_delay}s"
                )
                # pause before retrying
                time.sleep(retry_delay)


def _fetch_events_for_contract(
    web3,
    contract,
    events,
    from_block: int,
    to_block: int,
    max_retries: int,
    retry_delay: float,
    retry_chunk_decrease_factor: float,
    logger: Logger,
) -> Tuple[Iterable, int]:
    """Get events using eth_getLogs API.

    This method is detached from any contract instance.

    This is a stateless method, as opposed to createFilter.
    It can be safely called against nodes which do not provide `eth_newFilter` API, like Infura.
    """

    if from_block is None:
        raise TypeError("Missing mandatory keyword argument to get_logs: fromBlock")

    # Depending on the Solidity version used to compile
    # the contract that uses the ABI,
    # it might have Solidity ABI encoding v1 or v2.
    # We just assume the default that you set on Web3 object here.
    # More information here https://eth-abi.readthedocs.io/en/latest/index.html
    codec: ABICodec = web3.codec

    topics = set()
    event_topics_to_abis = {}
    for event_type in events:
        event_abi = event_type._get_event_abi()
        event_topic = encode_hex(event_abi_to_log_topic(event_abi))  # type: ignore
        topics.add(event_topic)
        event_topics_to_abis[event_topic] = event_abi

    # Call JSON-RPC API on your Ethereum node.
    logs, actual_end_block = _get_logs(
        web3,
        contract.address,
        list(topics),
        from_block,
        to_block,
        max_retries,
        retry_delay,
        retry_chunk_decrease_factor,
        logger,
    )

    # Convert raw binary data to Python proxy objects as described by ABI
    all_events = []
    for log in logs:
        topics = log["topics"]
        event_abi = event_topics_to_abis.get(
            encode_hex(topics[0])
        )  # first topic is always event signature
        if not event_abi:
            # don't expect to get here since the topics were limited to the events specified
            raise ValueError(
                f"Unable to obtain event abi for received event with signature {topics[0]}"
            )

        # Convert raw JSON-RPC log result to human-readable event by using ABI data
        # More information how processLog works here
        # https://github.com/ethereum/web3.py/blob/fbaf1ad11b0c7fac09ba34baff2c256cffe0a148/web3/_utils/events.py#L200
        evt = get_event_data(codec, event_abi, log)
        # Note: This was originally yield,
        # but deferring the timeout exception caused the throttle logic not to work
        all_events.append(evt)
    return all_events, actual_end_block


class JSONifiedState(EventScannerState):
    """Store the state of scanned blocks and all events.

    All state is an in-memory dict.
    Simple load/store massive JSON on start up.
    """

    def __init__(self, persistent=True, fname="eventscanner.json"):
        self.state = None
        self.fname = fname
        # How many second ago we saved the JSON file
        self.last_save = 0
        self.persistent = persistent

    def reset(self):
        """Create initial state of nothing scanned."""
        self.state = {
            "last_scanned_block": 0,
            "blocks": {},
        }

    def restore(self):
        """Restore the last scan state from a file."""
        if not self.persistent:
            self.reset()
            return

        try:
            self.state = json.load(open(self.fname, "rt"))
            print(
                f"Restored the state, previously {self.state['last_scanned_block']} blocks have been scanned"
            )
        except (IOError, json.decoder.JSONDecodeError):
            print("State starting from scratch")
            self.reset()

    def save(self):
        """Save everything we have scanned so far in a file."""
        if self.persistent:
            with open(self.fname, "wt") as f:
                json.dump(self.state, f)
        self.last_save = time.time()

    #
    # EventScannerState methods implemented below
    #

    def get_last_scanned_block(self):
        """The number of the last block we have stored."""
        return self.state["last_scanned_block"]

    def delete_data(self, since_block):
        """Remove potentially reorganised blocks from the scan data."""
        for block_num in range(since_block, self.get_last_scanned_block()):
            if block_num in self.state["blocks"]:
                del self.state["blocks"][block_num]

    def start_chunk(self, block_number):
        pass  # TODO any reason this is not implemented?

    def end_chunk(self, block_number):
        """Save at the end of each block, so we can resume in the case of a crash or CTRL+C"""
        # Next time the scanner is started we will resume from this block
        self.state["last_scanned_block"] = block_number

        # Save the database file for every minute
        if self.persistent and (time.time() - self.last_save > 60):
            self.save()

    def process_event(self, block_when: datetime.datetime, event: AttributeDict) -> str:
        """Record a ERC-20 event_record in our database."""
        # Events are keyed by their transaction hash and log index
        # One transaction may contain multiple events
        # and each one of those gets their own log index

        event_name = event.event  # "Transfer"
        log_index = event.logIndex  # Log index within the block
        transaction_index = event.transactionIndex  # Transaction index within the block
        txhash = event.transactionHash.hex()  # Transaction hash
        block_number = event.blockNumber

        # Convert event to our internal format
        event_record = {
            "event": event_name,
            "blockTimestamp": block_when.timestamp(),
            "logIndex": log_index,
            "transactionIndex": transaction_index,
            "txhash": txhash,
            "blockNumber": block_number,
        }

        # Create empty dict as the block that contains all transactions by txhash
        if block_number not in self.state["blocks"]:
            self.state["blocks"][block_number] = {}

        block = self.state["blocks"][block_number]
        if txhash not in block:
            # We have not yet recorded any transfers in this transaction
            # (One transaction may contain multiple events if executed by a smart contract).
            # Create a tx entry that contains all events by a log index
            self.state["blocks"][block_number][txhash] = {}

        # Record event in our database
        if log_index in self.state["blocks"][block_number][txhash]:
            return None  # We have already recorded this event
        self.state["blocks"][block_number][txhash][log_index] = event_record

        # Return a pointer that allows us to look up this event later if needed
        return f"{block_number}-{txhash}-{log_index}"
