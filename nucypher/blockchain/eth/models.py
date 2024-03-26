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

from nucypher.types import PhaseNumber

PHASE1 = PhaseNumber(1)
PHASE2 = PhaseNumber(2)


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
        provider: ChecksumAddress
        aggregated: bool = False
        transcript: bytes = bytes()
        decryption_request_static_key: bytes = bytes()

        @classmethod
        def from_data(cls, data: list):
            return cls(
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
        def make_participants(data: list) -> Iterable["Coordinator.Participant"]:
            """Converts a list of participant data into an iterable of Participant objects."""
            for participant_data in data:
                participant = Coordinator.Participant.from_data(data=participant_data)
                yield participant
