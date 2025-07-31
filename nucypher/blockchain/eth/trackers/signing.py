from typing import Optional, Tuple

from web3.datastructures import AttributeDict

from nucypher.blockchain.eth.models import SigningCoordinator
from nucypher.blockchain.eth.trackers.rituals import RitualTracker


class SigningRitualTracker(RitualTracker):
    class SigningParticipationState(RitualTracker.ParticipationState):
        def __init__(
            self,
            participating=False,
            already_posted_signature=False,
        ):
            super().__init__(participating)
            self.already_posted_signature = already_posted_signature

    def __init__(
        self,
        operator,
        persistent: bool = False,
    ):
        contract = operator.signing_coordinator_agent.contract
        actions = {
            contract.events.InitiateSigningCohort: operator.perform_post_signature,
        }
        events = [
            contract.events.InitiateSigningCohort,
            contract.events.SigningCohortDeployed,
        ]

        self.signing_coordinator_agent = operator.signing_coordinator_agent

        super().__init__(
            operator=operator,
            web3=operator.signing_coordinator_agent.blockchain.w3,
            contract=contract,
            events=events,
            actions=actions,
            persistent=persistent,
            timeout=self.signing_coordinator_agent.get_timeout(),
        )

    def _get_identifier(self, event: AttributeDict) -> str:
        return event.args.cohortId

    def _action_required_based_on_participation_state(
        self, participation_state: SigningParticipationState, event: AttributeDict
    ) -> bool:
        """Check if an action is required for a given ritual event."""
        # does event have an associated action
        event_type = getattr(self.contract.events, event.event)
        event_has_associated_action = event_type in self.actions
        already_posted_signature = (
            event_type == self.contract.events.InitiateSigningCohort
            and participation_state.already_posted_signature
        )
        if any(
            [
                not event_has_associated_action,
                already_posted_signature,
            ]
        ):
            return False

        return True

    def _create_participation_state(
        self, event: AttributeDict
    ) -> SigningParticipationState:
        event_type = getattr(self.contract.events, event.event)
        args = event.args
        if event_type == self.contract.events.InitiateSigningCohort:
            participation_state = self.SigningParticipationState(
                participating=(self.operator.checksum_address in args.participants)
            )
            return participation_state

        cohort_id = args.cohortId
        # obtain information from contract
        (
            participating,
            posted_signature,
        ) = self._get_participation_state_values_from_contract(cohort_id=cohort_id)
        participation_state = self.SigningParticipationState(
            participating=participating,
            already_posted_signature=posted_signature,
        )
        return participation_state

    def _update_participation_state(
        self, participation_state: SigningParticipationState, event: AttributeDict
    ) -> None:
        event_type = getattr(self.contract.events, event.event)
        if (
            event_type == self.contract.events.SigningCohortDeployed
            and not participation_state.already_posted_signature
        ):
            (
                _,  # participating ignored - we know we are participating
                posted_signature,
            ) = self._get_participation_state_values_from_contract(
                cohort_id=event.args.cohortId
            )
            participation_state.already_posted_signature = posted_signature

    def _get_cohort_participant_info(
        self, cohort_id: int
    ) -> Optional[SigningCoordinator.SigningCohortParticipant]:
        """
        Returns node's participant information for the provided
        ritual id; None if node is not participating in the ritual
        """
        is_participant = self.signing_coordinator_agent.is_signer(
            cohort_id=cohort_id, provider_address=self.operator.checksum_address
        )
        if is_participant:
            participant = self.signing_coordinator_agent.get_signer(
                cohort_id=cohort_id,
                provider=self.operator.checksum_address,
            )
            return participant

        return None

    def _get_participation_state_values_from_contract(
        self, cohort_id: int
    ) -> Tuple[bool, bool]:
        """
        Obtains values for ParticipationState from the Coordinator contract.
        """
        participating = False
        already_posted_signature = False

        participant_info = self._get_cohort_participant_info(cohort_id=cohort_id)
        if participant_info:
            # actually participating in this ritual; get latest information
            participating = True
            # populate information since we already hit the contract
            already_posted_signature = bool(participant_info.signature)

        return participating, already_posted_signature
