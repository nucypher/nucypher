from dataclasses import dataclass
from typing import List

from eth_typing import ChecksumAddress

from nucypher.blockchain.eth.agents import CoordinatorAgent
from nucypher.utilities.logging import Logger


class DKG:
    """
    Models all required data fetched from RPC eth_calls to perform DKG ceremonies.
    """

    log = Logger("dkg")

    PHASE1 = 1
    PHASE2 = 2

    @dataclass
    class Phase1:
        """Models all required data fetched from RPC eth_calls to perform DKG round 1."""

        ritual_id: int
        ritual: CoordinatorAgent.Ritual
        status: int
        transcript: bool

        @classmethod
        def fetch(
            cls,
            coordinator_agent: CoordinatorAgent,
            provider: ChecksumAddress,
            ritual_id: int,
        ):
            """Execute all required RPC eth_calls to perform DKG round 1."""
            ritual = coordinator_agent.get_ritual(
                ritual_id=ritual_id,
                participants=True,
                transcripts=False,
            )
            status = coordinator_agent.get_ritual_status(ritual_id=ritual_id)
            participant = coordinator_agent.get_participant(
                ritual_id=ritual_id, provider=provider, transcript=True
            )
            data = cls(
                ritual_id=ritual_id,
                status=status,
                transcript=bool(participant.transcript),
                ritual=ritual,
            )
            return data

        def ready(
            self, participants: List[ChecksumAddress], provider: ChecksumAddress
        ) -> bool:
            """
            Check if this data signals readiness to perform round 1 of the DKG protocol.
            This is a gating function, each of the conditions below must be met for the
            node to be ready to perform round 1.
            """
            if set(participants) != set(self.ritual.providers):
                # This is an internal state check for consistency between the
                # participant addresses dispatched from the EventScanner (StartRitual event)
                # and the ones collected from the CoordinatorAgent. This is an abnormal state
                # and can be understood as a higher-order bug.
                raise RuntimeError(
                    f"Participants mismatch: {participants} != {self.ritual.providers}"
                )
            if provider not in participants:
                # This verifies that the node is part of the ritual according to the
                # participant addresses dispatched from the EventScanner (StartRitual event).
                # This is an abnormal state and can be understood as a higher-order bug.
                DKG.log.error(
                    f"Not part of ritual {self.ritual_id}; no need to submit transcripts; skipping execution"
                )
                return False
            if self.status != CoordinatorAgent.Ritual.Status.DKG_AWAITING_TRANSCRIPTS:
                # This verifies that the ritual is in the correct state to submit transcripts.
                # If the ritual is not in the correct state, then the node should not submit transcripts.
                # Similar to the above branches, this is an internal state check for consistency between the
                # state dispatched from the scanner and the agent.  This is an abnormal state.
                DKG.log.error(
                    f"ritual #{self.ritual_id} is not waiting for transcripts; status={self.status}; skipping execution"
                )
                return False
            if self.transcript:
                # This verifies that the node has not already submitted a transcript for this
                # ritual as read from the CoordinatorAgent.  This is a normal state, as
                # the node may have already submitted a transcript for this ritual.
                DKG.log.info(
                    f"Node {provider} has already posted a transcript for ritual "
                    f"{self.ritual_id}; skipping execution"
                )
                return False
            return True

    @dataclass
    class Phase2:
        """Models all required data fetched from RPC eth_calls to perform DKG round 2."""

        ritual_id: int
        ritual: CoordinatorAgent.Ritual
        status: int
        aggregated: bool
        missing_transcripts: int

        @classmethod
        def fetch(
            cls,
            coordinator_agent: CoordinatorAgent,
            staking_provider: ChecksumAddress,
            ritual_id: int,
        ):
            """Execute all required RPC eth_calls to perform DKG round 2."""
            ritual = coordinator_agent.get_ritual(
                ritual_id=ritual_id,
                participants=True,
                transcripts=True,
            )
            participant = coordinator_agent.get_participant(
                ritual_id=ritual_id, provider=staking_provider, transcript=False
            )
            status = coordinator_agent.get_ritual_status(ritual_id=ritual_id)
            data = cls(
                ritual_id=ritual_id,
                ritual=ritual,
                status=status,
                aggregated=bool(participant.aggregated),
                missing_transcripts=sum(1 for t in ritual.transcripts if not t),
            )
            return data

        def ready(self, operator_address: ChecksumAddress) -> bool:
            """
            Check if this node is ready to perform round 2 of the DKG protocol.
            This is a gating function: All the conditions below must be met
            for the node to be ready to perform round 2.
            """
            if self.status != CoordinatorAgent.Ritual.Status.DKG_AWAITING_AGGREGATIONS:
                # This verifies that the node is part of the ritual according to the
                # participant addresses dispatched from the EventScanner (StartRitual event).
                # This is an abnormal state.
                DKG.log.debug(
                    f"ritual #{self.ritual_id} is not waiting for aggregations; status={self.status}."
                )
                return False
            if self.aggregated:
                # This is a normal state, as the node may have already submitted an aggregated
                # transcript for this ritual, and it's not necessary to submit another one. Carry on.
                DKG.log.debug(
                    f"Node {operator_address} has already posted an aggregated transcript for ritual {self.ritual_id}."
                )
                return False
            if self.missing_transcripts:
                # This is a highly abnormal state, as it indicates that the node has not
                # received all the transcripts for the ritual but was dispatched to perform phase 2.
                # It's not possible to perform round 2 of the DKG protocol without all the transcripts available.
                message = (
                    f"Aggregation is not permitted because ritual #{self.ritual_id} is "
                    f"missing {self.missing_transcripts} transcripts."
                )
                DKG.log.critical(message)
                return False
            return True
