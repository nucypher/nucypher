import time
from enum import Enum
from eth_typing import ChecksumAddress
from eth_utils import keccak
from typing import List

from nucypher.blockchain.eth.agents import CoordinatorAgent


class MockCoordinatorV1:

    SIGNALS = {}
    DKG_SIZE = 8

    Performance = CoordinatorAgent.Performance
    Ritual = CoordinatorAgent.Ritual
    RitualStatus = CoordinatorAgent.RitualStatus

    class Signal(Enum):
        START_RITUAL = 0
        START_TRANSCRIPT_ROUND = 1
        START_CONFIRMATION_ROUND = 2

    def __init__(self, transcripts_window: int, confirmations_window: int):
        self.transcripts_window = transcripts_window
        self.confirmations_window = confirmations_window
        self.rituals = {}

    def emit_signal(self, ritual_id: int, signal: Signal, **kwargs) -> None:
        self.SIGNALS[(int(time.time_ns()), ritual_id)] = (signal, {**kwargs, 'ritual_id': ritual_id})

    def number_of_rituals(self) -> int:
        return len(self.rituals)

    def initiate_ritual(self, nodes: List[ChecksumAddress]) -> None:
        if len(nodes) != self.DKG_SIZE:
            raise Exception('Invalid number of nodes')
        ritual = self.Ritual(
            id=len(self.rituals),
            init_timestamp=int(time.time_ns()),
            performances=[self.Performance(node=node) for node in nodes],
            status=self.RitualStatus.WAITING_FOR_CHECKINS
        )
        self.rituals[ritual.id] = ritual
        self.emit_signal(signal=self.Signal.START_RITUAL, ritual_id=ritual.id, nodes=nodes)

    def checkin(self, ritual_id: int, node_index: int) -> None:
        ritual = self.rituals[ritual_id]
        if ritual.status != self.RitualStatus.WAITING_FOR_CHECKINS:
            raise Exception(f'ritual {ritual_id} is not waiting for checkins')
        ritual.performances[node_index].checkin_timestamp = int(time.time_ns())
        ritual.total_checkins += 1
        if ritual.total_checkins == self.DKG_SIZE:
            ritual.status = self.RitualStatus.WAITING_FOR_TRANSCRIPTS
            self.emit_signal(signal=self.Signal.START_TRANSCRIPT_ROUND,
                             ritual_id=ritual_id,
                             nodes=[p.node for p in ritual.performances])

    def post_transcript(self, ritual_id: int, node_address: ChecksumAddress, node_index: int, transcript: bytes) -> None:
        ritual = self.rituals[ritual_id]
        if ritual.status != self.RitualStatus.WAITING_FOR_TRANSCRIPTS:
            raise Exception(f'ritual {ritual_id} is not waiting for transcripts')
        if ritual.performances[node_index].node != node_address:
            raise Exception(f'{node_address} is not part of ritual #{ritual_id}')
        if ritual.performances[node_index].transcript:
            raise Exception(f'{node_address} is not part of ritual #{ritual_id}')  # TODO: Wrong exception
        ritual.performances[node_index].transcript = keccak(transcript)
        ritual.total_transcripts += 1
        if ritual.total_transcripts == self.DKG_SIZE:
            ritual.status = self.RitualStatus.WAITING_FOR_CONFIRMATIONS
            self.emit_signal(signal=self.Signal.START_CONFIRMATION_ROUND,
                             ritual_id=ritual_id,
                             nodes=[p.node for p in ritual.performances])

    def post_confirmation(self,
                          ritual_id: int,
                          node_address: ChecksumAddress,
                          node_index: int,
                          confirmed_node_indexes: List[int]) -> None:
        ritual = self.rituals[ritual_id]
        if ritual.status != self.RitualStatus.WAITING_FOR_CONFIRMATIONS:
            raise Exception(f'ritual {ritual_id} is not waiting for confirmations')
        if ritual.performances[node_index].node != node_address:
            raise Exception(f'{node_address} is not part of ritual #{ritual_id}')
        if len(confirmed_node_indexes) > self.DKG_SIZE:
            raise Exception('Invalid number of confirmations')
        for index in confirmed_node_indexes:
            if index > self.DKG_SIZE:
                raise Exception('invalid node index')
            ritual.performances[index].confirmed_by.append(node_address)
        ritual.total_confirmations += 1
        if ritual.total_confirmations == self.DKG_SIZE:
            ritual.status = self.RitualStatus.COMPLETED
