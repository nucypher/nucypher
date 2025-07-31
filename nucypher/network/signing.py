import json
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Optional, Tuple

from hexbytes import HexBytes

from nucypher.crypto.powers import TransactingPower
from nucypher.policy.conditions.signing.base import SIGNING_CONDITION_OBJECT_CONTEXT_VAR
from nucypher.policy.conditions.types import ContextDict
from nucypher.utilities.erc4337_utils import (
    AAVersion,
    PackedUserOperation,
    UserOperation,
)


class SignatureRequestType(Enum):
    """Enum for different signature types."""

    USEROP = "userop"
    PACKED_USER_OP = "packedUserOp"
    EIP_191 = "eip-191"


# TODO I'm hesitant to have too much logic in this module because
#  this will all move to `nucypher-core`
class BaseSignatureRequest(ABC):

    def __init__(
        self,
        cohort_id: int,
        chain_id: int,
        signature_type: SignatureRequestType,
        context: Optional[ContextDict] = None,
    ):
        self.cohort_id = cohort_id
        self.chain_id = chain_id
        self.context = context or {}
        self.signature_type = signature_type

    @abstractmethod
    def __bytes__(self) -> bytes:
        raise NotImplementedError

    @classmethod
    def from_bytes(cls, request_data: bytes):
        raise NotImplementedError


class SignatureResponse:

    def __init__(
        self,
        _hash: bytes,
        signature: bytes,
        signature_type: SignatureRequestType,
    ):
        self.hash = _hash
        self.signature = signature
        self.signature_type = signature_type

    def __bytes__(self) -> bytes:
        """Serialize the response to bytes in JSON format."""
        data = {
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
        return cls(
            _hash=_hash,
            signature=signature,
            signature_type=signature_type,
        )


# TODO: This is only really for simple testing for now
class EIP191SignatureRequest(BaseSignatureRequest):
    def __init__(
        self,
        data: bytes,
        cohort_id: int,
        chain_id: int,
        context: Optional[ContextDict] = None,
    ):
        self.data = data
        super().__init__(
            cohort_id=cohort_id,
            chain_id=chain_id,
            signature_type=SignatureRequestType.EIP_191,
            context=context,
        )

    def __bytes__(self) -> bytes:
        """Serialize the EIP191 request to bytes in JSON format."""
        data = {
            "data": HexBytes(self.data).hex(),
            "cohort_id": self.cohort_id,
            "chain_id": self.chain_id,
            "context": self.context,
            "signature_type": self.signature_type.value,
        }
        return json.dumps(data).encode()

    @classmethod
    def from_bytes(cls, request_data: bytes):
        """Deserialize the EIP191 request from bytes in JSON format."""
        try:
            result = json.loads(request_data.decode())
            data = bytes(HexBytes(result["data"]))
            cohort_id = result["cohort_id"]
            chain_id = result["chain_id"]
            context = result["context"]
            signature_type_str = result["signature_type"]

        except (json.JSONDecodeError, KeyError) as e:
            raise ValueError("Invalid UserOperation request data") from e

        # Validate signature type
        signature_type = SignatureRequestType(signature_type_str)
        if signature_type != SignatureRequestType.EIP_191:
            raise ValueError(f"Expected EIP191 signature type, got {signature_type}")

        return cls(
            data=data,
            cohort_id=cohort_id,
            chain_id=chain_id,
            context=context,
        )


class UserOperationSignatureRequest(BaseSignatureRequest):
    """A specialized signature request for UserOperation."""

    def __init__(
        self,
        user_op: UserOperation,
        cohort_id: int,
        chain_id: int,
        aa_version: AAVersion,
        context: Optional[ContextDict] = None,
    ):
        self.user_op = user_op
        self.aa_version = aa_version
        super().__init__(
            cohort_id=cohort_id,
            chain_id=chain_id,
            signature_type=SignatureRequestType.USEROP,
            context=context,
        )

    def __bytes__(self) -> bytes:
        """Serialize the UserOperation request to bytes in JSON format."""
        # Serialize the UserOperation data
        user_op_data = bytes(self.user_op).decode("utf-8")

        data = {
            "user_op": user_op_data,
            "aa_version": self.aa_version.value,
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
            user_op_data = result["user_op"]
            aa_version_str = AAVersion(result["aa_version"])
            cohort_id = result["cohort_id"]
            chain_id = result["chain_id"]
            context = result["context"]
            signature_type_str = result["signature_type"]

        except (json.JSONDecodeError, KeyError) as e:
            raise ValueError("Invalid UserOperation request data") from e

        aa_version = AAVersion(aa_version_str)

        # Validate signature type
        signature_type = SignatureRequestType(signature_type_str)
        if signature_type != SignatureRequestType.USEROP:
            raise ValueError(f"Expected USEROP signature type, got {signature_type}")

        # Reconstruct the UserOperation
        user_op = UserOperation.from_bytes(user_op_data.encode("utf-8"))

        return cls(
            user_op=user_op,
            cohort_id=cohort_id,
            chain_id=chain_id,
            context=context,
            aa_version=aa_version,
        )


class PackedUserOperationSignatureRequest(BaseSignatureRequest):
    """A specialized signature request for PackedUserOperation."""

    def __init__(
        self,
        packed_user_op: PackedUserOperation,
        cohort_id: int,
        chain_id: int,
        aa_version: AAVersion,
        context: Optional[ContextDict] = None,
    ):

        self.packed_user_op = packed_user_op
        self.aa_version = aa_version
        super().__init__(
            cohort_id=cohort_id,
            chain_id=chain_id,
            signature_type=SignatureRequestType.PACKED_USER_OP,
            context=context,
        )

    def __bytes__(self) -> bytes:
        """Serialize the PackedUserOperation request to bytes in JSON format."""
        # Serialize the PackedUserOperation data
        packed_user_op_data = bytes(self.packed_user_op).decode("utf-8")

        data = {
            "packed_user_op": packed_user_op_data,
            "aa_version": self.aa_version.value,
            "cohort_id": self.cohort_id,
            "chain_id": self.chain_id,
            "context": self.context,
            "signature_type": self.signature_type.value,
        }
        return json.dumps(data).encode()

    @classmethod
    def from_bytes(cls, request_data: bytes):
        """Deserialize the PackedUserOperation request from bytes in JSON format."""
        try:
            result = json.loads(request_data.decode())
            packed_user_op_data = result["packed_user_op"]
            aa_version_str = AAVersion(result["aa_version"])
            cohort_id = result["cohort_id"]
            chain_id = result["chain_id"]
            context = result["context"]
            signature_type_str = result["signature_type"]

        except (json.JSONDecodeError, KeyError) as e:
            raise ValueError("Invalid PackedUserOperation request data") from e

        aa_version = AAVersion(aa_version_str)

        # Validate signature type
        signature_type = SignatureRequestType(signature_type_str)
        if signature_type != SignatureRequestType.PACKED_USER_OP:
            raise ValueError(
                f"Expected PACKED_USER_OP signature type, got {signature_type}"
            )

        # Reconstruct the UserOperation
        packed_user_op = PackedUserOperation.from_bytes(
            packed_user_op_data.encode("utf-8")
        )

        return cls(
            packed_user_op=packed_user_op,
            cohort_id=cohort_id,
            chain_id=chain_id,
            context=context,
            aa_version=aa_version,
        )


class UnsupportedSignatureRequest(ValueError):
    """
    Raised for unrecognized signature requests.
    """


#
# Logic for using SignatureRequest data classes
# This will stay in nucypher, while the data classes will move to nucypher-core
#
def sign_signature_request_data(
    request: BaseSignatureRequest,
    transacting_power: TransactingPower,
) -> Tuple[HexBytes, HexBytes]:
    """Sign a signature request using the provided transacting power."""
    if isinstance(request, UserOperationSignatureRequest):
        # Special handling for UserOperation requests
        packed_user_operation = PackedUserOperation.from_user_operation(request.user_op)
        return packed_user_operation.sign(
            transacting_power=transacting_power,
            aa_version=request.aa_version,
            chain_id=request.chain_id,
        )
    elif isinstance(request, PackedUserOperationSignatureRequest):
        return request.packed_user_op.sign(
            transacting_power=transacting_power,
            aa_version=request.aa_version,
            chain_id=request.chain_id,
        )
    elif isinstance(request, EIP191SignatureRequest):
        return transacting_power.sign_message_eip191(
            request.data,
            standardize=False,
        )

    raise UnsupportedSignatureRequest(
        f"Unsupported signature request: {request.__class__.__name__}"
    )


def deserialize_signature_request(
    request_data: bytes,
) -> BaseSignatureRequest:
    """Deserialize a signature request from bytes, and add signing object to context"""
    try:
        result = json.loads(request_data.decode())
        signature_type_str = result["signature_type"]
        signature_type = SignatureRequestType(signature_type_str)

        signature_request = None
        if signature_type == SignatureRequestType.USEROP:
            signature_request = UserOperationSignatureRequest.from_bytes(request_data)
        elif signature_type == SignatureRequestType.PACKED_USER_OP:
            signature_request = PackedUserOperationSignatureRequest.from_bytes(
                request_data
            )
        elif signature_type == SignatureRequestType.EIP_191:
            signature_request = EIP191SignatureRequest.from_bytes(request_data)

        if not signature_request:
            raise UnsupportedSignatureRequest(
                f"Invalid signature request type: {signature_type}"
            )

        # add the signing object to the context
        signing_object = get_signature_request_object(signature_request)
        signature_request.context[SIGNING_CONDITION_OBJECT_CONTEXT_VAR] = signing_object

        return signature_request

    except (json.JSONDecodeError, ValueError) as e:
        raise UnsupportedSignatureRequest("Invalid signature request data") from e


def get_signature_request_object(request: BaseSignatureRequest) -> Any:
    """Get the signature request object based on the request type."""
    if isinstance(request, UserOperationSignatureRequest):
        return request.user_op
    elif isinstance(request, PackedUserOperationSignatureRequest):
        return request.packed_user_op
    elif isinstance(request, EIP191SignatureRequest):
        return request.data

    raise UnsupportedSignatureRequest(
        f"Unsupported signature request: {request.__class__.__name__}"
    )
