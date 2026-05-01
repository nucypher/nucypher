import datetime
import time
from abc import ABC, abstractmethod
from typing import Callable, Dict, List

from twisted.internet import threads
from web3 import Web3
from web3.contract import Contract
from web3.contract.contract import ContractEvent
from web3.datastructures import AttributeDict

from nucypher.policy.conditions.utils import camel_case_to_snake
from nucypher.utilities.events import EventScanner, JSONifiedState
from nucypher.utilities.logging import Logger
from nucypher.utilities.task import SimpleTask


class EventActuator(EventScanner):
    """Act on events that are found by the scanner."""

    def __init__(
        self,
        hooks: List[
            Callable[[AttributeDict, Callable[[int], datetime.datetime]], None]
        ],
        *args,
        **kwargs,
    ):
        self.log = Logger("EventActuator")
        self.hooks = hooks
        super().__init__(*args, **kwargs)

    def process_event(
        self, event: AttributeDict, get_block_when: Callable[[int], datetime.datetime]
    ):
        for hook in self.hooks:
            try:
                hook(event, get_block_when)
            except Exception as e:
                self.log.warn("Error during event hook: {}".format(e))
                raise
        super().process_event(event, get_block_when)


class EventScannerTask(SimpleTask):
    """Task that runs the event scanner in a looping call."""

    INTERVAL = 240  # 4 mins in seconds

    def __init__(self, scanner: Callable):
        self.scanner = scanner
        super().__init__()

    def run(self) -> None:
        self.scanner()

    def handle_errors(self, *args, **kwargs) -> None:
        self.log.warn(
            "Error during ritual event scanning: {}".format(args[0].getTraceback())
        )
        if not self._task.running:
            self.log.warn("Restarting event scanner task!")
            self.start(now=False)  # take a breather


class EventTracker(ABC):

    def __init__(
        self,
        operator,
        web3: Web3,
        contract: Contract,
        events: List[ContractEvent],
        actions: Dict[ContractEvent, Callable],
        min_chunk_scan_size: int,
        chain_reorg_rescan_window: int,
        persistent: bool = False,  # TODO: use persistent storage?,
        *args,
        **kwargs,
    ):
        self.log = Logger("EventTracker")

        self.operator = operator
        self.web3 = web3
        self.contract = contract
        self.events = events
        self.actions = actions

        # Restore/create persistent event scanner state
        self.persistent = persistent
        self.state = JSONifiedState(persistent=persistent)
        self.state.restore()

        self.scanner = EventActuator(
            hooks=[self._handle_event],
            web3=self.web3,
            state=self.state,
            contract=self.contract,
            events=self.events,
            min_chunk_scan_size=min_chunk_scan_size,
            chain_reorg_rescan_window=chain_reorg_rescan_window,
        )

        self.task = EventScannerTask(scanner=self.scan)

    @property
    def provider(self):
        return self.web3.provider

    # TODO: should sample_window_size be additionally configurable/chain-dependent?
    @abstractmethod
    def _get_first_scan_start_block_number(self, sample_window_size: int = 100) -> int:
        """
        Returns the block number to start scanning for events from.
        """
        raise NotImplementedError

    @abstractmethod
    def _action_required(self, event: AttributeDict) -> bool:
        """Check if an action is required for a given ritual event."""
        raise NotImplementedError

    def start(self) -> None:
        """Start the event scanner task."""
        self.task.start()

    def stop(self) -> None:
        """Stop the event scanner task."""
        self.task.stop()

    def __execute_action(
        self,
        event: AttributeDict,
        timestamp: int,
        defer: bool = False,
    ):
        """Execute a round of a ritual asynchronously."""
        # NOTE: this format splits on *capital letters* and converts to snake case
        #  so "StartConfirmationRound" becomes "start_confirmation_round"
        #  do not use abbreviations in event names (e.g. "DKG" -> "d_k_g")
        formatted_kwargs = {camel_case_to_snake(k): v for k, v in event.args.items()}
        event_type = getattr(self.contract.events, event.event)

        def task():
            self.actions[event_type](timestamp=timestamp, **formatted_kwargs)

        if defer:
            d = threads.deferToThread(task)
            d.addErrback(self.task.handle_errors)
            return d
        else:
            return task()

    def _handle_event(
        self,
        event: AttributeDict,
        get_block_when: Callable[[int], datetime.datetime],
    ):
        # is event actionable
        if not self._action_required(event):
            self.log.debug(
                f"[{self.contract.address}] Event '{event.event}' does not require further action"
            )
            return

        timestamp = int(get_block_when(event.blockNumber).timestamp())
        d = self.__execute_action(event=event, timestamp=timestamp)
        return d

    def __scan(self, start_block, end_block, account):
        # Run the scan
        self.log.debug(
            f"[{self.contract.address}] ({account[:8]}) Scanning events in block range {start_block} - {end_block}"
        )
        start = time.time()
        result, total_chunks_scanned = self.scanner.scan(start_block, end_block)
        if self.persistent:
            self.state.save()
        duration = time.time() - start
        self.log.debug(
            f"[{self.contract.address}] Scanned total of {len(result)} events, in {duration} seconds, "
            f"total {total_chunks_scanned} chunk scans performed"
        )

    def scan(self):
        """
        Assume we might have scanned the blocks all the way to the last Ethereum block
        that mined a few seconds before the previous scan run ended.
        Because there might have been a minor Ethereum chain reorganisations since the last scan ended,
        we need to discard the last few blocks from the previous scan results.
        """
        last_scanned_block = self.scanner.get_last_scanned_block()

        if last_scanned_block == 0:
            # first run so calculate starting block number based on dkg timeout
            suggested_start_block = self._get_first_scan_start_block_number()
        else:
            self.scanner.delete_potentially_forked_block_data(
                last_scanned_block - self.scanner.chain_reorg_rescan_window
            )
            suggested_start_block = self.scanner.get_suggested_scan_start_block()

        end_block = self.scanner.get_suggested_scan_end_block()
        self.__scan(
            suggested_start_block, end_block, self.operator.transacting_power.account
        )
