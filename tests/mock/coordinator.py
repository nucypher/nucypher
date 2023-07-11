import time
from enum import Enum
from typing import Dict, List

from eth_typing import ChecksumAddress
from eth_utils import keccak
from nucypher_core import SessionStaticKey
from nucypher_core.ferveo import AggregatedTranscript, DkgPublicKey, Transcript
from web3.types import TxReceipt

from nucypher.blockchain.eth.agents import CoordinatorAgent
from nucypher.crypto.powers import TransactingPower
from tests.mock.agents import MockContractAgent
from tests.mock.interfaces import MockBlockchain


class MockCoordinatorAgent(MockContractAgent):

    Participant = CoordinatorAgent.Ritual.Participant
    Ritual = CoordinatorAgent.Ritual
    RitualStatus = CoordinatorAgent.Ritual.Status
    G1Point = CoordinatorAgent.Ritual.G1Point

    EVENTS = {}
    rituals = []

    class Events(Enum):
        START_RITUAL = 0
        START_AGGREGATION_ROUND = 1

    def __init__(self, blockchain: MockBlockchain, max_dkg_size: int = 64, timeout: int = 600):
        self.blockchain = blockchain
        self.timeout = timeout
        self.max_dkg_size = max_dkg_size
        # Note that the call to super() is not necessary here

        self._operator_to_staking_provider = {}

    def _add_operator_to_staking_provider_mapping(
        self, mapping: Dict[ChecksumAddress, ChecksumAddress]
    ):
        self._operator_to_staking_provider.update(mapping)

    def _get_staking_provider_from_operator(self, operator: ChecksumAddress):
        try:
            return self._operator_to_staking_provider[operator]
        except KeyError:
            return None

    def emit_event(self, ritual_id: int, signal: Events, **kwargs) -> None:
        self.EVENTS[(int(time.time_ns()), ritual_id)] = (signal, {**kwargs, 'ritual_id': ritual_id})

    def reset(self, **kwargs) -> None:
        # self.rituals = []
        # self.EVENTS = {}
        self._operator_to_staking_provider = {}

    #
    # Transactions
    #

    def initiate_ritual(
        self, providers: List[ChecksumAddress], transacting_power: TransactingPower
    ) -> TxReceipt:
        ritual_id = len(self.rituals)
        ritual = self.Ritual(
            init_timestamp=int(time.time_ns()),
            participants=[
                self.Participant(provider=provider) for provider in providers
            ],
            dkg_size=len(providers),
            initiator=transacting_power.account,
        )
        self.rituals.append(ritual)
        self.emit_event(
            signal=self.Events.START_RITUAL,
            ritual_id=ritual_id,
            initiator=transacting_power.account,
            participants=providers,
        )
        return self.blockchain.FAKE_RECEIPT

    def post_transcript(
        self,
        ritual_id: int,
        transcript: Transcript,
        transacting_power: TransactingPower,
        fire_and_forget: bool = False,
    ) -> TxReceipt:
        ritual = self.rituals[ritual_id]
        operator_address = transacting_power.account
        # either mapping is populated or just assume provider same as operator for testing
        provider = (
            self._get_staking_provider_from_operator(operator=operator_address)
            or transacting_power.account
        )
        participant = self.get_participant_from_provider(ritual_id, provider)
        participant.transcript = bytes(transcript)
        ritual.total_transcripts += 1
        if ritual.total_transcripts == ritual.dkg_size:
            ritual.status = self.RitualStatus.AWAITING_AGGREGATIONS
            self.emit_event(
                signal=self.Events.START_AGGREGATION_ROUND,
                ritual_id=ritual_id,
                participants=[
                    p.provider for p in ritual.participants
                ],  # TODO This should not be
            )
        return self.blockchain.FAKE_RECEIPT

    def post_aggregation(
        self,
        ritual_id: int,
        aggregated_transcript: AggregatedTranscript,
        public_key: DkgPublicKey,
        participant_public_key: SessionStaticKey,
        transacting_power: TransactingPower,
        fire_and_forget: bool = False,
    ) -> TxReceipt:
        ritual = self.rituals[ritual_id]
        operator_address = transacting_power.account
        # either mapping is populated or just assume provider same as operator for testing
        provider = (
            self._get_staking_provider_from_operator(operator=operator_address)
            or transacting_power.account
        )
        participant = self.get_participant_from_provider(ritual_id, provider)
        participant.aggregated = True
        participant.decryption_request_static_key = bytes(participant_public_key)

        g1_point = self.Ritual.G1Point.from_dkg_public_key(public_key)
        if len(ritual.aggregated_transcript) == 0:
            ritual.aggregated_transcript = bytes(aggregated_transcript)
            ritual.public_key = g1_point
        elif bytes(ritual.public_key) != bytes(g1_point) or keccak(
            ritual.aggregated_transcript
        ) != keccak(bytes(aggregated_transcript)):
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

    def get_participant_from_provider(
        self, ritual_id: int, provider: ChecksumAddress
    ) -> Ritual.Participant:
        for p in self.rituals[ritual_id].participants:
            if p.provider == provider:
                return p

        raise ValueError(f"Provider {provider} not found for ritual #{ritual_id}")

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

    def get_ritual_public_key(self, ritual_id: int) -> DkgPublicKey:
        if self.get_ritual_status(ritual_id=ritual_id) != self.RitualStatus.FINALIZED:
            # TODO should we raise here instead?
            return None

        ritual = self.get_ritual(ritual_id=ritual_id)
        if not ritual.public_key:
            return None

        return ritual.public_key.to_dkg_public_key()
