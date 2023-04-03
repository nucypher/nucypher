import time
from enum import Enum
from eth_typing import ChecksumAddress
from eth_utils import keccak
from typing import List

from nucypher.blockchain.eth.agents import CoordinatorAgent


class MockCoordinatorV1:

    SIGNALS = {}
    DKG_SIZE = 8

    Participant = CoordinatorAgent.Ritual.Participant
    Ritual = CoordinatorAgent.Ritual
    RitualStatus = CoordinatorAgent.Ritual.Status

    class Signal(Enum):
        START_RITUAL = 0
        START_TRANSCRIPT_ROUND = 1
        START_CONFIRMATION_ROUND = 2
        END_RITUAL = 3

    def __init__(self, transcripts_window: int, confirmations_window: int):
        self.transcripts_window = transcripts_window
        self.confirmations_window = confirmations_window
        self.rituals = {}

    def emit_signal(self, ritual_id: int, signal: Signal, **kwargs) -> None:
        self.SIGNALS[(int(time.time_ns()), ritual_id)] = (signal, {**kwargs, 'ritual_id': ritual_id})

    def number_of_rituals(self) -> int:
        return len(self.rituals)

    def initiate_ritual(
        self, initiator: ChecksumAddress, nodes: List[ChecksumAddress]
    ) -> None:
        if len(nodes) != self.DKG_SIZE:
            raise Exception('Invalid number of nodes')
        ritual = self.Ritual(
            id=len(self.rituals),
            init_timestamp=int(time.time_ns()),
            participants=[self.Participant(node=node) for node in nodes],
            dkg_size=len(nodes),
            initiator=initiator,
        )
        self.rituals[ritual.id] = ritual
        self.emit_signal(
            signal=self.Signal.START_RITUAL, ritual_id=ritual.id, nodes=nodes
        )
        self.emit_signal(
            signal=self.Signal.START_TRANSCRIPT_ROUND, ritual_id=ritual.id, nodes=nodes
        )

    def post_transcript(self, ritual_id: int, node_address: ChecksumAddress, node_index: int, transcript: bytes) -> None:
        ritual = self.rituals[ritual_id]
        # if ritual.status != self.RitualStatus.AWAITING_TRANSCRIPTS:
        #     raise Exception(f'ritual {ritual_id} is not waiting for transcripts')
        # if ritual.participants[node_index].node != node_address:
        #     raise Exception(f'{node_address} is not part of ritual #{ritual_id}')
        # if ritual.participants[node_index].transcript:
        #     raise Exception(f'{node_address} is not part of ritual #{ritual_id}')  # TODO: Wrong exception
        ritual.participants[node_index].transcript = keccak(transcript)
        ritual.total_transcripts += 1
        if ritual.total_transcripts == self.DKG_SIZE:
            ritual.status = self.RitualStatus.AWAITING_AGGREGATIONS
            self.emit_signal(
                signal=self.Signal.START_CONFIRMATION_ROUND,
                ritual_id=ritual_id,
                nodes=[p.node for p in ritual.participants],
            )

    def post_aggregation(self, ritual_id: int, node_address: ChecksumAddress, node_index: int, aggregated_transcript: bytes) -> None:
        ritual = self.rituals[ritual_id]
        # if ritual.status != self.RitualStatus.AWAITING_AGGREGATIONS:
        #     raise Exception(f'ritual {ritual_id} is not waiting for transcripts')
        # if ritual.participants[node_index].node != node_address:
        #     raise Exception(f'{node_address} is not part of ritual #{ritual_id}')
        # if ritual.participants[node_index].transcript:
        #     raise Exception(f'{node_address} is not part of ritual #{ritual_id}')  # TODO: Wrong exception
        ritual.participants[node_index].transcript = keccak(aggregated_transcript)
        ritual.total_transcripts += 1
        if ritual.total_transcripts == self.DKG_SIZE:
            ritual.status = self.RitualStatus.FINALIZED
            self.emit_signal(
                signal=self.Signal.END_RITUAL,
                ritual_id=ritual_id,
                nodes=[p.node for p in ritual.participants],
            )
