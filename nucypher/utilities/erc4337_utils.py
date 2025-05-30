import copy
import json
from dataclasses import dataclass
from enum import Enum
from typing import Tuple

import eth_abi
from eth_utils import keccak, to_bytes, to_checksum_address
from hexbytes import HexBytes

from nucypher.crypto.powers import TransactingPower


class EntryPointContracts:
    """Constants for EntryPoint contract addresses."""

    ENTRYPOINT_V08 = "0x4337084D9E255Ff0702461CF8895CE9E3b5Ff108"


class AAVersion(Enum):
    """Constants for AA versions."""

    V08 = "0.8.0"
    MDT = "mdt"


@dataclass
class UserOperation:
    """Represents a UserOperation for ERC-4337."""

    # https://www.erc4337.io/docs/understanding-ERC-4337/user-operation
    # Base
    sender: str
    nonce: int
    init_code: bytes = b""
    call_data: bytes = b""

    # Gas limits
    call_gas_limit: int = 0
    verification_gas_limit: int = 0
    pre_verification_gas: int = 0

    # Fee parameters
    max_fee_per_gas: int = 0
    max_priority_fee_per_gas: int = 0

    # Paymaster (optional)
    paymaster: str = None
    paymaster_verification_gas_limit: int = 0
    paymaster_post_op_gas_limit: int = 0
    paymaster_data: bytes = b""

    # Signature placeholder
    signature: bytes = b""

    def __eq__(self, other) -> bool:
        if not isinstance(other, UserOperation):
            return False
        return self.to_dict() == other.to_dict()

    def __bytes__(self) -> bytes:
        return json.dumps(self.to_dict(), sort_keys=True).encode("utf-8")

    @classmethod
    def from_bytes(cls, data: bytes) -> "UserOperation":
        d = json.loads(data.decode("utf-8"))
        return cls(
            sender=d["sender"],
            nonce=d["nonce"],
            init_code=bytes(HexBytes(d["init_code"] or b"")),
            call_data=bytes(HexBytes(d["call_data"] or b"")),
            call_gas_limit=d["call_gas_limit"],
            verification_gas_limit=d["verification_gas_limit"],
            pre_verification_gas=d["pre_verification_gas"],
            max_fee_per_gas=d["max_fee_per_gas"],
            max_priority_fee_per_gas=d["max_priority_fee_per_gas"],
            paymaster=d["paymaster"],
            paymaster_verification_gas_limit=d["paymaster_verification_gas_limit"],
            paymaster_post_op_gas_limit=d["paymaster_post_op_gas_limit"],
            paymaster_data=bytes(HexBytes(d["paymaster_data"] or b"")),
            signature=bytes(HexBytes(d["signature"] or b"")),
        )

    def to_dict(self) -> dict:
        return {
            "sender": self.sender,
            "nonce": self.nonce,
            "init_code": HexBytes(self.init_code).hex(),
            "call_data": HexBytes(self.call_data).hex(),
            "call_gas_limit": self.call_gas_limit,
            "verification_gas_limit": self.verification_gas_limit,
            "pre_verification_gas": self.pre_verification_gas,
            "max_fee_per_gas": self.max_fee_per_gas,
            "max_priority_fee_per_gas": self.max_priority_fee_per_gas,
            "paymaster": self.paymaster,
            "paymaster_verification_gas_limit": self.paymaster_verification_gas_limit,
            "paymaster_post_op_gas_limit": self.paymaster_post_op_gas_limit,
            "paymaster_data": HexBytes(self.paymaster_data).hex(),
            "signature": HexBytes(self.signature).hex(),
        }


PACKED_USER_OPERATION_DOMAIN_TYPE = {
    "EIP712Domain": [
        {"name": "name", "type": "string"},
        {"name": "version", "type": "string"},
        {"name": "chainId", "type": "uint256"},
        {"name": "verifyingContract", "type": "address"},
    ]
}

PACKED_USER_OPERATION_V08_TYPES = {
    **PACKED_USER_OPERATION_DOMAIN_TYPE,
    "PackedUserOperation": [
        {"name": "sender", "type": "address"},
        {"name": "nonce", "type": "uint256"},
        {"name": "initCode", "type": "bytes"},
        {"name": "callData", "type": "bytes"},
        {"name": "accountGasLimits", "type": "bytes32"},
        {"name": "preVerificationGas", "type": "uint256"},
        {"name": "gasFees", "type": "bytes32"},
        {"name": "paymasterAndData", "type": "bytes"},
    ],
}

PACKED_USER_OPERATION_MDT_TYPES = {
    **PACKED_USER_OPERATION_DOMAIN_TYPE,
    "PackedUserOperation": copy.deepcopy(
        PACKED_USER_OPERATION_V08_TYPES["PackedUserOperation"]
    )
    + [{"name": "entryPoint", "type": "address"}],
}


@dataclass
class PackedUserOperation:
    """Represents a packed UserOperation for Infinitism (v0.8.0) / OZ calldata-optimized format."""

    # - https://docs.openzeppelin.com/community-contracts/0.0.1/account-abstraction#useroperation
    # - https://github.com/eth-infinitism/account-abstraction/blob/v0.8.0/contracts/interfaces/PackedUserOperation.sol
    sender: str
    nonce: int
    init_code: bytes
    call_data: bytes
    account_gas_limits: bytes
    pre_verification_gas: int
    gas_fees: bytes
    paymaster_and_data: bytes
    signature: bytes

    @classmethod
    def _pack_account_gas_limits(
        cls, call_gas_limit: int, verification_gas_limit: int
    ) -> bytes:
        combined = (verification_gas_limit << 128) | call_gas_limit
        return combined.to_bytes(32, byteorder="big")

    @classmethod
    def _pack_gas_fees(cls, max_fee_per_gas: int, max_priority_fee_per_gas) -> bytes:
        combined = (max_priority_fee_per_gas << 128) | max_fee_per_gas
        return combined.to_bytes(32, byteorder="big")

    @classmethod
    def _pack_paymaster_and_data(
        cls,
        paymaster: str,
        paymaster_verification_gas_limit: int,
        paymaster_post_op_gas_limit: int,
        paymaster_data: bytes,
    ) -> bytes:
        if not paymaster:
            return b""
        paymaster_bytes = to_bytes(hexstr=paymaster)
        verification_bytes = paymaster_verification_gas_limit.to_bytes(
            16, byteorder="big"
        )
        post_op_bytes = paymaster_post_op_gas_limit.to_bytes(16, byteorder="big")
        return paymaster_bytes + verification_bytes + post_op_bytes + paymaster_data

    @classmethod
    def from_user_operation(cls, user_op: UserOperation) -> "PackedUserOperation":
        """Convert a UserOperation to a PackedUserOperation."""
        return cls(
            sender=user_op.sender,
            nonce=user_op.nonce,
            init_code=user_op.init_code,
            call_data=user_op.call_data,
            account_gas_limits=cls._pack_account_gas_limits(
                user_op.call_gas_limit, user_op.verification_gas_limit
            ),
            pre_verification_gas=user_op.pre_verification_gas,
            gas_fees=cls._pack_gas_fees(
                user_op.max_fee_per_gas, user_op.max_priority_fee_per_gas
            ),
            paymaster_and_data=cls._pack_paymaster_and_data(
                user_op.paymaster,
                user_op.paymaster_verification_gas_limit,
                user_op.paymaster_post_op_gas_limit,
                user_op.paymaster_data,
            ),
            signature=user_op.signature,
        )

    def _to_eip712_message(self, aa_version: AAVersion) -> dict:
        result = {
            "sender": self.sender,
            "nonce": self.nonce,
            "initCode": self.init_code,
            "callData": self.call_data,
            "accountGasLimits": self.account_gas_limits,
            "preVerificationGas": self.pre_verification_gas,
            "gasFees": self.gas_fees,
            "paymasterAndData": self.paymaster_and_data,
        }
        if aa_version == AAVersion.MDT:
            result["entryPoint"] = EntryPointContracts.ENTRYPOINT_V08
        return result

    @staticmethod
    def _get_domain(aa_version: AAVersion, chain_id: int) -> dict:
        result = {
            # TODO: Gross workaround for MDT (Hopefully this can be removed in the future)
            "name": "ERC4337" if aa_version != AAVersion.MDT else "MultiSigDeleGator",
            "version": "1",
            "chainId": chain_id,
            "verifyingContract": EntryPointContracts.ENTRYPOINT_V08,
        }
        return result

    def to_eip712_struct(self, aa_version: AAVersion, chain_id: int) -> dict:
        types = (
            PACKED_USER_OPERATION_V08_TYPES
            if aa_version == AAVersion.V08
            else PACKED_USER_OPERATION_MDT_TYPES
        )
        return {
            "types": types,
            "primaryType": "PackedUserOperation",
            "domain": self._get_domain(aa_version, chain_id),
            "message": self._to_eip712_message(aa_version),
        }

    def sign(
        self,
        transacting_power: TransactingPower,
        aa_version: AAVersion,
        chain_id: int,
    ) -> Tuple[HexBytes, HexBytes]:
        """Sign the PackedUserOperation."""
        eip_712_message = self.to_eip712_struct(aa_version, chain_id)
        message_hash, signature = transacting_power.sign_message_eip712(
            eip_712_message, standardize=False
        )

        self.signature = bytes(signature)
        return message_hash, signature


def encode_function_call(signature: str, args: list) -> HexBytes:
    selector = HexBytes(keccak(text=signature)[:4])
    types = [
        t
        for t in signature[signature.find("(") + 1 : signature.find(")")].split(",")
        if t
    ]
    return selector + HexBytes(eth_abi.encode(types, args))


def create_eth_transfer(
    sender: str, nonce: int, to: str, value: int, **kwargs
) -> "UserOperation":
    data = encode_function_call(
        "execute(address,uint256,bytes)",
        [to_checksum_address(to), value, b""],
    )
    return UserOperation(sender, nonce, b"", data, **kwargs)


def create_erc20_transfer(
    sender: str, nonce: int, token: str, to: str, amount: int, **kwargs
) -> "UserOperation":
    call = encode_function_call(
        "transfer(address,uint256)", [to_checksum_address(to), amount]
    )
    data = encode_function_call(
        "execute(address,uint256,bytes)", [to_checksum_address(token), 0, call]
    )
    return UserOperation(sender, nonce, b"", data, **kwargs)


def create_erc20_approve(
    sender: str, nonce: int, token: str, spender: str, amount: int, **kwargs
) -> "UserOperation":
    call = encode_function_call(
        "approve(address,uint256)", [to_checksum_address(spender), amount]
    )
    data = encode_function_call(
        "execute(address,uint256,bytes)", [to_checksum_address(token), 0, call]
    )
    return UserOperation(sender, nonce, b"", data, **kwargs)


def create_contract_call(
    sender: str, nonce: int, target: str, data: HexBytes, value: int = 0, **kwargs
) -> "UserOperation":
    payload = encode_function_call(
        "execute(address,uint256,bytes)", [to_checksum_address(target), value, data]
    )
    return UserOperation(sender, nonce, b"", payload, **kwargs)
