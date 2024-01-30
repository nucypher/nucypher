from collections import defaultdict
from typing import Optional

from hexbytes import HexBytes
from nucypher_core.ferveo import AggregatedTranscript, Transcript


class DKGStorage:
    """A simple in-memory storage for DKG data"""

    def __init__(self):
        self.data = defaultdict(dict)

    def store_transcript(self, ritual_id: int, transcript: Transcript) -> None:
        self.data["transcripts"][ritual_id] = bytes(transcript)

    def get_transcript(self, ritual_id: int) -> Optional[Transcript]:
        data = self.data["transcripts"].get(ritual_id)
        if not data:
            return None
        transcript = Transcript.from_bytes(data)
        return transcript

    def store_transcript_txhash(self, ritual_id: int, txhash: HexBytes) -> None:
        self.data["transcript_tx_hashes"][ritual_id] = txhash

    def clear_transcript_txhash(self, ritual_id: int, txhash: HexBytes):
        if self.get_transcript_txhash(ritual_id) == txhash:
            del self.data["transcript_tx_hashes"][ritual_id]

    def get_transcript_txhash(self, ritual_id: int) -> Optional[HexBytes]:
        return self.data["transcript_tx_hashes"].get(ritual_id)

    def store_aggregated_transcript(self, ritual_id: int, aggregated_transcript: AggregatedTranscript) -> None:
        self.data["aggregated_transcripts"][ritual_id] = bytes(aggregated_transcript)

    def get_aggregated_transcript(
        self, ritual_id: int
    ) -> Optional[AggregatedTranscript]:
        data = self.data["aggregated_transcripts"].get(ritual_id)
        if not data:
            return None

        aggregated_transcript = AggregatedTranscript.from_bytes(data)
        return aggregated_transcript

    def store_aggregation_txhash(self, ritual_id: int, txhash: HexBytes) -> None:
        self.data["aggregation_tx_hashes"][ritual_id] = txhash

    def clear_aggregated_txhash(self, ritual_id: int, txhash: HexBytes):
        if self.get_aggregation_txhash(ritual_id) == txhash:
            del self.data["aggregation_tx_hashes"][ritual_id]

    def get_aggregation_txhash(self, ritual_id: int) -> Optional[HexBytes]:
        return self.data["aggregation_tx_hashes"].get(ritual_id)

    def store_public_key(self, ritual_id: int, public_key: bytes) -> None:
        self.data["public_keys"][ritual_id] = public_key

    def get_public_key(self, ritual_id: int) -> Optional[bytes]:
        return self.data["public_keys"].get(ritual_id)
