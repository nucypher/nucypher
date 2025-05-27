import json
from enum import Enum
from typing import Dict, Optional, Union

from hexbytes import HexBytes

from nucypher.policy.conditions.types import ContextDict

EIP712Dict = Dict[str, Union[str, int, float, bool, Dict, list]]


class SignatureType(Enum):
    """Enum for different signature types."""

    EIP_191 = "eip-191"
    EIP_712 = "eip-712"


class SignatureRequest:

    def __init__(
        self,
        data: Union[bytes, EIP712Dict],
        cohort_id: int,
        chain_id: int,
        signature_type: SignatureType,
        context: Optional[ContextDict] = None,
    ):
        if signature_type not in SignatureType:
            raise ValueError(f"Invalid signature type: {signature_type}")
        if signature_type == SignatureType.EIP_712 and not isinstance(data, dict):
            raise ValueError("EIP-712 signature type requires data to be a dictionary.")
        if signature_type == SignatureType.EIP_191 and not isinstance(data, bytes):
            raise ValueError("EIP-191 signature type requires data to be bytes.")
        self.data = data
        self.cohort_id = cohort_id
        self.chain_id = chain_id
        self.context = context or {}
        self.signature_type = signature_type

    def __bytes__(self) -> bytes:
        """Serialize the request to bytes in JSON format."""
        if self.signature_type == SignatureType.EIP_712:
            # Convert dict to JSON string for EIP-712
            data = json.dumps(self.data).encode()
        else:
            # Convert bytes to hex string for EIP-191
            data = HexBytes(self.data)
        data = {
            "data": data.hex(),
            "cohort_id": self.cohort_id,
            "chain_id": self.chain_id,
            "context": self.context,
            "signature_type": self.signature_type.value,
        }
        return json.dumps(data).encode()

    @staticmethod
    def from_bytes(request_data: bytes):
        try:
            result = json.loads(request_data.decode())
            cohort_id = result["cohort_id"]
            chain_id = result["chain_id"]
            context = result["context"]
            signature_type_str = result["signature_type"]
            signature_type = SignatureType(signature_type_str)
            data = HexBytes(result["data"])
        except (ValueError, KeyError) as e:
            raise ValueError("Invalid request data") from e

        if signature_type == SignatureType.EIP_712:
            # Deserialize data from JSON string for EIP-712
            data = json.loads(data.decode())
        return SignatureRequest(
            data=data,
            cohort_id=cohort_id,
            chain_id=chain_id,
            context=context,
            signature_type=signature_type,
        )


class SignatureResponse:

    def __init__(
        self,
        message: Union[HexBytes, EIP712Dict],
        _hash: HexBytes,
        signature: HexBytes,
        signature_type: SignatureType,
    ):
        self.message = message
        self.hash = _hash
        self.signature = signature
        self.signature_type = signature_type

    def __bytes__(self) -> bytes:
        """Serialize the response to bytes in JSON format."""
        if self.signature_type == SignatureType.EIP_712:
            # Convert dict to JSON string for EIP-712
            message = HexBytes(json.dumps(self.message).encode())
        else:
            # Convert bytes to hex string for EIP-191
            message = HexBytes(self.message)
        data = {
            "message": message.hex(),
            "message_hash": self.hash.hex(),
            "signature": self.signature.hex(),
            "signature_type": self.signature_type.value,
        }
        return json.dumps(data).encode()

    @classmethod
    def from_bytes(cls, response_data: bytes):
        """Deserialize the response from bytes in JSON format."""
        result = json.loads(response_data.decode())
        _hash = HexBytes(result["message_hash"])
        signature = HexBytes(result["signature"])
        signature_type = SignatureType(result["signature_type"])
        message = HexBytes(result["message"])
        if signature_type == SignatureType.EIP_712:
            # Deserialize message from JSON string for EIP-712
            message = json.loads(message.decode())
        return cls(
            message=message,
            _hash=_hash,
            signature=signature,
            signature_type=signature_type,
        )
