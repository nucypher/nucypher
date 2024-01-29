from dataclasses import dataclass, field
from typing import (
    Dict,
    Iterable,
    List,
    NamedTuple,
)

from eth_typing.evm import ChecksumAddress
from nucypher_core import SessionStaticKey
from nucypher_core.ferveo import (
    DkgPublicKey,
    FerveoPublicKey,
)

from nucypher.utilities.logging import Logger


@dataclass
class Ferveo:
    class G1Point(NamedTuple):
        """Coordinator contract representation of DkgPublicKey."""

        # TODO validation of these if used directly
        word0: bytes  # 32 bytes
        word1: bytes  # 16 bytes

        @classmethod
        def from_dkg_public_key(cls, public_key: DkgPublicKey):
            return cls.from_bytes(bytes(public_key))

        @classmethod
        def from_bytes(cls, data: bytes):
            if len(data) != DkgPublicKey.serialized_size():
                raise ValueError(
                    f"Invalid byte length; expected {DkgPublicKey.serialized_size()} "
                    f"bytes but got {len(data)} bytes for G1Point"
                )
            return cls(word0=data[:32], word1=data[32:48])

        def to_dkg_public_key(self) -> DkgPublicKey:
            data = bytes(self)
            if not data:
                return None
            return DkgPublicKey.from_bytes(data)

        def __bytes__(self):
            return self.word0 + self.word1

    class G2Point(NamedTuple):
        """
        Coordinator contract representation of Ferveo Participant public key.
        """

        # TODO validation of these if used directly
        word0: bytes  # 32 bytes
        word1: bytes  # 32 bytes
        word2: bytes  # 32 bytes

        @classmethod
        def from_public_key(cls, public_key: FerveoPublicKey):
            return cls.from_bytes(bytes(public_key))

        @classmethod
        def from_bytes(cls, data: bytes):
            if len(data) != FerveoPublicKey.serialized_size():
                raise ValueError(
                    f"Invalid byte length; expected {FerveoPublicKey.serialized_size()}"
                    f" bytes but got {len(data)} bytes for G2Point"
                )
            return cls(word0=data[:32], word1=data[32:64], word2=data[64:96])

        def to_public_key(self) -> FerveoPublicKey:
            data = bytes(self)
            if not data:
                return
            return FerveoPublicKey.from_bytes(data)

        def __bytes__(self):
            return self.word0 + self.word1 + self.word2


@dataclass
class Coordinator:
    @dataclass
    class RitualStatus:
        NON_INITIATED = 0
        DKG_AWAITING_TRANSCRIPTS = 1
        DKG_AWAITING_AGGREGATIONS = 2
        DKG_TIMEOUT = 3
        DKG_INVALID = 4
        ACTIVE = 5
        EXPIRED = 6

    @dataclass
    class Participant:
        index: int
        provider: ChecksumAddress
        aggregated: bool = False
        transcript: bytes = bytes()
        decryption_request_static_key: bytes = bytes()

        @classmethod
        def from_data(cls, index: int, data: list):
            return cls(
                index=index,
                provider=ChecksumAddress(data[0]),
                aggregated=data[1],
                transcript=bytes(data[2]),
                decryption_request_static_key=bytes(data[3]),
            )

    @dataclass
    class Ritual:
        id: int
        initiator: ChecksumAddress
        authority: ChecksumAddress
        access_controller: ChecksumAddress
        dkg_size: int
        init_timestamp: int
        end_timestamp: int
        threshold: int
        total_transcripts: int = 0
        total_aggregations: int = 0
        public_key: Ferveo.G1Point = None
        aggregation_mismatch: bool = False
        aggregated_transcript: bytes = bytes()
        participants: List = field(default_factory=list)

        @property
        def providers(self):
            return [p.provider for p in self.participants]

        @property
        def transcripts(self) -> Iterable[bytes]:
            return [p.transcript for p in self.participants]

        @property
        def shares(self) -> int:
            return len(self.providers)

        def get_participant(self, provider: ChecksumAddress):
            for p in self.participants:
                if p.provider == provider:
                    return p

        @property
        def participant_public_keys(self) -> Dict[ChecksumAddress, SessionStaticKey]:
            participant_public_keys = {}
            for p in self.participants:
                participant_public_keys[p.provider] = SessionStaticKey.from_bytes(
                    p.decryption_request_static_key
                )
            return participant_public_keys

        @staticmethod
        def make_participants(
            data: list, start: int = 0
        ) -> Iterable["Coordinator.Participant"]:
            """Converts a list of participant data into an iterable of Participant objects."""
            for i, participant_data in enumerate(data, start=start):
                participant = Coordinator.Participant.from_data(
                    index=i, data=participant_data
                )
                yield participant


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
        ritual: Coordinator.Ritual
        status: int
        transcript: bool

        @classmethod
        def fetch(
            cls,
            coordinator_agent,
            provider: ChecksumAddress,
            ritual_id: int,
        ):
            """Execute all required RPC eth_calls to perform DKG round 1."""
            ritual = coordinator_agent.get_ritual(
                ritual_id=ritual_id,
                transcripts=False,
            )
            status = coordinator_agent.get_ritual_status(ritual_id=ritual_id)
            participant = coordinator_agent.get_participant(
                ritual_id=ritual_id, provider=provider, transcript=True
            )
            data = cls(
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
                    f"Not part of ritual {self.ritual.id}; no need to submit transcripts; skipping execution"
                )
                return False
            if self.status != Coordinator.RitualStatus.DKG_AWAITING_TRANSCRIPTS:
                # This verifies that the ritual is in the correct state to submit transcripts.
                # If the ritual is not in the correct state, then the node should not submit transcripts.
                # Similar to the above branches, this is an internal state check for consistency between the
                # state dispatched from the scanner and the agent.  This is an abnormal state.
                DKG.log.error(
                    f"ritual #{self.ritual.id} is not waiting for transcripts; status={self.status}; skipping execution"
                )
                return False
            if self.transcript:
                # This verifies that the node has not already submitted a transcript for this
                # ritual as read from the CoordinatorAgent.  This is a normal state, as
                # the node may have already submitted a transcript for this ritual.
                DKG.log.info(
                    f"Node {provider} has already posted a transcript for ritual "
                    f"{self.ritual.id}; skipping execution"
                )
                return False
            return True

    @dataclass
    class Phase2:
        """Models all required data fetched from RPC eth_calls to perform DKG round 2."""
        ritual: Coordinator.Ritual
        status: int
        aggregated: bool
        missing_transcripts: int

        @classmethod
        def fetch(
            cls,
            coordinator_agent,
            staking_provider: ChecksumAddress,
            ritual_id: int,
        ):
            """Execute all required RPC eth_calls to perform DKG round 2."""
            ritual = coordinator_agent.get_ritual(
                ritual_id=ritual_id,
                transcripts=True,
            )
            participant = ritual.get_participant(staking_provider)
            status = coordinator_agent.get_ritual_status(ritual_id=ritual.id)
            data = cls(
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
            if self.status != Coordinator.RitualStatus.DKG_AWAITING_AGGREGATIONS:
                # This verifies that the node is part of the ritual according to the
                # participant addresses dispatched from the EventScanner (StartRitual event).
                # This is an abnormal state.
                DKG.log.debug(
                    f"ritual #{self.ritual.id} is not waiting for aggregations; status={self.status}."
                )
                return False
            if self.aggregated:
                # This is a normal state, as the node may have already submitted an aggregated
                # transcript for this ritual, and it's not necessary to submit another one. Carry on.
                DKG.log.debug(
                    f"Node {operator_address} has already posted an aggregated transcript for ritual {self.ritual.id}."
                )
                return False
            if self.missing_transcripts:
                # This is a highly abnormal state, as it indicates that the node has not
                # received all the transcripts for the ritual but was dispatched to perform phase 2.
                # It's not possible to perform round 2 of the DKG protocol without all the transcripts available.
                message = (
                    f"Aggregation is not permitted because ritual #{self.ritual.id} is "
                    f"missing {self.missing_transcripts} transcripts."
                )
                DKG.log.critical(message)
                return False
            return True
