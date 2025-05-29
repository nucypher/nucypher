import json
from enum import Enum
from typing import Dict, Optional, Tuple, Union

from eth_typing import Hash32
from hexbytes import HexBytes

from nucypher.policy.conditions.types import ContextDict
from nucypher.utilities.erc4337_utils import EntryPointContracts, PackedUserOperation

EIP712Dict = Dict[str, Union[str, int, float, bool, Dict, list]]


class SignatureRequestType(Enum):
    """Enum for different signature types."""

    USEROP = "userop"
    EIP_191 = "eip-191"
    EIP_712 = "eip-712"


class BaseSignatureRequest:

    def __init__(
        self,
        data: Union[bytes, EIP712Dict],
        cohort_id: int,
        chain_id: int,
        signature_type: SignatureRequestType,
        context: Optional[ContextDict] = None,
    ):
        if not isinstance(signature_type, SignatureRequestType):
            raise ValueError(f"Invalid signature type: {signature_type}")
        if signature_type == SignatureRequestType.EIP_712 and not isinstance(
            data, dict
        ):
            raise ValueError("EIP-712 signature type requires data to be a dictionary.")
        if signature_type == SignatureRequestType.EIP_191 and not isinstance(
            data, bytes
        ):
            raise ValueError("EIP-191 signature type requires data to be bytes.")
        self.data = data
        self.cohort_id = cohort_id
        self.chain_id = chain_id
        self.context = context or {}
        self.signature_type = signature_type

    def __bytes__(self) -> bytes:
        """Serialize the request to bytes in JSON format."""
        if self.signature_type == SignatureRequestType.EIP_712:
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
            signature_type = SignatureRequestType(signature_type_str)
            data = HexBytes(result["data"])
        except (ValueError, KeyError) as e:
            raise ValueError("Invalid request data") from e

        if signature_type == SignatureRequestType.EIP_712:
            # Deserialize data from JSON string for EIP-712
            data = json.loads(data.decode())
        return BaseSignatureRequest(
            data=data,
            cohort_id=cohort_id,
            chain_id=chain_id,
            context=context,
            signature_type=signature_type,
        )


class SignatureResponse:

    def __init__(
        self,
        message: Union[bytes, EIP712Dict],
        _hash: bytes,
        signature: bytes,
        signature_type: SignatureRequestType,
    ):
        self.message = message
        self.hash = _hash
        self.signature = signature
        self.signature_type = signature_type

    def __bytes__(self) -> bytes:
        """Serialize the response to bytes in JSON format."""
        if self.signature_type == SignatureRequestType.EIP_712:
            # Convert dict to JSON string for EIP-712
            message = HexBytes(json.dumps(self.message).encode())
        else:
            # Convert bytes to hex string for EIP-191
            message = HexBytes(self.message)
        data = {
            "message": HexBytes(message).hex(),
            "message_hash": HexBytes(self.hash).hex(),
            "signature": HexBytes(self.signature).hex(),
            "signature_type": self.signature_type.value,
        }
        return json.dumps(data).encode()

    @classmethod
    def from_bytes(cls, response_data: bytes):
        """Deserialize the response from bytes in JSON format."""
        result = json.loads(response_data.decode())
        _hash = bytes(HexBytes(result["message_hash"]))
        signature = bytes(HexBytes(result["signature"]))
        signature_type = SignatureRequestType(result["signature_type"])
        message = bytes(HexBytes(result["message"]))
        if signature_type == SignatureRequestType.EIP_712:
            # Deserialize message from JSON string for EIP-712
            message = json.loads(message.decode())
        return cls(
            message=message,
            _hash=_hash,
            signature=signature,
            signature_type=signature_type,
        )


class UserOperationSigningRequest(BaseSignatureRequest):
    """A specialized signature request for UserOperation."""

    def __init__(
        self,
        userop: PackedUserOperation,
        cohort_id: int,
        chain_id: int,
        context: Optional[ContextDict] = None,
        entrypoint: Optional[str] = None,
    ):

        if not isinstance(userop, PackedUserOperation):
            raise ValueError("userop must be an instance of PackedUserOperation.")
        if entrypoint is None:
            raise ValueError(
                "Entry point must be specified for UserOperation signing request."
            )

        # Validate entrypoint against known values
        valid_entrypoints = [
            EntryPointContracts.ENTRYPOINT_V07,
            EntryPointContracts.ENTRYPOINT_V08,
        ]
        if entrypoint not in valid_entrypoints:
            raise ValueError(
                f"Invalid entrypoint: {entrypoint}. Must be one of {valid_entrypoints}."
            )

        self.userop = userop
        self.entrypoint = entrypoint

        super().__init__(
            data=userop.to_eip712_struct(entrypoint=entrypoint, chain_id=chain_id),
            cohort_id=cohort_id,
            chain_id=chain_id,
            signature_type=SignatureRequestType.USEROP,
            context=context or {},
        )

    def sign(self, transacting_power) -> Tuple[Hash32, HexBytes]:
        return self.userop.sign(
            transacting_power=transacting_power,
            entrypoint=self.entrypoint,
            chain_id=self.chain_id,
        )

    def __bytes__(self) -> bytes:
        """Serialize the UserOperation request to bytes in JSON format."""
        # Serialize the UserOperation data
        userop_data = bytes(self.userop).decode("utf-8")

        data = {
            "userop": userop_data,
            "entrypoint": self.entrypoint,
            "cohort_id": self.cohort_id,
            "chain_id": self.chain_id,
            "context": self.context,
            "signature_type": self.signature_type.value,
        }
        return json.dumps(data).encode()

    @classmethod
    def from_bytes(cls, request_data: bytes):
        """Deserialize the UserOperation request from bytes in JSON format."""
        try:
            result = json.loads(request_data.decode())
            userop_data = result["userop"]
            entrypoint = result["entrypoint"]
            cohort_id = result["cohort_id"]
            chain_id = result["chain_id"]
            context = result["context"]
            signature_type_str = result["signature_type"]

        except (json.JSONDecodeError, KeyError) as e:
            raise ValueError("Invalid UserOperation request data") from e

        try:
            # Validate signature type
            signature_type = SignatureRequestType(signature_type_str)
            if signature_type != SignatureRequestType.USEROP:
                raise ValueError(
                    f"Expected USEROP signature type, got {signature_type}"
                )

            # Reconstruct the PackedUserOperation
            userop = PackedUserOperation.from_bytes(userop_data.encode("utf-8"))

        except ValueError:
            # Re-raise ValueError as-is (includes our validation errors)
            raise

        return cls(
            userop=userop,
            cohort_id=cohort_id,
            chain_id=chain_id,
            context=context,
            entrypoint=entrypoint,
        )


def deserialize_signature_request(
    request_data: bytes,
) -> Union[BaseSignatureRequest, UserOperationSigningRequest]:
    """Deserialize a signature request from bytes."""
    try:
        result = json.loads(request_data.decode())
        signature_type_str = result["signature_type"]
        signature_type = SignatureRequestType(signature_type_str)

        if signature_type == SignatureRequestType.USEROP:
            return UserOperationSigningRequest.from_bytes(request_data)
        else:
            return BaseSignatureRequest.from_bytes(request_data)
    except (json.JSONDecodeError, ValueError) as e:
        raise ValueError("Invalid signature request data") from e
