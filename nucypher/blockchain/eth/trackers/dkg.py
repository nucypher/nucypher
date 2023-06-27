import os
import time
from typing import Callable, List, Optional, Tuple, Type, Union

from twisted.internet import threads
from web3.contract.contract import ContractEvent
from web3.datastructures import AttributeDict

from nucypher.blockchain.eth import actors
from nucypher.policy.conditions.utils import camel_case_to_snake
from nucypher.utilities.events import EventScanner, JSONifiedState
from nucypher.utilities.logging import Logger
from nucypher.utilities.task import SimpleTask


class EventActuator(EventScanner):
    """Act on events that are found by the scanner."""

    def __init__(
        self,
        hooks: List[Callable],
        clear: bool = True,
        chain_reorg_rescan_window: int = 10,
        *args,
        **kwargs,
    ):
        self.log = Logger("EventActuator")
        if clear and os.path.exists(JSONifiedState.STATE_FILENAME):
            os.remove(JSONifiedState.STATE_FILENAME)
        self.hooks = hooks
        super().__init__(
            chain_reorg_rescan_window=chain_reorg_rescan_window, *args, **kwargs
        )

    def process_event(self, event, get_block_when):
        for hook in self.hooks:
            try:
                hook(event, get_block_when)
            except Exception as e:
                self.log.warn("Error during event hook: {}".format(e))
                raise
        super().process_event(event, get_block_when)


class EventScannerTask(SimpleTask):
    """Task that runs the event scanner in a looping call."""

    INTERVAL = 20  # seconds

    def __init__(self, scanner: Callable, *args, **kwargs):
        self.scanner = scanner
        super().__init__(*args, **kwargs)

    def run(self):
        self.scanner()

    def handle_errors(self, *args, **kwargs):
        self.log.warn("Error during ritual event scanning: {}".format(args[0].getTraceback()))
        if not self._task.running:
            self.log.warn("Restarting event scanner task!")
            self.start(now=True)


class ActiveRitualTracker:

    MAX_CHUNK_SIZE = 10000

    def __init__(
        self,
        ritualist: "actors.Ritualist",
        persistent: bool = False,  # TODO: use persistent storage?
    ):
        self.log = Logger("RitualTracker")

        self.ritualist = ritualist
        self.coordinator_agent = ritualist.coordinator_agent

        self.rituals = dict()  # TODO: use persistent storage?

        # Restore/create persistent event scanner state
        self.persistent = persistent
        self.state = JSONifiedState(persistent=persistent)
        self.state.restore()

        # Map events to handlers
        self.actions = {
            self.contract.events.StartRitual: self.ritualist.perform_round_1,
            self.contract.events.StartAggregationRound: self.ritualist.perform_round_2,
        }
        self.events = list(self.actions)

        # TODO: Remove the default JSON-RPC retry middleware
        # as it correctly cannot handle eth_getLogs block range throttle down.
        # self.web3.middleware_onion.remove(http_retry_request_middleware)

        self.scanner = EventActuator(
            hooks=[self._handle_ritual_event],
            web3=self.web3,
            state=self.state,
            contract=self.contract,
            events=self.events,
            filters={"address": self.contract.address},
            # How many maximum blocks at the time we request from JSON-RPC,
            # and we are unlikely to exceed the response size limit of the JSON-RPC server
            max_chunk_scan_size=self.MAX_CHUNK_SIZE
        )

        self.task = EventScannerTask(scanner=self.scan)
        self.active_tasks = set()
        self.refresh()

    @property
    def provider(self):
        return self.web3.provider

    @property
    def web3(self):
        return self.coordinator_agent.blockchain.w3

    @property
    def contract(self):
        return self.coordinator_agent.contract

    # TODO: should sample_window_size be additionally configurable/chain-dependent?
    def _get_first_scan_start_block_number(self, sample_window_size: int = 100) -> int:
        """
        Returns the block number to start scanning for events from.
        """
        w3 = self.web3
        timeout = self.coordinator_agent.get_timeout()

        latest_block = w3.eth.get_block('latest')
        if latest_block.number == 0:
            return 0

        # get average block time
        sample_block_number = latest_block.number - sample_window_size
        if sample_block_number <= 0:
            return 0
        base_block = w3.eth.get_block(sample_block_number)
        average_block_time = (
            latest_block.timestamp - base_block.timestamp
        ) / sample_window_size

        number_of_blocks_in_the_past = int(timeout / average_block_time)

        expected_start_block = w3.eth.get_block(
            max(0, latest_block.number - number_of_blocks_in_the_past)
        )
        target_timestamp = latest_block.timestamp - timeout

        # Keep looking back until we find the last block before the target timestamp
        while (
            expected_start_block.number > 0
            and expected_start_block.timestamp > target_timestamp
        ):
            expected_start_block = w3.eth.get_block(expected_start_block.number - 1)

        # if non-zero block found - return the block before
        return expected_start_block.number - 1 if expected_start_block.number > 0 else 0

    def get_ritual(self, ritual_id: int, with_participants: bool = True):
        """Get a ritual from the blockchain."""
        ritual = self.coordinator_agent.get_ritual(
            ritual_id=ritual_id, with_participants=with_participants
        )
        return ritual

    def refresh(self, fetch_rituals: Optional[List[int]] = None, all: bool = False):
        """Refresh the list of rituals with the latest data from the blockchain"""
        ritual_ids = self.rituals.keys()
        if all:
            ritual_ids = range(self.coordinator_agent.number_of_rituals() - 1)
        elif fetch_rituals:
            ritual_ids = [*fetch_rituals, *ritual_ids]
        for rid in ritual_ids:
            ritual = self.get_ritual(ritual_id=rid)
            self.track_ritual(ritual_id=rid, ritual=ritual)
        
    def start(self):
        """Start the event scanner task."""
        return self.task.start()

    def stop(self):
        """Stop the event scanner task."""
        return self.task.stop()

    def __action_required(self, event_type: Type[ContractEvent], block_number: int, ritual_id: int):
        """Check if an action is required for a given event."""
        if (event_type, ritual_id) in self.active_tasks:
            self.log.debug(
                f"Already tracking {event_type} for ritual {ritual_id} from block #{block_number}"
            )
            return False
        return True

    def _filter(self, event) -> Tuple[AttributeDict, Union[None, Type[ContractEvent]]]:
        """Secondary filtration of events."""
        name, args = event.event, event.args
        event_type = getattr(self.contract.events, event.event)
        if hasattr(args, "participants"):
            # Filter out events that are not for me
            if self.ritualist.checksum_address not in args.participants:
                self.log.debug(f"Event {name} is not for me, skipping")
                return None, event_type
        if not self.__action_required(event_type, event.blockNumber, args.ritualId):
            return None, event_type
        return event, event_type

    def __execute_round(self, event_type, timestamp: int, ritual_id: int, defer: bool = False, **kwargs):
        """Execute a round of a ritual asynchronously."""
        def task():
            self.actions[event_type](timestamp=timestamp, ritual_id=ritual_id, **kwargs)
        if defer:
            d = threads.deferToThread(task)
            d.addErrback(self.task.handle_errors)
            d.addCallback(self.refresh)
            return d
        else:
            return task()

    def _handle_ritual_event(self, event: AttributeDict, get_block_when: Callable):
        # Refresh the list of rituals to make sure we have the latest data
        self.refresh()
        # Filter out events that are not for us
        event, event_type = self._filter(event)
        if not event:
            return
        # NOTE: this format splits on *capital letters* and converts to snake case
        #  so "StartConfirmationRound" becomes "start_confirmation_round"
        #  do not use abbreviations in event names (e.g. "DKG" -> "d_k_g")
        formatted_kwargs = {camel_case_to_snake(k): v for k, v in event.args.items()}
        timestamp = int(get_block_when(event.blockNumber).timestamp())
        ritual_id = event.args.ritualId
        ritual = self.get_ritual(ritual_id=ritual_id)
        self.add_ritual(ritual_id=ritual_id, ritual=ritual)
        self.active_tasks.add((event_type, ritual_id))
        d = self.__execute_round(event_type=event_type, timestamp=timestamp, **formatted_kwargs)
        return d

    def __scan(self, start_block, end_block, account):
        # Run the scan
        self.log.debug(f"({account[:8]}) Scanning events in block range {start_block} - {end_block}")
        start = time.time()
        result, total_chunks_scanned = self.scanner.scan(start_block, end_block)
        if self.persistent:
            self.state.save()
        duration = time.time() - start
        self.log.debug(f"Scanned total of {len(result)} events, in {duration} seconds, "
                       f"total {total_chunks_scanned} chunk scans performed")

    def scan(self):
        """
        Assume we might have scanned the blocks all the way to the last Ethereum block
        that mined a few seconds before the previous scan run ended.
        Because there might have been a minor Ethereum chain reorganisations since the last scan ended,
        we need to discard the last few blocks from the previous scan results.
        """
        self.scanner.delete_potentially_forked_block_data(
            self.state.get_last_scanned_block() - self.scanner.chain_reorg_rescan_window
        )

        if self.scanner.get_last_scanned_block() == 0:
            # first run so calculate starting block number based on dkg timeout
            suggested_start_block = self._get_first_scan_start_block_number()
        else:
            suggested_start_block = self.scanner.get_suggested_scan_start_block()

        end_block = self.scanner.get_suggested_scan_end_block()
        self.__scan(
            suggested_start_block, end_block, self.ritualist.transacting_power.account
        )

    def add_ritual(self, ritual_id, ritual):
        self.rituals[ritual_id] = ritual
        return ritual

    def track_ritual(self, ritual_id: int, ritual=None, transcript=None, confirmations=None, checkin_timestamp=None):
        try:
            _ritual = self.rituals[ritual_id]
        except KeyError:
            if not ritual:
                raise ValueError("Ritual not found and no new ritual provided")
            _ritual = self.add_ritual(ritual_id=ritual_id, ritual=ritual)
        if ritual_id and ritual:
            # replace the whole ritual
            self.rituals[ritual_id] = ritual
        if transcript:
            # update the transcript
            _ritual.transcript = transcript
        if confirmations:
            # update the confirmations
            _ritual.confirmations = confirmations
        if checkin_timestamp:
            # update the checkin timestamp
            _ritual.checkin_timestamp = checkin_timestamp
