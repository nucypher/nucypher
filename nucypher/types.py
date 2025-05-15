import json
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


class ThresholdSignatureRequest:
    """TODO: Implement this in nucypher_core"""

    def __init__(
        self,
        data_to_sign: bytes,
        cohort_id: int,
        context: Optional[ContextDict] = None,
    ):
        self.data_to_sign = data_to_sign
        self.cohort_id = cohort_id
        self.context = context or {}

    def __bytes__(self) -> bytes:
        """Serialize the request to bytes in JSON format."""
        data = {
            "data_to_sign": self.data_to_sign.hex(),
            "cohort_id": self.cohort_id,
            "context": self.context,
        }
        return json.dumps(data).encode()

    @staticmethod
    def from_bytes(request_data: bytes):
        result = json.loads(request_data.decode())
        data_to_sign = bytes(HexBytes(result["data_to_sign"]))
        cohort_id = result["cohort_id"]
        context = result["context"]
        return ThresholdSignatureRequest(
            data_to_sign=data_to_sign,
            cohort_id=cohort_id,
            context=context,
        )


class ThresholdSignatureResponse:

    def __init__(self, data: bytes):
        self.data = data

    def __bytes__(self) -> bytes:
        """Serialize the response to bytes in JSON format."""
        return self.data

    @staticmethod
    def from_bytes(response_data: bytes):
        """Deserialize the response from bytes in JSON format."""
        return ThresholdSignatureResponse(data=response_data)
