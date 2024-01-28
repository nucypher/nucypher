from dataclasses import dataclass
from typing import List

from eth_typing import ChecksumAddress

from nucypher.blockchain.eth.agents import CoordinatorAgent
from nucypher.utilities.logging import Logger


class DKG:
    """
    Models all required data fetched from
    RPC eth_calls to perform DKG ceremonies.
    """

    log = Logger("dkg")

    PHASE1 = 1
    PHASE2 = 2

    @dataclass
    class Phase1:
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
            """Encapsulate all required RPC eth_calls to perform DKG round 1."""
            ritual = coordinator_agent.get_ritual(
                ritual_id=ritual_id,
                participants=True,
                transcripts=False,
            )
            status = coordinator_agent.get_ritual_status(ritual_id=ritual_id)
            participant = coordinator_agent.get_participant(
                ritual_id=ritual_id, provider=provider, transcript=True
            )
            transcript = bool(participant.transcript)
            data = cls(
                ritual_id=ritual_id,
                status=status,
                transcript=transcript,
                ritual=ritual,
            )
            return data

        def ready(
            self, participants: List[ChecksumAddress], provider: ChecksumAddress
        ) -> bool:
            if provider not in participants:
                DKG.log.error(
                    f"Not part of ritual {self.ritual_id}; no need to submit transcripts; skipping execution"
                )
                return False
            if self.status != CoordinatorAgent.Ritual.Status.DKG_AWAITING_TRANSCRIPTS:
                DKG.log.error(
                    f"ritual #{self.ritual_id} is not waiting for transcripts; status={self.status}; skipping execution"
                )
                return False
            if self.transcript:
                DKG.log.info(
                    f"Node {provider} has already posted a transcript for ritual "
                    f"{self.ritual_id}; skipping execution"
                )
                return False
            return True

    @dataclass
    class Phase2:
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
            """Encapsulate all required RPC eth_calls to perform DKG round 2."""
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
            """Check if this node is ready to perform round 2 of the DKG protocol."""
            if self.status != CoordinatorAgent.Ritual.Status.DKG_AWAITING_AGGREGATIONS:
                DKG.log.debug(
                    f"ritual #{self.ritual_id} is not waiting for aggregations; status={self.status}."
                )
                return False
            if self.aggregated:
                DKG.log.debug(
                    f"Node {operator_address} has already posted an aggregated transcript for ritual {self.ritual_id}."
                )
                return False
            if self.missing_transcripts:
                message = (
                    f"Aggregation is not permitted because ritual #{self.ritual_id} is "
                    f"missing {self.missing_transcripts} transcripts."
                )
                DKG.log.critical(message)
                return False
            return True
