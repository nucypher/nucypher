import json
from enum import Enum
from typing import Optional

from hexbytes import HexBytes

from nucypher.policy.conditions.types import ContextDict


class UserOp:
    """
    A Python representation of the ERC-4337 PackedUserOperation as used by
    OpenZeppelin’s ERC4337Utils.hash(…).
    """

    def __init__(
        self,
        sender: str,
        nonce: int,
        init_code: bytes,
        call_data: bytes,
        verification_gas_limit: int,
        call_gas_limit: int,
        pre_verification_gas: int,
        max_fee_per_gas: int,
        max_priority_fee_per_gas: int,
        paymaster_and_data: bytes = b"",
        signature: Optional[bytes] = None,
        chain_id: int = 1,
        entry_point: str = "",
    ):
        self.sender = sender
        self.nonce = nonce
        self.initCode = init_code
        self.callData = call_data
        self.verificationGasLimit = verification_gas_limit
        self.callGasLimit = call_gas_limit
        self.preVerificationGas = pre_verification_gas
        self.maxFeePerGas = max_fee_per_gas
        self.maxPriorityFeePerGas = max_priority_fee_per_gas
        self.paymasterAndData = paymaster_and_data
        self.signature = signature or b""
        self.chainId = chain_id
        self.entryPoint = entry_point

    def to_message(self) -> dict:
        """Return the 'message' object for EIP-712 encoding (excludes signature)."""
        return {
            "sender": self.sender,
            "nonce": self.nonce,
            "initCode": self.initCode.hex(),
            "callData": self.callData.hex(),
            "verificationGasLimit": self.verificationGasLimit,
            "callGasLimit": self.callGasLimit,
            "preVerificationGas": self.preVerificationGas,
            "maxFeePerGas": self.maxFeePerGas,
            "maxPriorityFeePerGas": self.maxPriorityFeePerGas,
            "paymasterAndData": self.paymasterAndData.hex(),
        }

    def to_structured_data(self) -> dict:
        """
        Builds the full EIP-712 structured data dict for hashing via eth-account
        or similar libraries.
        """
        domain = {
            "name": "UserOperation",
            "version": "1",
            "chainId": self.chainId,
            "verifyingContract": self.entryPoint,
        }
        types = {
            "EIP712Domain": [
                {"name": "name", "type": "string"},
                {"name": "version", "type": "string"},
                {"name": "chainId", "type": "uint256"},
                {"name": "verifyingContract", "type": "address"},
            ],
            "UserOperation": [
                {"name": "sender", "type": "address"},
                {"name": "nonce", "type": "uint256"},
                {"name": "initCode", "type": "bytes"},
                {"name": "callData", "type": "bytes"},
                {"name": "verificationGasLimit", "type": "uint256"},
                {"name": "callGasLimit", "type": "uint256"},
                {"name": "preVerificationGas", "type": "uint256"},
                {"name": "maxFeePerGas", "type": "uint256"},
                {"name": "maxPriorityFeePerGas", "type": "uint256"},
                {"name": "paymasterAndData", "type": "bytes"},
            ],
        }
        return {
            "types": types,
            "domain": domain,
            "primaryType": "UserOperation",
            "message": self.to_message(),
        }

    def __bytes__(self) -> bytes:
        """
        Serializes the structured data to JSON bytes for signing.
        """
        return json.dumps(self.to_structured_data(), separators=(",", ":")).encode()

    @staticmethod
    def from_bytes(data: bytes) -> "UserOperation":
        """
        Deserialize a UserOperation from the same JSON format produced by __bytes__.
        Note: signature must be set separately if present.
        """
        obj = json.loads(data.decode())
        msg = obj["message"]
        return UserOperation(
            sender=msg["sender"],
            nonce=int(msg["nonce"]),
            init_code=bytes.fromhex(msg["initCode"]),
            call_data=bytes.fromhex(msg["callData"]),
            verification_gas_limit=int(msg["verificationGasLimit"]),
            call_gas_limit=int(msg["callGasLimit"]),
            pre_verification_gas=int(msg["preVerificationGas"]),
            max_fee_per_gas=int(msg["maxFeePerGas"]),
            max_priority_fee_per_gas=int(msg["maxPriorityFeePerGas"]),
            paymaster_and_data=bytes.fromhex(msg["paymasterAndData"]),
            signature=None,
            chain_id=int(obj["domain"]["chainId"]),
            entry_point=obj["domain"]["verifyingContract"],
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
