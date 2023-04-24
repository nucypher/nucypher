import time
from enum import Enum
from eth_typing import ChecksumAddress
from eth_utils import keccak
from ferveo_py import PublicKey
from typing import List
from web3.types import TxReceipt

from nucypher.blockchain.eth.agents import CoordinatorAgent
from nucypher.crypto.powers import TransactingPower
from tests.mock.agents import MockContractAgent
from tests.mock.interfaces import MockBlockchain


class MockCoordinatorAgent(MockContractAgent):

    Participant = CoordinatorAgent.Ritual.Participant
    Ritual = CoordinatorAgent.Ritual
    RitualStatus = CoordinatorAgent.Ritual.Status

    PUBLIC_KEY_SIZE = 104  # TODO get from contract / ferveo (ferveo #99)
    EVENTS = {}

    class Events(Enum):
        START_RITUAL = 0
        START_AGGREGATION_ROUND = 1

    def __init__(self, blockchain: MockBlockchain, max_dkg_size: int = 64, timeout: int = 600):
        self.blockchain = blockchain
        self.rituals = {}
        self.timeout = timeout
        self.max_dkg_size = max_dkg_size
        # Note that the call to super() is not necessary here

    def emit_event(self, ritual_id: int, signal: Events, **kwargs) -> None:
        self.EVENTS[(int(time.time_ns()), ritual_id)] = (signal, {**kwargs, 'ritual_id': ritual_id})

    def reset(self, **kwargs) -> None:
        # self.rituals = {}
        # self.EVENTS = {}
        pass

    #
    # Transactions
    #

    def initiate_ritual(
        self, nodes: List[ChecksumAddress], transacting_power: TransactingPower
    ) -> TxReceipt:
        ritual = self.Ritual(
            id=len(self.rituals),
            init_timestamp=int(time.time_ns()),
            participants=[self.Participant(node=node) for node in nodes],
            dkg_size=len(nodes),
            initiator=transacting_power.account,
        )
        self.rituals[ritual.id] = ritual
        self.emit_event(
            signal=self.Events.START_RITUAL,
            ritual_id=ritual.id,
            initiator=transacting_power.account,
            nodes=nodes,
        )
        return self.blockchain.FAKE_RECEIPT

    def post_transcript(
            self,
            ritual_id: int,
            node_index: int,
            transcript: bytes,
            transacting_power: TransactingPower
    ) -> TxReceipt:
        ritual = self.rituals[ritual_id]
        ritual.participants[node_index].transcript = transcript
        ritual.total_transcripts += 1
        if ritual.total_transcripts >= ritual.dkg_size:
            ritual.status = self.RitualStatus.AWAITING_AGGREGATIONS
            self.emit_event(
                signal=self.Events.START_AGGREGATION_ROUND,
                ritual_id=ritual_id,
                nodes=[p.node for p in ritual.participants],
            )
        return self.blockchain.FAKE_RECEIPT

    def post_aggregation(
        self,
        ritual_id: int,
        node_index: int,
        aggregated_transcript: bytes,
        public_key: PublicKey,
        transacting_power: TransactingPower,
    ) -> TxReceipt:
        ritual = self.rituals[ritual_id]

        aggregated_transcript_hash = keccak(aggregated_transcript)
        public_key_hash = keccak(bytes(public_key))

        if len(ritual.aggregated_transcript) == 0 and len(ritual.public_key) == 0:
            ritual.aggregated_transcript = aggregated_transcript
            ritual.aggregated_transcript_hash = aggregated_transcript_hash
            ritual.public_key = public_key
            ritual.public_key_hash = public_key_hash
        elif (
            ritual.aggregated_transcript_hash != aggregated_transcript_hash
            or ritual.public_key_hash != public_key_hash
        ):
            ritual.aggregation_mismatch = True
            # don't increment aggregations
            # TODO Emit EndRitual here?
            return self.blockchain.FAKE_RECEIPT

        ritual.total_aggregations += 1
        return self.blockchain.FAKE_RECEIPT

    #
    # Calls
    #

    def get_timeout(self) -> int:
        return self.timeout

    def number_of_rituals(self) -> int:
        return len(self.rituals)

    def get_ritual(
        self, ritual_id: int, with_participants: bool = True
    ) -> CoordinatorAgent.Ritual:
        return self.rituals[ritual_id]

    def get_participants(self, ritual_id: int) -> List[Ritual.Participant]:
        return self.rituals[ritual_id].participants

    def get_node_index(self, ritual_id: int, node: ChecksumAddress) -> int:
        for i, p in enumerate(self.get_participants(ritual_id)):
            if p.node == node:
                return i

        raise ValueError(f"{node} not in list")

    def get_ritual_status(self, ritual_id: int) -> int:
        ritual = self.rituals[ritual_id]
        timestamp = int(ritual.init_timestamp)
        deadline = timestamp + self.timeout
        if timestamp == 0:
            return self.RitualStatus.NON_INITIATED
        elif ritual.total_aggregations == ritual.dkg_size:
            return self.RitualStatus.FINALIZED
        elif ritual.aggregation_mismatch:
            return self.RitualStatus.INVALID
        elif timestamp > deadline:
            return self.RitualStatus.TIMEOUT
        elif ritual.total_transcripts < ritual.dkg_size:
            return self.RitualStatus.AWAITING_TRANSCRIPTS
        elif ritual.total_aggregations < ritual.dkg_size:
            return self.RitualStatus.AWAITING_AGGREGATIONS
        else:
            raise RuntimeError(f"Ritual {ritual_id} is in an unknown state")  # :-(
