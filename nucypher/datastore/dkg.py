from collections import defaultdict
from typing import List, Optional

from hexbytes import HexBytes
from nucypher_core.ferveo import (
    Validator,
)

from nucypher.blockchain.eth.models import Coordinator


class DKGStorage:
    """A simple in-memory storage for DKG data"""

    # round 1
    KEY_TRANSCRIPT_TXS = "transcript_tx_hashes"
    KEY_VALIDATORS = "validators"
    # round 2
    KEY_AGGREGATED_TXS = "aggregation_tx_hashes"
    # active rituals
    KEY_ACTIVE_RITUAL = "active_rituals"

    _KEYS = [
        KEY_TRANSCRIPT_TXS,
        KEY_VALIDATORS,
        KEY_AGGREGATED_TXS,
        KEY_ACTIVE_RITUAL,
    ]

    def __init__(self):
        self.data = defaultdict(dict)

    def clear(self, ritual_id):
        for key in self._KEYS:
            try:
                del self.data[key][ritual_id]
            except KeyError:
                continue

    #
    # DKG Round 1 - Transcripts
    #
    def store_transcript_txhash(self, ritual_id: int, txhash: HexBytes) -> None:
        self.data[self.KEY_TRANSCRIPT_TXS][ritual_id] = txhash

    def clear_transcript_txhash(self, ritual_id: int, txhash: HexBytes) -> bool:
        if self.get_transcript_txhash(ritual_id) == txhash:
            del self.data[self.KEY_TRANSCRIPT_TXS][ritual_id]
            return True
        return False

    def get_transcript_txhash(self, ritual_id: int) -> Optional[HexBytes]:
        return self.data[self.KEY_TRANSCRIPT_TXS].get(ritual_id)

    def store_validators(self, ritual_id: int, validators: List[Validator]) -> None:
        self.data[self.KEY_VALIDATORS][ritual_id] = list(validators)

    def get_validators(self, ritual_id: int) -> Optional[List[Validator]]:
        validators = self.data[self.KEY_VALIDATORS].get(ritual_id)
        if not validators:
            return None

        return list(validators)

    #
    # DKG Round 2 - Aggregation
    #
    def store_aggregation_txhash(self, ritual_id: int, txhash: HexBytes) -> None:
        self.data[self.KEY_AGGREGATED_TXS][ritual_id] = txhash

    def clear_aggregated_txhash(self, ritual_id: int, txhash: HexBytes) -> bool:
        if self.get_aggregation_txhash(ritual_id) == txhash:
            del self.data[self.KEY_AGGREGATED_TXS][ritual_id]
            return True
        return False

    def get_aggregation_txhash(self, ritual_id: int) -> Optional[HexBytes]:
        return self.data[self.KEY_AGGREGATED_TXS].get(ritual_id)

    #
    # Active Rituals
    #
    def store_active_ritual(self, active_ritual: Coordinator.Ritual) -> None:
        if active_ritual.total_aggregations != active_ritual.dkg_size:
            # safeguard against a non-active ritual being cached
            raise ValueError("Only active rituals can be cached")
        self.data[self.KEY_ACTIVE_RITUAL][active_ritual.id] = active_ritual

    def get_active_ritual(self, ritual_id: int) -> Optional[Coordinator.Ritual]:
        return self.data[self.KEY_ACTIVE_RITUAL].get(ritual_id)
