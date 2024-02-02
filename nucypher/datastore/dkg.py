from collections import defaultdict
from typing import List, Optional, Union

from hexbytes import HexBytes
from nucypher_core.ferveo import (
    AggregatedTranscript,
    DecryptionSharePrecomputed,
    DecryptionShareSimple,
    Validator,
)


class DKGStorage:
    """A simple in-memory storage for DKG data"""

    # round 1
    KEY_TRANSCRIPT_TXS = "transcript_tx_hashes"
    KEY_VALIDATORS = "validators"
    # round 2
    KEY_AGGREGATED_TXS = "aggregation_tx_hashes"
    KEY_AGGREGATED_TRANSCRIPTS = "aggregated_transcripts"
    # active rituals
    KEY_DECRYPTION_SHARE = "decryption_share"

    _KEYS = [
        KEY_TRANSCRIPT_TXS,
        KEY_VALIDATORS,
        KEY_AGGREGATED_TXS,
        KEY_AGGREGATED_TRANSCRIPTS,
        KEY_DECRYPTION_SHARE,
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
    def store_aggregated_transcript(
        self, ritual_id: int, aggregated_transcript: AggregatedTranscript
    ) -> None:
        self.data[self.KEY_AGGREGATED_TRANSCRIPTS][ritual_id] = bytes(
            aggregated_transcript
        )

    def get_aggregated_transcript(
        self, ritual_id: int
    ) -> Optional[AggregatedTranscript]:
        data = self.data[self.KEY_AGGREGATED_TRANSCRIPTS].get(ritual_id)
        if not data:
            return None

        aggregated_transcript = AggregatedTranscript.from_bytes(data)
        return aggregated_transcript

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
    def store_decryption_share(
        self,
        ritual_id: int,
        decryption_share: Union[DecryptionShareSimple, DecryptionSharePrecomputed],
    ) -> None:
        self.data[self.KEY_DECRYPTION_SHARE][ritual_id] = decryption_share

    def get_decryption_share(
        self, ritual_id: int
    ) -> Optional[Union[DecryptionShareSimple, DecryptionSharePrecomputed]]:
        return self.data[self.KEY_DECRYPTION_SHARE].get(ritual_id)
