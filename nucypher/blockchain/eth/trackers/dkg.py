import datetime
import os
import time
from typing import Callable, List, Type

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

    class ParticipationState:
        def __init__(
            self,
            participating=False,
            already_posted_transcript=False,
            already_posted_aggregate=False,
        ):
            self.participating = participating
            self.already_posted_transcript = already_posted_transcript
            self.already_posted_aggregate = already_posted_aggregate

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

        self.events = [
            self.contract.events.StartRitual,
            self.contract.events.TranscriptPosted,
            self.contract.events.StartAggregationRound,
            self.contract.events.AggregationPosted,
            self.contract.events.EndRitual,
        ]

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
        self.participation_states = dict()  # { ritual_id -> ParticipationState }

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

    def start(self):
        """Start the event scanner task."""
        return self.task.start()

    def stop(self):
        """Stop the event scanner task."""
        return self.task.stop()

    def _action_required(self, event_type: Type[ContractEvent]):
        """Check if an action is required for a given event type."""
        return event_type in self.actions

    def _is_participating_in_ritual(self, ritual_id: int) -> bool:
        """
        Checks the Coordinator contact to determine if the Ritualist is participating in this
        ritual.
        """
        # do some work to figure out if this event is relevant
        participants = self.coordinator_agent.get_participants(ritual_id=ritual_id)
        for p in participants:
            if p.provider == self.ritualist.checksum_address:
                return True

        return False

    def _is_relevant_event(
        self, event: AttributeDict, event_type: Type[ContractEvent]
    ) -> bool:
        """
        Secondary filtration of events. Returns whether this event is related to a ritual that
        the Ritualist is participating in.
        """
        args = event.args

        # check for participation
        participation_state = self.participation_states.get(args.ritualId)
        if not participation_state:
            # unsure about anything; create bare-bones state (default values); need to do more processing
            participation_state = self.ParticipationState()
            self.participation_states[args.ritualId] = participation_state
            state_already_tracked = False
        else:
            state_already_tracked = True

        # now we have a participating state to use/populate
        if event_type == self.contract.events.StartRitual:
            participation_state.participating = (
                self.ritualist.checksum_address in args.participants
            )
        elif event_type == self.contract.events.TranscriptPosted:
            if args.node == self.ritualist.checksum_address:
                participation_state.participating = True
                participation_state.already_posted_transcript = True
        elif event_type == self.contract.events.AggregationPosted:
            if args.node == self.ritualist.checksum_address:
                # done all of our ritual tasks
                participation_state.participating = True
                participation_state.already_posted_transcript = True
                participation_state.already_posted_aggregate = True
        #
        # special cases where you can't determine participation from event input arguments
        #
        elif event_type == self.contract.events.StartAggregationRound:
            if state_already_tracked and participation_state.participating:
                # know ritualist is participating
                participation_state.already_posted_transcript = True
            elif not state_already_tracked:
                if self._is_participating_in_ritual(ritual_id=args.ritualId):
                    participation_state.participating = True
                    participation_state.already_posted_transcript = True
        elif event_type == self.contract.events.EndRitual:
            # while `EndRitual` signals the end of the ritual, the event being relevant is not
            # the same as acting upon the event. Perhaps there is an event action for the EndRitual
            # event for a ritual that is being participated in. So to be complete, and adhere to
            # the expectations of this function we still determine if participating if state not
            # previously tracked
            if not state_already_tracked:
                if self._is_participating_in_ritual(ritual_id=args.ritualId):
                    participation_state.participating = True
                    participation_state.already_posted_transcript = True
                    participation_state.already_posted_aggregate = True

            # ritual is over no need to track the state anymore
            self.participation_states.pop(args.ritualId, None)
        else:
            raise ValueError(f"unprocessed event type: {event_type}")

        # what did we learn
        if not participation_state.participating:
            return False

        return True

    def __execute_action(
        self,
        event_type: Type[ContractEvent],
        timestamp: int,
        ritual_id: int,
        defer: bool = False,
        **kwargs,
    ):
        """Execute a round of a ritual asynchronously."""
        def task():
            self.actions[event_type](timestamp=timestamp, ritual_id=ritual_id, **kwargs)
        if defer:
            d = threads.deferToThread(task)
            d.addErrback(self.task.handle_errors)
            return d
        else:
            return task()

    def _handle_ritual_event(
        self, event: AttributeDict, get_block_when: Callable[[int], datetime.datetime]
    ):
        event_type = getattr(self.contract.events, event.event)
        # Filter out events that are not for me
        if not self._is_relevant_event(event, event_type):
            self.log.debug(f"Event {event.event} is not for me, skipping")
            return

        # is event actionable or just used for understanding ritual state
        if not self._action_required(event_type):
            self.log.debug(f"Non-actionable event {event.event}, skipping")
            return

        # NOTE: this format splits on *capital letters* and converts to snake case
        #  so "StartConfirmationRound" becomes "start_confirmation_round"
        #  do not use abbreviations in event names (e.g. "DKG" -> "d_k_g")
        formatted_kwargs = {camel_case_to_snake(k): v for k, v in event.args.items()}
        timestamp = int(get_block_when(event.blockNumber).timestamp())
        ritual_id = event.args.ritualId
        ritual = self.coordinator_agent.get_ritual(ritual_id=ritual_id)
        self.add_ritual(ritual_id=ritual_id, ritual=ritual)
        d = self.__execute_action(
            event_type=event_type, timestamp=timestamp, **formatted_kwargs
        )
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
