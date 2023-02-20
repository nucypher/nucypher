import os
from dataclasses import dataclass

from eth_typing import ChecksumAddress
from typing import List


class FerveoError(Exception):
    pass


@dataclass
class PublicKey:
    public_key: bytes

@dataclass
class Keypair:
    public_key: PublicKey
    secret_key: bytes

    @staticmethod
    def random():
        return Keypair(PublicKey(os.urandom(32)), os.urandom(32))


@dataclass
class DecryptionShare:
    share: bytes

    def __bytes__(self):
        return self.share

    def validate(self, *args, **kwargs) -> bool:
        return True


@dataclass
class Transcript:
    transcript: bytes

    @classmethod
    def from_bytes(cls, transcript: bytes):
        return cls(transcript=transcript)

    def __bytes__(self):
        return self.transcript

    def validate(self, *args, **kwargs) -> bool:
        return True


@dataclass
class AggregatedTranscript:
    transcript: bytes

    @classmethod
    def from_bytes(cls, transcript: bytes):
        return cls(transcript=transcript)

    def __bytes__(self):
        return self.transcript

    @staticmethod
    def validate(self, *args, **kwargs) -> bool:
        return True

    @staticmethod
    def create_decryption_share(*args, **kwargs) -> DecryptionShare:
        return DecryptionShare(share=os.urandom(32))


@dataclass
class Dkg:
    tau: int
    shares_num: int
    security_threshold: int
    validators: List[ChecksumAddress]
    me: ChecksumAddress

    @staticmethod
    def generate_transcript(*args, **kwargs) -> Transcript:
        return Transcript(transcript=os.urandom(32))

    @staticmethod
    def aggregate_transcripts(*args, **kwargs) -> AggregatedTranscript:
        return AggregatedTranscript(transcript=os.urandom(32))

    @staticmethod
    def validate(self, *args, **kwargs) -> bool:
        return True

    @property
    def final_key(self) -> PublicKey:
        return PublicKey(public_key=os.urandom(32))
