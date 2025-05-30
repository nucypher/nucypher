import json
from dataclasses import dataclass
from enum import Enum
from typing import Tuple

import eth_abi
from eth_utils import keccak, to_checksum_address
from hexbytes import HexBytes

from nucypher.crypto.powers import TransactingPower


class EntryPointContracts:
    """Constants for EntryPoint contract addresses."""

    # TODO: not sure if we should keep v07 (the hash is different and not eip-127
    ENTRYPOINT_V07 = "0x0000000071727De22E5E9d8BAf0edAc6f37da032"
    ENTRYPOINT_V08 = "0x4337084D9E255Ff0702461CF8895CE9E3b5Ff108"


class EntryPointVersion(Enum):
    """Constants for EntryPoint versions."""
    V08 = "0.8.0"

    def get_domain_data(self, chain_id: int) -> dict:
        """Returns the domain for the EntryPoint version."""
        result = {
            "name": "ERC4337",
            "version": "1",
            "chainId": chain_id,
        }
        if self == EntryPointVersion.V08:
            result["verifyingContract"] = EntryPointContracts.ENTRYPOINT_V08
            return result

        raise ValueError(f"Unsupported EntryPoint version: {self}")


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
    paymaster_and_data: bytes = b""

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
            init_code=bytes(HexBytes(d["init_code"]) or b""),
            call_data=bytes(HexBytes(d["call_data"]) or b""),
            call_gas_limit=d["call_gas_limit"],
            verification_gas_limit=d["verification_gas_limit"],
            pre_verification_gas=d["pre_verification_gas"],
            max_fee_per_gas=d["max_fee_per_gas"],
            max_priority_fee_per_gas=d["max_priority_fee_per_gas"],
            paymaster_and_data=bytes(HexBytes(d["paymaster_and_data"]) or b""),
            signature=bytes(HexBytes(d["signature"]) or b""),
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
            "paymaster_and_data": HexBytes(self.paymaster_and_data).hex(),
            "signature": HexBytes(self.signature).hex(),
        }


PACKED_USER_OPERATION_EIP_712_TYPES = {
    "EIP712Domain": [
        {"name": "name", "type": "string"},
        {"name": "version", "type": "string"},
        {"name": "chainId", "type": "uint256"},
        {"name": "verifyingContract", "type": "address"},
    ],
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
            paymaster_and_data=user_op.paymaster_and_data,
            signature=user_op.signature,
        )

    def to_eip712_struct(
        self, entrypoint_version: EntryPointVersion, chain_id: int
    ) -> dict:
        return {
            "types": PACKED_USER_OPERATION_EIP_712_TYPES,
            "primaryType": "PackedUserOperation",
            "domain": entrypoint_version.get_domain_data(chain_id),
            "message": self._to_message(),
        }

    def sign(
        self,
        transacting_power: TransactingPower,
        entrypoint_version: EntryPointVersion,
        chain_id: int,
    ) -> Tuple[HexBytes, HexBytes]:
        eip_712_message = self.to_eip712_struct(entrypoint_version, chain_id)
        message_hash, signature = transacting_power.sign_message_eip712(
            eip_712_message, standardize=False
        )
        self.signature = bytes(signature)
        return message_hash, signature

    def _to_message(self) -> dict:
        return {
            "sender": self.sender,
            "nonce": self.nonce,
            "initCode": self.init_code,
            "callData": self.call_data,
            "accountGasLimits": self.account_gas_limits,
            "preVerificationGas": self.pre_verification_gas,
            "gasFees": self.gas_fees,
            "paymasterAndData": self.paymaster_and_data,
        }


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
