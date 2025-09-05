from typing import Optional, Union

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
        """
        Participation state for DKG rituals.
        """

        PREFIX = "dkg-"

        def __init__(
            self,
            participating=False,
            already_posted_transcript=False,
            already_posted_aggregate=False,
        ):
            super().__init__(participating)
            self.already_posted_transcript = already_posted_transcript
            self.already_posted_aggregate = already_posted_aggregate

    class CohortParticipationStateDuringHandover(RitualTracker.ParticipationState):
        """
        Cohort participation state during handover process.
        """

        PREFIX = "handover-"

        def __init__(self, participating=False):
            super().__init__(participating)

    def __init__(
        self,
        operator,
        persistent: bool = False,  # TODO: use persistent storage?
    ):
        contract = operator.coordinator_agent.contract

        self.handover_event_types = [
            contract.events.HandoverRequest,
            contract.events.HandoverTranscriptPosted,
            contract.events.HandoverFinalized,
            contract.events.HandoverCanceled,
        ]

        actions = {
            contract.events.StartRitual: operator.perform_round_1,
            contract.events.StartAggregationRound: operator.perform_round_2,
            contract.events.HandoverRequest: operator.perform_handover_transcript_phase,
            contract.events.HandoverTranscriptPosted: operator.perform_handover_blinded_share_phase,
        }

        all_events = [
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
            events=all_events,
            actions=actions,
            persistent=persistent,
            timeout=self.coordinator_agent.get_dkg_timeout(),
        )

    def _get_identifier(self, event: AttributeDict) -> str:
        event_type = getattr(self.contract.events, event.event)
        if event_type in self.handover_event_types:
            return f"{self.CohortParticipationStateDuringHandover.PREFIX}{event.args.ritualId}"
        else:
            return f"{self.DkgParticipationState.PREFIX}{event.args.ritualId}"

    def _action_required_based_on_participation_state(
        self,
        participation_state: Union[
            DkgParticipationState, CohortParticipationStateDuringHandover
        ],
        event: AttributeDict,
    ) -> bool:
        # Let's handle separately handover events and non-handover events
        event_type = getattr(self.contract.events, event.event)
        if event_type in self.handover_event_types:
            # handover modifies existing ritual metadata; so we need to proactively prune it
            # during handover process for ALL associated nodes
            # (part of handover, ALL existing participants in ritual) to avoid having
            # any stale metadata in the metadata storage cache
            self.operator.prune_ritual_metadata_due_to_handover(event.args.ritualId)

            is_departing_participant_in_handover = (
                event.args.departingParticipant == self.operator.checksum_address
            )
            is_incoming_participant_in_handover = (
                event.args.incomingParticipant == self.operator.checksum_address
            )

            if event_type in [
                self.contract.events.HandoverFinalized,
                self.contract.events.HandoverCanceled,
            ]:
                if (
                    event_type == self.contract.events.HandoverCanceled
                    and is_incoming_participant_in_handover
                ) or (
                    event_type == self.contract.events.HandoverFinalized
                    and is_departing_participant_in_handover
                ):
                    # if handover is canceled/finalized we need to reset the participation state
                    participation_state.participating = False

                # pruning metadata/cleanup is sufficient when Handover is finalized or canceled;
                # no further action required
                return False

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
    ) -> Union[DkgParticipationState, CohortParticipationStateDuringHandover]:
        # obtain information from contract
        participation_state = self._get_latest_participation_state_values(event=event)
        return participation_state

    def _update_participation_state(
        self,
        cached_participation_state: Union[
            DkgParticipationState, CohortParticipationStateDuringHandover
        ],
        event: AttributeDict,
    ) -> None:
        # already tracked but cache values may be out of date
        self._get_latest_participation_state_values(event, cached_participation_state)

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

    def _get_latest_participation_state_values(
        self,
        event: AttributeDict,
        cached_participation_state: Optional[
            Union[
                DkgParticipationState,
                CohortParticipationStateDuringHandover,
            ]
        ] = None,
    ) -> Union[DkgParticipationState, CohortParticipationStateDuringHandover]:
        """
        Obtains values for current participation state.
        """
        # check if we are participating in this ritual
        event_type = getattr(self.contract.events, event.event)
        if event_type in self.handover_event_types:
            return self.__get_latest_state_based_on_handover_event(
                event, cached_participation_state
            )
        else:
            return self.__get_latest_state_based_on_dkg_event(
                event, cached_participation_state
            )

    def __get_latest_state_based_on_dkg_event(
        self,
        event: AttributeDict,
        cached_participation_state: Optional[DkgParticipationState] = None,
    ) -> DkgParticipationState:
        """
        Returns the latest participation state value for DKG rituals.
        """
        # Handle DKG events; some events have all the information we need, otherwise
        # we go to the contract
        event_type = getattr(self.contract.events, event.event)
        if cached_participation_state:
            if cached_participation_state.participating:
                # already participating in this ritual
                if event_type == self.contract.events.StartAggregationRound:
                    cached_participation_state.already_posted_transcript = True
                elif (
                    event_type == self.contract.events.EndRitual
                    and event.args.successful
                ):
                    # since successful we know these values are true
                    cached_participation_state.already_posted_transcript = True
                    cached_participation_state.already_posted_aggregate = True
                return cached_participation_state
            else:
                # not participating; nothing to do here
                return cached_participation_state

        # no previous cached participation state, establish new one for cache
        new_participation_state = self.DkgParticipationState()
        if event_type == self.contract.events.StartRitual:
            # start ritual has all the information we need; no need to go to contract
            participating = self.operator.checksum_address in event.args.participants
            new_participation_state.participating = participating
        else:
            # get participant information from the contract
            participant_info = self._get_ritual_participant_info(
                ritual_id=event.args.ritualId
            )
            if participant_info:
                # actually participating in this ritual;
                # populate information since we already hit the contract
                already_posted_transcript = bool(participant_info.transcript)
                already_posted_aggregate = participant_info.aggregated
                new_participation_state.participating = True
                new_participation_state.already_posted_transcript = (
                    already_posted_transcript
                )
                new_participation_state.already_posted_aggregate = (
                    already_posted_aggregate
                )

        return new_participation_state

    def __get_latest_state_based_on_handover_event(
        self,
        event: AttributeDict,
        cached_participation_state: Optional[
            CohortParticipationStateDuringHandover
        ] = None,
    ) -> CohortParticipationStateDuringHandover:
        """
        Returns the participation state value for handover events.
        """
        # handover modifies "participating", either:
        # 1) part of handover process
        # 2) part of original ritual (handover changes metadata)
        cached_participation_state = (
            cached_participation_state or self.CohortParticipationStateDuringHandover()
        )
        if cached_participation_state.participating:
            # already participating, nothing to check here
            return cached_participation_state

        # 1) part of handover
        if self.operator.checksum_address == event.args.departingParticipant:
            # operator is the departing participant
            cached_participation_state.participating = True
        elif self.operator.checksum_address == event.args.incomingParticipant:
            # operator is the incoming participant
            cached_participation_state.participating = True

        # 2) part of original dkg
        if not cached_participation_state.participating:
            cached_participation_state.participating = (
                self.coordinator_agent.is_participant(
                    event.args.ritualId, self.operator.checksum_address
                )
            )
        return cached_participation_state


    def scan(self):
        last_scanned_block = self.scanner.get_last_scanned_block()
        self._LAST_SCANNED_BLOCK_METRIC.set(last_scanned_block)

        super().scan()
