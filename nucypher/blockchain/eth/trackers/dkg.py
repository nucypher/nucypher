from typing import Optional, Tuple

import maya
from prometheus_client import REGISTRY, Gauge
from web3.datastructures import AttributeDict

from nucypher.blockchain.eth.models import Coordinator
from nucypher.blockchain.eth.trackers.events import EventTracker
from nucypher.blockchain.eth.utils import get_block_just_before
from nucypher.utilities.cache import TTLCache


class ActiveRitualTracker(EventTracker):
    # how often to check/purge for expired cached values - 8hrs?
    _PARTICIPATION_STATES_PURGE_INTERVAL = 60 * 60 * 8

    # what's the buffer for potentially receiving repeated events - 10mins?
    _RITUAL_TIMEOUT_ADDITIONAL_TTL_BUFFER = 60 * 10

    _LAST_SCANNED_BLOCK_METRIC = Gauge(
        "ritual_events_last_scanned_block_number",
        "Last scanned block number for ritual events",
        registry=REGISTRY,
    )

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
        operator,
        persistent: bool = False,  # TODO: use persistent storage?
    ):
        contract = operator.coordinator_agent.contract
        actions = {
            contract.events.StartRitual: operator.perform_round_1,
            contract.events.StartAggregationRound: operator.perform_round_2,
        }
        events = [
            contract.events.StartRitual,
            contract.events.StartAggregationRound,
            contract.events.EndRitual,
        ]

        super().__init__(
            operator=operator,
            web3=operator.coordinator_agent.blockchain.w3,
            contract=contract,
            events=events,
            actions=actions,
            persistent=persistent,
        )

        self.coordinator_agent = operator.coordinator_agent

        cache_ttl = (
            self.coordinator_agent.get_timeout()
            + self._RITUAL_TIMEOUT_ADDITIONAL_TTL_BUFFER
        )
        self._participation_states = TTLCache(
            ttl=cache_ttl
        )  # { ritual_id -> ParticipationState }
        self._participation_states_next_purge_timestamp = maya.now().add(
            seconds=self._PARTICIPATION_STATES_PURGE_INTERVAL
        )

    # TODO: should sample_window_size be additionally configurable/chain-dependent?
    def _get_first_scan_start_block_number(self, sample_window_size: int = 100) -> int:
        """
        Returns the block number to start scanning for events from.
        """
        timeout = self.coordinator_agent.get_timeout()
        return get_block_just_before(
            w3=self.web3, how_far_back=timeout, sample_window_size=sample_window_size
        )

    def _action_required(self, event: AttributeDict) -> bool:
        """Check if an action is required for a given ritual event."""
        # establish participation state first
        participation_state = self._get_participation_state(event)

        if not participation_state.participating:
            return False

        # does event have an associated action
        event_type = getattr(self.contract.events, event.event)

        event_has_associated_action = event_type in self.actions
        already_posted_transcript = (
            event_type == self.contract.events.StartRitual
            and participation_state.already_posted_transcript
        )
        already_posted_aggregate = (
            event_type == self.contract.events.StartAggregationRound
            and participation_state.already_posted_aggregate
        )
        if any(
            [
                not event_has_associated_action,
                already_posted_transcript,
                already_posted_aggregate,
            ]
        ):
            return False

        return True

    def _get_ritual_participant_info(
        self, ritual_id: int
    ) -> Optional[Coordinator.Participant]:
        """
        Returns node's participant information for the provided
        ritual id; None if node is not participating in the ritual
        """
        is_participant = self.coordinator_agent.is_participant(
            ritual_id=ritual_id, provider=self.operator.checksum_address
        )
        if is_participant:
            participant = self.coordinator_agent.get_participant(
                ritual_id=ritual_id,
                provider=self.operator.checksum_address,
                transcript=True,
            )
            return participant

        return None

    def _purge_expired_participation_states_as_needed(self):
        # let's check whether we should purge participation states before returning
        now = maya.now()
        if now > self._participation_states_next_purge_timestamp:
            self._participation_states.purge_expired()
            self._participation_states_next_purge_timestamp = now.add(
                seconds=self._PARTICIPATION_STATES_PURGE_INTERVAL
            )

    def _get_participation_state_values_from_contract(
        self, ritual_id: int
    ) -> Tuple[bool, bool, bool]:
        """
        Obtains values for ParticipationState from the Coordinator contract.
        """
        participating = False
        already_posted_transcript = False
        already_posted_aggregate = False

        participant_info = self._get_ritual_participant_info(ritual_id=ritual_id)
        if participant_info:
            # actually participating in this ritual; get latest information
            participating = True
            # populate information since we already hit the contract
            already_posted_transcript = bool(participant_info.transcript)
            already_posted_aggregate = participant_info.aggregated

        return participating, already_posted_transcript, already_posted_aggregate

    def _get_participation_state(self, event: AttributeDict) -> ParticipationState:
        """
        Returns the current participation state of the Operator as it pertains to
        the ritual associated with the provided event.
        """
        self._purge_expired_participation_states_as_needed()

        event_type = getattr(self.contract.events, event.event)
        if event_type not in self.events:
            # should never happen since we specify the list of events we
            # want to receive (1st level of filtering)
            raise RuntimeError(f"Unexpected event type: {event_type}")

        args = event.args

        try:
            ritual_id = args.ritualId
        except AttributeError:
            # no ritualId arg
            raise RuntimeError(
                f"Unexpected event type: '{event_type}' has no ritual id as argument"
            )

        participation_state = self._participation_states[ritual_id]
        if not participation_state:
            # not previously tracked; get current state and return
            # need to determine if participating in this ritual or not
            if event_type == self.contract.events.StartRitual:
                participation_state = self.ParticipationState(
                    participating=(self.operator.checksum_address in args.participants)
                )
                self._participation_states[ritual_id] = participation_state
                return participation_state

            # obtain information from contract
            (
                participating,
                posted_transcript,
                posted_aggregate,
            ) = self._get_participation_state_values_from_contract(ritual_id=ritual_id)
            participation_state = self.ParticipationState(
                participating=participating,
                already_posted_transcript=posted_transcript,
                already_posted_aggregate=posted_aggregate,
            )
            self._participation_states[ritual_id] = participation_state
            return participation_state

        # already tracked but not participating
        if not participation_state.participating:
            return participation_state

        #
        # already tracked and participating in ritual - populate other values
        #
        if event_type == self.contract.events.StartAggregationRound:
            participation_state.already_posted_transcript = True
        elif event_type == self.contract.events.EndRitual:
            # while `EndRitual` signals the end of the ritual, and there is no
            # *current* node action for EndRitual, perhaps there will
            # be one in the future. So to be complete, and adhere to
            # the expectations of this function we still update
            # the participation state
            if args.successful:
                # since successful we know these values are true
                participation_state.already_posted_transcript = True
                participation_state.already_posted_aggregate = True
            elif (
                not participation_state.already_posted_transcript
                or not participation_state.already_posted_aggregate
            ):
                # not successful - and unsure of state values
                # obtain information from contract
                (
                    _,  # participating ignored - we know we are participating
                    posted_transcript,
                    posted_aggregate,
                ) = self._get_participation_state_values_from_contract(
                    ritual_id=ritual_id
                )
                participation_state.already_posted_transcript = posted_transcript
                participation_state.already_posted_aggregate = posted_aggregate

        return participation_state

    def scan(self):
        last_scanned_block = self.scanner.get_last_scanned_block()
        self._LAST_SCANNED_BLOCK_METRIC.set(last_scanned_block)

        super().scan()
