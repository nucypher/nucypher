from collections import defaultdict

from nucypher_core.ferveo import AggregatedTranscript, Transcript
from web3.types import TxReceipt


class DKGStorage:
    """A simple in-memory storage for DKG data"""

    def __init__(self):
        self.data = defaultdict(dict)

    def store_transcript(self, ritual_id: int, transcript: Transcript) -> None:
        self.data["transcripts"][ritual_id] = bytes(transcript)

    def get_transcript(self, ritual_id: int) -> Transcript:
        data = self.data["transcripts"][ritual_id]
        transcript = Transcript.from_bytes(data)
        return transcript

    def store_transcript_receipt(self, ritual_id: int, receipt: TxReceipt) -> None:
        self.data["transcript_receipts"][ritual_id] = receipt

    def get_transcript_receipt(self, ritual_id: int) -> TxReceipt:
        return self.data["transcript_receipts"][ritual_id]

    def store_aggregated_transcript(self, ritual_id: int, aggregated_transcript: AggregatedTranscript) -> None:
        self.data["aggregated_transcripts"][ritual_id] = bytes(aggregated_transcript)

    def get_aggregated_transcript(self, ritual_id: int) -> AggregatedTranscript:
        return self.data["aggregated_transcripts"][ritual_id]

    def store_aggregated_transcript_receipt(self, ritual_id: int, receipt: TxReceipt) -> None:
        self.data["aggregated_transcript_receipts"][ritual_id] = receipt

    def get_aggregated_transcript_receipt(self, ritual_id: int) -> TxReceipt:
        return self.data["aggregated_transcript_receipts"][ritual_id]

    def store_dkg_params(self, ritual_id: int, public_params) -> None:
        self.data["public_params"][ritual_id] = public_params

    def get_dkg_params(self, ritual_id: int) -> int:
        return self.data["public_params"][ritual_id]

    def store_public_key(self, ritual_id: int, public_key: bytes) -> None:
        self.data["public_keys"][ritual_id] = public_key

    def get_public_key(self, ritual_id: int) -> bytes:
        return self.data["public_keys"][ritual_id]
