import json
from enum import Enum
from typing import NamedTuple, NewType, Optional, TypeVar

from hexbytes import HexBytes

from nucypher.policy.conditions.types import ContextDict

ERC20Units = NewType("ERC20Units", int)
NuNits = NewType("NuNits", ERC20Units)
TuNits = NewType("TuNits", ERC20Units)

Agent = TypeVar("Agent", bound="agents.EthereumContractAgent")  # noqa: F821

RitualId = int
PhaseNumber = int


class PhaseId(NamedTuple):
    ritual_id: RitualId
    phase: PhaseNumber


class _SignatureTypes(Enum):
    EIP191 = "eip-191"
    EIP712 = "eip-712"


class SignatureRequest:

    def __init__(
        self,
        cohort_id: int,
        chain_id: int,
        data_to_sign: bytes,
        context: Optional[ContextDict] = None,
        _type: str = _SignatureTypes.EIP191.value,
    ):
        if _type not in [t.value for t in _SignatureTypes]:
            raise ValueError(
                f"Invalid type: {_type}. Must be one of {[t.value for t in _SignatureTypes]}"
            )
        self.cohort_id = cohort_id
        self.data_to_sign = data_to_sign
        self.cohort_id = cohort_id
        self.chain_id = chain_id
        self.data_to_sign = data_to_sign
        self.context = context or {}

    def __bytes__(self) -> bytes:
        """Serialize the request to bytes in JSON format."""
        data = {
            "cohort_id": self.cohort_id,
            "chain_id": self.chain_id,
            "data_to_sign": self.data_to_sign.hex(),
            "context": self.context,
            "type": _SignatureTypes.EIP191.value,
        }
        return json.dumps(data).encode()

    @staticmethod
    def from_bytes(request_data: bytes):
        try:
            result = json.loads(request_data.decode())
            data_to_sign = bytes(HexBytes(result["data_to_sign"]))
            cohort_id = result["cohort_id"]
            context = result["context"]
            _type = result["type"]
        except (ValueError, KeyError) as e:
            raise ValueError("Invalid request data") from e
        return SignatureRequest(
            cohort_id=cohort_id,
            chain_id=chain_id,
            data_to_sign=data_to_sign,
            context=context,
            _type=_type,
        )


class SignatureResponse:

    def __init__(self, message_hash: bytes, signature: bytes):
        self.message_hash = message_hash
        self.signature = signature

    def __bytes__(self) -> bytes:
        """Serialize the response to bytes in JSON format."""
        data = {
            "message_hash": self.message_hash.hex(),
            "signature": self.signature.hex(),
        }
        return json.dumps(data).encode()

    @classmethod
    def from_bytes(cls, response_data: bytes):
        """Deserialize the response from bytes in JSON format."""
        result = json.loads(response_data.decode())
        message_hash = bytes(HexBytes(result["message_hash"]))
        signature = bytes(HexBytes(result["signature"]))
        return cls(
            message_hash=message_hash,
            signature=signature,

        )
