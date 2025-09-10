import abc
from abc import abstractmethod
from collections import defaultdict
from typing import List, Optional

from atxm.tx import AsyncTx
from nucypher_core.ferveo import Validator

from nucypher.blockchain.eth.models import (
    DKG_PHASE_1,
    DKG_PHASE_2,
    HANDOVER_AWAITING_BLINDED_SHARE,
    HANDOVER_AWAITING_TRANSCRIPT,
    SIGNING_AWAITING_SIGNATURES,
    Coordinator,
)
from nucypher.types import PhaseId, PhaseNumber


class RitualStorage(abc.ABC):
    """A simple in-memory storage for ritual data"""

    _KEYS: List[str] = NotImplemented

    def __init__(self):
        self._data = defaultdict(dict)

    def clear(self, ritual_id):
        for key in self._KEYS:
            try:
                del self._data[key][ritual_id]
            except KeyError:
                continue

    #
    # DKG Phases
    #
    @classmethod
    @abstractmethod
    def _get_phase_key(cls, phase: PhaseNumber):
        raise NotImplementedError

    def store_ritual_phase_async_tx(self, phase_id: PhaseId, async_tx: AsyncTx):
        key = self._get_phase_key(phase_id.phase)
        self._data[key][phase_id.ritual_id] = async_tx

    def clear_ritual_phase_async_tx(self, phase_id: PhaseId, async_tx: AsyncTx) -> bool:
        key = self._get_phase_key(phase_id.phase)
        if self._data[key].get(phase_id.ritual_id) is async_tx:
            try:
                del self._data[key][phase_id.ritual_id]
                return True
            except KeyError:
                pass
        return False

    def get_ritual_phase_async_tx(self, phase_id: PhaseId) -> Optional[AsyncTx]:
        key = self._get_phase_key(phase_id.phase)
        return self._data[key].get(phase_id.ritual_id)

    # Metadata
    def _store_ritual_metadata(self, key: str, ritual_id: int, metadata) -> None:
        self._data[key][ritual_id] = metadata

    def _get_ritual_metadata(self, key: str, ritual_id: int) -> Optional[any]:
        metadata = self._data[key].get(ritual_id)
        return metadata

    def _clear_ritual_metadata(self, key: str, ritual_id: int) -> bool:
        try:
            del self._data[key][ritual_id]
            return True
        except KeyError:
            return False


class DKGStorage(RitualStorage):
    """A simple in-memory storage for DKG/Handover ritual data"""

    # round 1
    _KEY_PHASE_1_TXS = "phase_1_txs"
    _KEY_VALIDATORS = "validators"
    # round 2
    _KEY_PHASE_2_TXS = "phase_2_txs"
    # handover phases
    _KEY_PHASE_AWAITING_TRANSCRIPT_TXS = "handover_transcript_txs"
    _KEY_PHASE_AWAITING_BLINDED_SHARE_TXS = "handover_blinded_share_txs"
    # active rituals
    _KEY_ACTIVE_RITUAL = "active_rituals"

    _KEYS = [
        _KEY_PHASE_1_TXS,
        _KEY_VALIDATORS,
        _KEY_PHASE_2_TXS,
        _KEY_ACTIVE_RITUAL,
        _KEY_PHASE_AWAITING_TRANSCRIPT_TXS,
        _KEY_PHASE_AWAITING_BLINDED_SHARE_TXS,
    ]

    def __init__(self):
        super().__init__()

    #
    # DKG Phases
    #
    @classmethod
    def _get_phase_key(cls, phase: int):
        if phase == DKG_PHASE_1:
            return cls._KEY_PHASE_1_TXS
        elif phase == DKG_PHASE_2:
            return cls._KEY_PHASE_2_TXS
        elif phase == HANDOVER_AWAITING_TRANSCRIPT:
            return cls._KEY_PHASE_AWAITING_TRANSCRIPT_TXS
        elif phase == HANDOVER_AWAITING_BLINDED_SHARE:
            return cls._KEY_PHASE_AWAITING_BLINDED_SHARE_TXS
        else:
            raise ValueError(f"Unknown phase: {phase}")

    # Validators for rituals
    def store_validators(self, ritual_id: int, validators: List[Validator]) -> None:
        self._store_ritual_metadata(self._KEY_VALIDATORS, ritual_id, list(validators))

    def get_validators(self, ritual_id: int) -> Optional[List[Validator]]:
        validators = self._get_ritual_metadata(self._KEY_VALIDATORS, ritual_id)
        if not validators:
            return None

        return list(validators)  # return a copy of the list

    def clear_validators(self, ritual_id: int) -> bool:
        return self._clear_ritual_metadata(self._KEY_VALIDATORS, ritual_id)

    #
    # Active Rituals
    #
    def store_active_ritual(self, active_ritual: Coordinator.Ritual) -> None:
        if active_ritual.total_aggregations != active_ritual.dkg_size:
            # safeguard against a non-active ritual being cached
            raise ValueError("Only active rituals can be cached")

        self._store_ritual_metadata(
            self._KEY_ACTIVE_RITUAL, active_ritual.id, active_ritual
        )

    def get_active_ritual(self, ritual_id: int) -> Optional[Coordinator.Ritual]:
        return self._get_ritual_metadata(self._KEY_ACTIVE_RITUAL, ritual_id)

    def clear_active_ritual_object(self, ritual_id: int) -> bool:
        return self._clear_ritual_metadata(self._KEY_ACTIVE_RITUAL, ritual_id)


class SigningRitualStorage(RitualStorage):
    """A simple in-memory storage for Signing Ritual data"""

    _KEY_PHASE_POST_SIGNATURE_TXS = "post_signature_txs"

    _KEYS = [
        _KEY_PHASE_POST_SIGNATURE_TXS,
    ]

    def __init__(self):
        super().__init__()

    #
    # Signing Phases
    #
    @classmethod
    def _get_phase_key(cls, phase: int):
        if phase == SIGNING_AWAITING_SIGNATURES:
            return cls._KEY_PHASE_POST_SIGNATURE_TXS
        else:
            raise ValueError(f"Unknown phase: {phase}")
