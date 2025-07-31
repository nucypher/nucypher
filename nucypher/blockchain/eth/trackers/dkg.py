from typing import Optional, Tuple

from prometheus_client import REGISTRY, Gauge
from web3.datastructures import AttributeDict

from nucypher.blockchain.eth.models import Coordinator
from nucypher.blockchain.eth.trackers.rituals import RitualTracker


class DkgRitualTracker(RitualTracker):
    _LAST_SCANNED_BLOCK_METRIC = Gauge(
        "ritual_events_last_scanned_block_number",
        "Last scanned block number for ritual events",
        registry=REGISTRY,
    )

    class DkgParticipationState(RitualTracker.ParticipationState):
        def __init__(
            self,
            participating=False,
            already_posted_transcript=False,
            already_posted_aggregate=False,
        ):
            super().__init__(participating)
            self.already_posted_transcript = already_posted_transcript
            self.already_posted_aggregate = already_posted_aggregate

        def update(self, updated_state: "DkgParticipationState"):
            self.participating = updated_state.participating
            self.already_posted_transcript = updated_state.already_posted_transcript
            self.already_posted_aggregate = updated_state.already_posted_aggregate

    def __init__(
        self,
        operator,
        persistent: bool = False,  # TODO: use persistent storage?
    ):
        contract = operator.coordinator_agent.contract

        self.handover_event_types = [
            contract.events.HandoverTranscriptPosted,
            contract.events.HandoverRequest,
            contract.events.HandoverFinalized,
        ]

        actions = {
            contract.events.StartRitual: operator.perform_round_1,
            contract.events.StartAggregationRound: operator.perform_round_2,
            contract.events.HandoverRequest: operator.perform_handover_transcript_phase,
            contract.events.HandoverTranscriptPosted: operator.perform_handover_blinded_share_phase,
        }
        events = [
            contract.events.StartRitual,
            contract.events.StartAggregationRound,
            contract.events.EndRitual,
            *self.handover_event_types,
        ]

        self.coordinator_agent = operator.coordinator_agent

        super().__init__(
            operator=operator,
            web3=operator.coordinator_agent.blockchain.w3,
            contract=contract,
            events=events,
            actions=actions,
            persistent=persistent,
            timeout=self.coordinator_agent.get_dkg_timeout(),
        )

    def _get_identifier(self, event: AttributeDict) -> str:
        return event.args.ritualId

    def _action_required_based_on_participation_state(
        self, participation_state: DkgParticipationState, event: AttributeDict
    ) -> bool:
        # Let's handle separately handover events and non-handover events
        event_type = getattr(self.contract.events, event.event)
        if event_type in self.handover_event_types:
            # handover modifies existing ritual metadata; so we need to proactively prune it
            # during handover process and at the end to avoid having any stale metadata
            # in the cache
            self.operator.prune_ritual_metadata_due_to_handover(
                event.args.ritualId
            )

            if event_type == self.contract.events.HandoverFinalized:
                # pruning metadata is sufficient when Handover is finalized;
                # no further action required
                return False

            is_departing_participant_in_handover = (
                    event_type == self.contract.events.HandoverTranscriptPosted
                    and event.args.departingParticipant
                    == self.operator.checksum_address
            )
            is_incoming_participant_in_handover = (
                    event_type == self.contract.events.HandoverRequest
                    and event.args.incomingParticipant
                    == self.operator.checksum_address
            )
            # for handover events we need to act only if the operator is the departing or incoming participant
            return (
                    is_departing_participant_in_handover
                    or is_incoming_participant_in_handover
            )

        # Non-handover events (for the moment, DKG events)
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

    def _create_participation_state(
        self, event: AttributeDict
    ) -> DkgParticipationState:
        # obtain information from contract
        participation_state = self._get_participation_state_values_from_contract(event=event)
        return participation_state

    def _update_participation_state(
        self, participation_state: DkgParticipationState, event: AttributeDict
    ) -> None:
        #
        # already tracked and participating in ritual - populate other values
        # based on certain events, the values can be populated without consulting the contract
        #
        event_type = getattr(self.contract.events, event.event)
        if event_type == self.contract.events.StartAggregationRound:
            participation_state.already_posted_transcript = True
        elif event_type == self.contract.events.EndRitual:
            # while `EndRitual` signals the end of the ritual, and there is no
            # *current* node action for EndRitual, perhaps there will
            # be one in the future. So to be complete, and adhere to
            # the expectations of this function we still update
            # the participation state
            if event.args.successful:
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
                    event=event,
                )
                participation_state.already_posted_transcript = posted_transcript
                participation_state.already_posted_aggregate = posted_aggregate
        elif event_type == self.contract.events.HandoverFinalized:
            # HandoverFinalized signals the end of the handover process
            # node is either departing or incoming participant
            if event.args.departingParticipant == self.operator.checksum_address:
                # node no longer in ritual
                participation_state.participating = False
                participation_state.already_posted_transcript = False
                participation_state.already_posted_aggregate = False
            else:
                # node newly added to ritual
                participation_state.participating = True
                participation_state.already_posted_transcript = True
                participation_state.already_posted_aggregate = True


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

    def _get_participation_state_values_from_contract(
        self, event: AttributeDict
    ) -> DkgParticipationState:
        """
        Obtains values for current participation state.
        """
        # check if we are participating in this ritual
        event_type = getattr(self.contract.events, event.event)
        if event_type in self.handover_event_types:
            return self.__get_handover_participation_state_value(event)
        else:
            return self.__get_dkg_participation_state_value(event)


    def __get_dkg_participation_state_value(self, event: AttributeDict) -> DkgParticipationState:
        """
        Returns the participation state value for DKG events.
        """
        # Handle DKG events
        event_type = getattr(self.contract.events, event.event)
        if event_type == self.contract.events.StartRitual:
            participating = self.operator.checksum_address in event.args.participants
            return self.DkgParticipationState(participating=participating)
        else:
            participant_info = self._get_ritual_participant_info(ritual_id=event.args.ritualId)
            if participant_info:
                # actually participating in this ritual; get latest information
                participating = True
                # populate information since we already hit the contract
                already_posted_transcript = bool(participant_info.transcript)
                already_posted_aggregate = participant_info.aggregated
                return self.DkgParticipationState(
                    participating=participating,
                    already_posted_transcript=already_posted_transcript,
                    already_posted_aggregate=already_posted_aggregate
                )

        return self.DkgParticipationState(participating=False)

    def __get_handover_participation_state_value(self, event: AttributeDict):
        """
        Returns the participation state value for handover events.
        """
        # Handle Handover events
        if self.operator.checksum_address == event.args.departingParticipant:
            # operator is the departing participant so we know that ritual is active and
            # node already posted data
            return self.DkgParticipationState(
                participating=True,
                already_posted_transcript=True,
                already_posted_aggregate=True,
            )

        event_type = getattr(self.contract.events, event.event)
        if event_type == self.contract.events.HandoverRequest and self.operator.checksum_address == event.args.incomingParticipant:
            return self.DkgParticipationState(participating=True)

        ritual_id = event.args.ritualId
        handover = self.coordinator_agent.get_handover(
            ritual_id=ritual_id,
            departing_provider=event.args.departingParticipant
        )
        # check if operator is the incoming participant; other values aren't applicable
        participating = (handover.incoming_validator == self.operator.checksum_address)
        return self.DkgParticipationState(participating=participating)


    def scan(self):
        last_scanned_block = self.scanner.get_last_scanned_block()
        self._LAST_SCANNED_BLOCK_METRIC.set(last_scanned_block)

        super().scan()
