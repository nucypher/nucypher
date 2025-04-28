import json
from typing import NamedTuple, NewType, TypeVar

from hexbytes import HexBytes

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
        condition: bytes,
        context: bytes,

    ):
        self.data_to_sign = data_to_sign
        self.cohort_id = cohort_id
        self.condition = condition
        self.context = context

    @staticmethod
    def from_bytes(request_data: bytes):
        result = json.loads(request_data.decode())
        data_to_sign = bytes(HexBytes(result["data_to_sign"]))
        cohort_id = result["cohort_id"]
        condition = bytes(HexBytes(result["condition"]))
        context = bytes(HexBytes(result["context"]))

        return ThresholdSignatureRequest(
            data_to_sign=data_to_sign,
            cohort_id=cohort_id,
            condition=condition,
            context=context,
        )
