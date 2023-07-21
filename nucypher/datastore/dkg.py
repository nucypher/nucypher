from collections import defaultdict
from typing import Optional, Union

from hexbytes import HexBytes
from nucypher_core.ferveo import AggregatedTranscript, Transcript
from web3.types import TxReceipt


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

    def store_transcript_receipt(
        self, ritual_id: int, txhash_or_receipt: Union[TxReceipt, HexBytes]
    ) -> None:
        self.data["transcript_receipts"][ritual_id] = txhash_or_receipt

    def get_transcript_receipt(
        self, ritual_id: int
    ) -> Optional[Union[TxReceipt, HexBytes]]:
        return self.data["transcript_receipts"].get(ritual_id)

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

    def store_aggregated_transcript_receipt(
        self, ritual_id: int, txhash_or_receipt: Union[TxReceipt, HexBytes]
    ) -> None:
        self.data["aggregated_transcript_receipts"][ritual_id] = txhash_or_receipt

    def get_aggregated_transcript_receipt(
        self, ritual_id: int
    ) -> Optional[Union[TxReceipt, HexBytes]]:
        return self.data["aggregated_transcript_receipts"].get(ritual_id)

    def store_public_key(self, ritual_id: int, public_key: bytes) -> None:
        self.data["public_keys"][ritual_id] = public_key

    def get_public_key(self, ritual_id: int) -> Optional[bytes]:
        return self.data["public_keys"].get(ritual_id)
