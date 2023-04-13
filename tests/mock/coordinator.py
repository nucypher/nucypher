import time
from enum import Enum
from eth_typing import ChecksumAddress
from eth_utils import keccak
from ferveo_py import PublicKey
from typing import List

from nucypher.blockchain.eth.agents import CoordinatorAgent
from nucypher.crypto.powers import TransactingPower
from tests.mock.interfaces import MockBlockchain


class MockCoordinatorV1:

    SIGNALS = {}

    Participant = CoordinatorAgent.Ritual.Participant
    Ritual = CoordinatorAgent.Ritual
    RitualStatus = CoordinatorAgent.Ritual.Status

    class Signal(Enum):
        START_TRANSCRIPT_ROUND = 0
        START_AGGREGATION_ROUND = 1

    def __init__(self, testerchain: MockBlockchain):
        self.testerchain = testerchain
        self.rituals = {}
        self.timeout = 600

    def emit_signal(self, ritual_id: int, signal: Signal, **kwargs) -> None:
        self.SIGNALS[(int(time.time_ns()), ritual_id)] = (signal, {**kwargs, 'ritual_id': ritual_id})

    def number_of_rituals(self) -> int:
        return len(self.rituals)

    def initiate_ritual(
        self, nodes: List[ChecksumAddress], transacting_power: TransactingPower
    ) -> None:
        ritual = self.Ritual(
            id=len(self.rituals),
            init_timestamp=int(time.time_ns()),
            participants=[self.Participant(node=node) for node in nodes],
            dkg_size=len(nodes),
            initiator=transacting_power.account,
        )
        self.rituals[ritual.id] = ritual
        self.emit_signal(
            signal=self.Signal.START_TRANSCRIPT_ROUND, ritual_id=ritual.id, nodes=nodes
        )

    def post_transcript(self, ritual_id: int, node_index: int, transcript: bytes, transacting_power: TransactingPower) -> None:
        ritual = self.rituals[ritual_id]
        ritual.participants[node_index].transcript = transcript
        ritual.total_transcripts += 1
        if ritual.total_transcripts == ritual.dkg_size:
            ritual.status = self.RitualStatus.AWAITING_AGGREGATIONS
            self.emit_signal(
                signal=self.Signal.START_AGGREGATION_ROUND,
                ritual_id=ritual_id,
                nodes=[p.node for p in ritual.participants],
            )
        return self.testerchain.FAKE_RECEIPT

    def post_aggregation(self, ritual_id: int, node_index: int, aggregated_transcript: bytes, transacting_power: TransactingPower) -> None:
        ritual = self.rituals[ritual_id]
        ritual.participants[node_index].aggregated_transcript = aggregated_transcript
        ritual.participants[node_index].aggregated_transcript_hash = keccak(aggregated_transcript)
        ritual.total_aggregations += 1
        return self.testerchain.FAKE_RECEIPT

    def get_ritual(self, ritual_id: int, with_participants: bool = False) -> CoordinatorAgent.Ritual:
        return self.rituals[ritual_id]

    def get_participants(self, ritual_id: int) -> List[ChecksumAddress]:
        return [p.node for p in self.rituals[ritual_id].participants]

    def get_node_index(self, ritual_id: int, node: ChecksumAddress) -> int:
        return self.get_participants(ritual_id).index(node)

    def post_public_key(self, ritual_id: int, public_key: PublicKey, transacting_power: TransactingPower) -> None:
        ritual = self.rituals[ritual_id]
        ritual.public_key = public_key
        return self.testerchain.FAKE_RECEIPT

    def get_ritual_status(self, ritual_id: int) -> int:
        ritual = self.rituals[ritual_id]
        timestamp = int(ritual.init_timestamp)
        deadline = timestamp + self.timeout
        if timestamp == 0:
            return self.RitualStatus.NOT_INITIATED
        elif ritual.public_key is not None:
            return self.RitualStatus.FINALIZED
        elif ritual.total_aggregations == ritual.dkg_size:
            return self.RitualStatus.FINALIZED
        elif ritual.aggregation_mismatch:
            return self.RitualStatus.AGGREGATION_MISMATCH
        elif timestamp > deadline:
            return self.RitualStatus.TIMEOUT
        elif ritual.total_transcripts < ritual.dkg_size:
            return self.RitualStatus.AWAITING_TRANSCRIPTS
        elif ritual.total_aggregations < ritual.dkg_size:
            return self.RitualStatus.AWAITING_AGGREGATIONS
        else:
            raise RuntimeError(f"Ritual {ritual_id} is in an unknown state")  # :-(

    def reset(self) -> None:
        self.rituals = {}
        self.SIGNALS = {}
