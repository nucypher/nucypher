import json
from enum import Enum
from typing import Optional

from hexbytes import HexBytes

from nucypher.policy.conditions.types import ContextDict


class UserOp:

    def __init__(
        self,
        sender: str,
        destination: str,
        value: int,
        data: str,
        nonce: int,
        chain_id: int,
        contract_address: str,
    ):
        self.sender = sender
        self.destination = destination
        self.value = value
        self.data = data
        self.nonce = nonce
        self.chain_id = chain_id
        self.contract_address = contract_address

    def to_message(self) -> dict:
        """Returns the message payload for EIP-712 encoding."""
        return {
            "sender": self.sender,
            "destination": self.destination,
            "value": self.value,
            "data": self.data,
            "nonce": self.nonce,
            "chainId": self.chain_id,
            "contractAddress": self.contract_address,
        }

    def to_structured_data(self) -> dict:
        """Builds the full EIP-712 structured data dict."""
        domain = {
            "name": "TACoMultisig",
            "version": "1",
            "chainId": self.chain_id,
            "verifyingContract": self.contract_address,
        }
        _types = {
            "EIP712Domain": [
                {"name": "name", "type": "string"},
                {"name": "version", "type": "string"},
                {"name": "chainId", "type": "uint256"},
                {"name": "verifyingContract", "type": "address"},
            ],
            "Transaction": [
                {"name": "sender", "type": "address"},
                {"name": "destination", "type": "address"},
                {"name": "value", "type": "uint256"},
                {"name": "data", "type": "bytes"},
                {"name": "nonce", "type": "uint256"},
            ],
        }
        return {
            "types": _types,
            "domain": domain,
            "primaryType": "Transaction",
            "message": self.to_message(),
        }

    def __bytes__(self) -> bytes:
        """
        Serializes the UserOp to bytes in JSON format.
        """
        return json.dumps(self.to_structured_data()).encode()

    @staticmethod
    def from_bytes(user_op_data: bytes):
        """
        Deserializes the UserOp from bytes in JSON format.
        """
        result = json.loads(user_op_data.decode())
        sender = result["message"]["sender"]
        destination = result["message"]["destination"]
        value = result["message"]["value"]
        data = result["message"]["data"]
        nonce = result["message"]["nonce"]
        chain_id = result["domain"]["chainId"]
        contract_address = result["domain"]["verifyingContract"]

        return UserOp(
            sender=sender,
            destination=destination,
            value=value,
            data=data,
            nonce=nonce,
            chain_id=chain_id,
            contract_address=contract_address,
        )

class _SignatureTypes(Enum):
    EIP191 = "eip-191"
    EIP712 = "eip-712"


class SignatureRequest:

    def __init__(
        self,
        data: bytes,
        cohort_id: int,
        chain_id: int,
        context: Optional[ContextDict] = None,
        _type: str = _SignatureTypes.EIP191.value,
    ):
        self.data = data
        if _type not in [t.value for t in _SignatureTypes]:
            raise ValueError(
                f"Invalid type: {_type}. Must be one of {[t.value for t in _SignatureTypes]}"
            )
        self.cohort_id = cohort_id
        self.chain_id = chain_id
        self.data = data
        self.context = context or {}

    def __bytes__(self) -> bytes:
        """Serialize the request to bytes in JSON format."""
        data = {
            "cohort_id": self.cohort_id,
            "chain_id": self.chain_id,
            "data": bytes(self.data).hex(),
            "context": self.context,
            "type": _SignatureTypes.EIP191.value,
        }
        return json.dumps(data).encode()

    @staticmethod
    def from_bytes(request_data: bytes):
        try:
            result = json.loads(request_data.decode())
            data = bytes(HexBytes(result["data"]))
            chain_id = result["chain_id"]
            cohort_id = result["cohort_id"]
            context = result["context"]
            _type = result["type"]
        except (ValueError, KeyError) as e:
            raise ValueError("Invalid request data") from e
        return SignatureRequest(
            cohort_id=cohort_id,
            chain_id=chain_id,
            data=data,
            context=context,
            _type=_type,
        )


class SignatureResponse:

    def __init__(self, message: bytes, _hash: bytes, signature: bytes):
        self.message = message
        self.hash = _hash
        self.signature = signature

    def __bytes__(self) -> bytes:
        """Serialize the response to bytes in JSON format."""
        data = {
            "message": self.message.hex(),
            "message_hash": self.hash.hex(),
            "signature": self.signature.hex(),
        }
        return json.dumps(data).encode()

    @classmethod
    def from_bytes(cls, response_data: bytes):
        """Deserialize the response from bytes in JSON format."""
        result = json.loads(response_data.decode())
        _hash = bytes(HexBytes(result["message_hash"]))
        signature = bytes(HexBytes(result["signature"]))
        message = bytes(HexBytes(result["message"]))
        return cls(
            message=message,
            _hash=_hash,
            signature=signature,
        )
