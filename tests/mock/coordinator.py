import time
from copy import deepcopy
from enum import Enum
from typing import Dict, List, NamedTuple, Optional

from eth_typing import ChecksumAddress
from eth_utils import keccak
from nucypher_core import SessionStaticKey
from nucypher_core.ferveo import (
    AggregatedTranscript,
    DkgPublicKey,
    FerveoPublicKey,
    Transcript,
)
from web3.types import TxReceipt

from nucypher.blockchain.eth.interfaces import BlockchainInterface
from nucypher.blockchain.eth.models import Coordinator, Ferveo
from nucypher.crypto.powers import TransactingPower
from tests.mock.agents import MockContractAgent
from tests.mock.interfaces import MockBlockchain


class MockCoordinatorAgent(MockContractAgent):

    Participant = Coordinator.Participant
    Ritual = Coordinator.Ritual
    RitualStatus = Coordinator.RitualStatus
    G1Point = Ferveo.G1Point
    G2Point = Ferveo.G2Point

    class ParticipantKey(NamedTuple):
        lastRitualId: int
        publicKey: Ferveo.G2Point

    EVENTS = {}
    _rituals = []

    class Events(Enum):
        START_RITUAL = 0
        START_AGGREGATION_ROUND = 1

    def __init__(self, blockchain: MockBlockchain, max_dkg_size: int = 64, timeout: int = 600):
        self.blockchain = blockchain
        self.timeout = timeout
        self.max_dkg_size = max_dkg_size
        # Note that the call to super() is not necessary here

        self._operator_to_staking_provider = {}
        self._participant_keys_history = {}

    def _add_operator_to_staking_provider_mapping(
        self, mapping: Dict[ChecksumAddress, ChecksumAddress]
    ):
        self._operator_to_staking_provider.update(mapping)

    def _get_staking_provider_from_operator(self, operator: ChecksumAddress):
        try:
            return self._operator_to_staking_provider[operator]
        except KeyError:
            return None

    @classmethod
    def get_threshold_for_ritual_size(cls, dkg_size: int):
        # default is simple (same as Coordinator contract)
        return dkg_size // 2 + 1

    def emit_event(self, ritual_id: int, signal: Events, **kwargs) -> None:
        self.EVENTS[(int(time.time_ns()), ritual_id)] = (signal, {**kwargs, 'ritual_id': ritual_id})

    def reset(self, **kwargs) -> None:
        # self.rituals = []
        # self.EVENTS = {}
        self._operator_to_staking_provider = {}

    #
    # Transactions - modify state
    #

    def __find_participant_for_state_change(self, ritual_id, provider) -> Participant:
        for p in self._rituals[ritual_id].participants:
            if p.provider == provider:
                return p

        raise ValueError("participant not found")

    def initiate_ritual(
        self,
        fee_model: ChecksumAddress,
        providers: List[ChecksumAddress],
        authority: ChecksumAddress,
        duration: int,
        access_controller: ChecksumAddress,
        transacting_power: TransactingPower,
    ) -> TxReceipt:
        ritual_id = len(self._rituals)
        init_timestamp = int(time.time_ns())
        end_timestamp = init_timestamp + duration
        ritual = self.Ritual(
            id=ritual_id,
            initiator=transacting_power.account,
            authority=authority,
            access_controller=access_controller,
            init_timestamp=init_timestamp,
            end_timestamp=end_timestamp,
            participants=[
                self.Participant(provider=provider) for provider in providers
            ],
            dkg_size=len(providers),
            threshold=self.get_threshold_for_ritual_size(len(providers)),
            fee_model=fee_model,
        )
        self._rituals.append(ritual)
        self.emit_event(
            signal=self.Events.START_RITUAL,
            ritual_id=ritual_id,
            authority=authority,
            participants=providers,
        )
        return self.blockchain.FAKE_RECEIPT

    def post_transcript(
        self,
        ritual_id: int,
        transcript: Transcript,
        transacting_power: TransactingPower,
        async_tx_hooks: BlockchainInterface.AsyncTxHooks,
    ) -> TxReceipt:
        ritual = self._rituals[ritual_id]
        operator_address = transacting_power.account
        # either mapping is populated or just assume provider same as operator for testing
        provider = (
            self._get_staking_provider_from_operator(operator=operator_address)
            or transacting_power.account
        )
        participant = self.__find_participant_for_state_change(ritual_id, provider)
        participant.transcript = bytes(transcript)
        ritual.total_transcripts += 1
        if ritual.total_transcripts == ritual.dkg_size:
            ritual.status = self.RitualStatus.DKG_AWAITING_AGGREGATIONS
            self.emit_event(
                signal=self.Events.START_AGGREGATION_ROUND,
                ritual_id=ritual_id,
                participants=[
                    p.provider for p in ritual.participants
                ],  # TODO This should not be
            )
        return self.blockchain.mock_async_tx(async_tx_hooks)

    def post_aggregation(
        self,
        ritual_id: int,
        aggregated_transcript: AggregatedTranscript,
        public_key: DkgPublicKey,
        participant_public_key: SessionStaticKey,
        transacting_power: TransactingPower,
        async_tx_hooks: BlockchainInterface.AsyncTxHooks,
    ) -> TxReceipt:
        ritual = self._rituals[ritual_id]
        operator_address = transacting_power.account
        # either mapping is populated or just assume provider same as operator for testing
        provider = (
            self._get_staking_provider_from_operator(operator=operator_address)
            or transacting_power.account
        )
        participant = self.__find_participant_for_state_change(ritual_id, provider)
        participant.aggregated = True
        participant.decryption_request_static_key = bytes(participant_public_key)

        g1_point = self.G1Point.from_dkg_public_key(public_key)
        if len(ritual.aggregated_transcript) == 0:
            ritual.aggregated_transcript = bytes(aggregated_transcript)
            ritual.public_key = g1_point
        elif bytes(ritual.public_key) != bytes(g1_point) or keccak(
            ritual.aggregated_transcript
        ) != keccak(bytes(aggregated_transcript)):
            ritual.aggregation_mismatch = True
            # don't increment aggregations
            # TODO Emit EndRitual here?
            return self.blockchain.mock_async_tx(async_tx_hooks)

        ritual.total_aggregations += 1
        return self.blockchain.mock_async_tx(async_tx_hooks)

    def set_provider_public_key(
        self, public_key: FerveoPublicKey, transacting_power: TransactingPower
    ) -> TxReceipt:
        operator_address = transacting_power.account
        # either mapping is populated or just assume provider same as operator for testing
        provider_address = (
            self._get_staking_provider_from_operator(operator=operator_address)
            or transacting_power.account
        )

        participant_keys = self._participant_keys_history.get(provider_address)
        if not participant_keys:
            participant_keys = []
            self._participant_keys_history[provider_address] = participant_keys

        participant_keys.append(
            self.ParticipantKey(
                lastRitualId=self.number_of_rituals(),
                publicKey=self.G2Point.from_public_key(public_key),
            )
        )

        return self.blockchain.FAKE_RECEIPT

    #
    # Read Calls - don't change state (only use copies of objects)
    #

    def is_provider_public_key_set(self, staking_provider: ChecksumAddress) -> bool:
        return staking_provider in self._participant_keys_history

    def get_timeout(self) -> int:
        return self.timeout

    def number_of_rituals(self) -> int:
        return len(self._rituals)

    def get_ritual(
        self, ritual_id: int, transcripts: bool = False
    ) -> Coordinator.Ritual:
        ritual = self._rituals[ritual_id]
        # return a copy of the ritual object; the original value is used for state
        copied_ritual = deepcopy(ritual)
        if not transcripts:
            for participant in copied_ritual.participants:
                participant.transcript = bytes()
        return copied_ritual

    def is_participant(self, ritual_id: int, provider: ChecksumAddress) -> bool:
        try:
            self.get_participant(ritual_id, provider, False)
            return True
        except ValueError:
            return False

    def get_participant(
        self, ritual_id: int, provider: ChecksumAddress, transcript: bool = False
    ) -> Participant:
        for p in self._rituals[ritual_id].participants:
            if p.provider == provider:
                copied_participant = deepcopy(p)
                if not transcript:
                    copied_participant.transcript = bytes()
                return copied_participant
        raise ValueError(f"Provider {provider} not found for ritual #{ritual_id}")

    def get_providers(self, ritual_id: int) -> List[ChecksumAddress]:
        return [p.provider for p in self._rituals[ritual_id].participants]

    def get_ritual_status(self, ritual_id: int) -> int:
        ritual = self._rituals[ritual_id]
        timestamp = int(ritual.init_timestamp)
        deadline = timestamp + self.timeout
        if timestamp == 0:
            return self.RitualStatus.NON_INITIATED
        elif ritual.total_aggregations == ritual.dkg_size:
            if time.time() <= ritual.end_timestamp:
                return self.RitualStatus.ACTIVE
            else:
                return self.RitualStatus.EXPIRED
        elif ritual.aggregation_mismatch:
            return self.RitualStatus.DKG_INVALID
        elif timestamp > deadline:
            return self.RitualStatus.DKG_TIMEOUT
        elif ritual.total_transcripts < ritual.dkg_size:
            return self.RitualStatus.DKG_AWAITING_TRANSCRIPTS
        elif ritual.total_aggregations < ritual.dkg_size:
            return self.RitualStatus.DKG_AWAITING_AGGREGATIONS
        else:
            raise RuntimeError(f"Ritual {ritual_id} is in an unknown state")  # :-(

    def is_ritual_active(self, ritual_id: int) -> bool:
        result = self.get_ritual_status(ritual_id)
        return result == self.RitualStatus.ACTIVE

    def get_ritual_id_from_public_key(self, public_key: DkgPublicKey) -> int:
        for i, ritual in enumerate(self._rituals):
            if bytes(ritual.public_key) == bytes(public_key):
                return i

        raise ValueError(
            f"No ritual id found for public key 0x{bytes(public_key).hex()}"
        )

    def get_ritual_public_key(self, ritual_id: int) -> Optional[DkgPublicKey]:
        status = self.get_ritual_status(ritual_id=ritual_id)
        if (
            status != Coordinator.RitualStatus.ACTIVE
            and status != Coordinator.RitualStatus.EXPIRED
        ):
            # TODO should we raise here instead?
            return None

        ritual = self.get_ritual(ritual_id=ritual_id)
        if not ritual.public_key:
            return None

        return ritual.public_key.to_dkg_public_key()

    def get_provider_public_key(
        self, provider: ChecksumAddress, ritual_id: int
    ) -> FerveoPublicKey:
        participant_keys = self._participant_keys_history[provider]
        for participant_key in reversed(participant_keys):
            if participant_key.lastRitualId <= ritual_id:
                g2_point = participant_key.publicKey
                return g2_point.to_public_key()

        raise ValueError(
            f"Public key not found for provider {provider} for ritual #{ritual_id}"
        )

    def is_encryption_authorized(
        self, ritual_id: int, evidence: bytes, ciphertext_header: bytes
    ) -> bool:
        # always allow
        return True
