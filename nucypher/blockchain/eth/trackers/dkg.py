import os
import time
from twisted.internet import threads
from typing import Callable, List, Optional, Tuple, Type, Union
from web3 import Web3
from web3.contract.contract import Contract, ContractEvent
from web3.datastructures import AttributeDict
from web3.providers import BaseProvider

from nucypher.policy.conditions.utils import camel_case_to_snake
from nucypher.utilities.events import EventScanner, JSONifiedState
from nucypher.utilities.logging import Logger
from nucypher.utilities.task import SimpleTask


class EventActuator(EventScanner):
    """Act on events that are found by the scanner."""

    def __init__(self, hooks: List[Callable], clear: bool = True, *args, **kwargs):
        self.log = Logger("EventActuator")
        if clear and os.path.exists(JSONifiedState.STATE_FILENAME):
            os.remove(JSONifiedState.STATE_FILENAME)
        self.hooks = hooks
        super().__init__(*args, **kwargs)

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

    INTERVAL = 10 # seconds

    def __init__(self, scanner: Callable, *args, **kwargs):
        self.scanner = scanner
        super().__init__(*args, **kwargs)

    def run(self):
        self.scanner()

    def handle_errors(self, *args, **kwargs):
        self.log.warn("Error during ritual event scanning: {}".format(args[0].getTraceback()))
        raise args[0]


class ActiveRitualTracker:

    MAX_CHUNK_SIZE = 10000

    def __init__(self,
                 ritualist,
                 eth_provider: BaseProvider,
                 contract: Contract,
                 start_block: int = 0,  # TODO: use a start block that correlates to the ritual timeout
                 persistent: bool = False  # TODO: use persistent storage?
                 ):

        self.log = Logger("RitualTracker")

        self.ritualist = ritualist
        self.rituals = dict()  # TODO: use persistent storage?

        self.eth_provider = eth_provider
        self.contract = contract
        self.start_block = start_block

        # Restore/create persistent event scanner state
        self.persistent = persistent
        self.state = JSONifiedState(persistent=persistent)
        self.state.restore()

        # Map events to handlers
        self.actions = {
            contract.events.StartTranscriptRound: self.ritualist.perform_round_1,
            contract.events.StartAggregationRound: self.ritualist.perform_round_2,
        }
        self.events = list(self.actions)

        self.provider = eth_provider
        # Remove the default JSON-RPC retry middleware
        # as it correctly cannot handle eth_getLogs block range throttle down.
        self.provider._middlewares = (
            tuple()
        )  # TODO: Do this more precisely to not unintentionally remove other middlewares
        self.web3 = Web3(self.provider)

        self.scanner = EventActuator(
            hooks=[self._handle_ritual_event],
            web3=self.web3,
            state=self.state,
            contract=self.contract,
            events=self.events,
            filters={"address": contract.address},
            # How many maximum blocks at the time we request from JSON-RPC,
            # and we are unlikely to exceed the response size limit of the JSON-RPC server
            max_chunk_scan_size=self.MAX_CHUNK_SIZE
        )

        self.task = EventScannerTask(scanner=self.scan)
        self.active_tasks = set()
        self.refresh()

    def get_ritual(self, ritual_id: int, with_participants: bool = True):
        """Get a ritual from the blockchain."""
        ritual = self.ritualist.coordinator_agent.get_ritual(
            ritual_id=ritual_id, with_participants=with_participants
        )
        return ritual

    def refresh(self, fetch_rituals: Optional[List[int]] = None, all: bool = False):
        """Refresh the list of rituals with the latest data from the blockchain"""
        ritual_ids = self.rituals.keys()
        if all:
            ritual_ids = range(self.ritualist.coordinator_agent.number_of_rituals() - 1)
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
            # self.log.debug(f"Already tracking {event_type} for ritual {ritual_id} from block #{block_number}")
            return False
        return True

    def _filter(self, event) -> Tuple[AttributeDict, Union[None, Type[ContractEvent]]]:
        """Secondary filtration of events."""
        name, args = event.event, event.args
        event_type = getattr(self.contract.events, event.event)
        if hasattr(args, "nodes"):
            # Filter out events that are not for me
            if self.ritualist.checksum_address not in args.nodes:
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
        ritual = self.get_ritual(ritual_id=event.args.ritualId)
        self.add_ritual(ritual=ritual)
        self.active_tasks.add((event_type, ritual.id))
        d = self.__execute_round(event_type=event_type, timestamp=timestamp, **formatted_kwargs)
        return d

    def __scan(self, start_block, end_block, account):
        # Run the scan
        # self.log.debug(f"({account[:8]}) Scanning events from blocks {start_block} - {end_block}")
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
        chain_reorg_safety_blocks = 10
        self.scanner.delete_potentially_forked_block_data(self.state.get_last_scanned_block() - chain_reorg_safety_blocks)

        # Scan from [last block scanned] - [latest ethereum block]
        # Note that our chain reorg safety blocks cannot go negative
        start_block = max(self.state.get_last_scanned_block() - chain_reorg_safety_blocks, self.start_block)
        end_block = self.scanner.get_suggested_scan_end_block()
        self.__scan(start_block, end_block, self.ritualist.transacting_power.account)

    # def get_node_index(self, ritual_id: int, node: ChecksumAddress) -> int:
    #     return self.rituals[ritual_id].nodes.index(node)

    def add_ritual(self, ritual):
        self.rituals[ritual.id] = ritual
        return ritual

    def track_ritual(self, ritual_id: int, ritual=None, transcript=None, confirmations=None, checkin_timestamp=None):
        try:
            _ritual = self.rituals[ritual_id]
        except KeyError:
            if not ritual:
                raise ValueError("Ritual not found and no new ritual provided")
            _ritual = self.add_ritual(ritual=ritual)
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
