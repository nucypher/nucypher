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

        self.coordinator_agent = operator.coordinator_agent

        super().__init__(
            operator=operator,
            web3=operator.coordinator_agent.blockchain.w3,
            contract=contract,
            events=events,
            actions=actions,
            persistent=persistent,
            timeout=self.coordinator_agent.get_timeout(),
        )

    def _get_identifier(self, event: AttributeDict) -> str:
        return event.args.ritualId

    def _action_required_based_on_participation_state(
        self, participation_state: DkgParticipationState, event: AttributeDict
    ) -> bool:
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
        event_type = getattr(self.contract.events, event.event)
        args = event.args
        if event_type == self.contract.events.StartRitual:
            participation_state = self.DkgParticipationState(
                participating=(self.operator.checksum_address in args.participants)
            )
            return participation_state

        ritual_id = args.ritualId
        # obtain information from contract
        (
            participating,
            posted_transcript,
            posted_aggregate,
        ) = self._get_participation_state_values_from_contract(ritual_id=ritual_id)
        participation_state = self.DkgParticipationState(
            participating=participating,
            already_posted_transcript=posted_transcript,
            already_posted_aggregate=posted_aggregate,
        )
        return participation_state

    def _update_participation_state(
        self, participation_state: DkgParticipationState, event: AttributeDict
    ) -> None:
        #
        # already tracked and participating in ritual - populate other values
        #
        event_type = getattr(self.contract.events, event.event)
        args = event.args
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
                ritual_id = args.ritualId
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

    def scan(self):
        last_scanned_block = self.scanner.get_last_scanned_block()
        self._LAST_SCANNED_BLOCK_METRIC.set(last_scanned_block)

        super().scan()
