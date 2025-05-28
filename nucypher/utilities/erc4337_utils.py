import json
from dataclasses import dataclass, field
from typing import Tuple

import eth_abi
from eth_account.messages import (
    SignableMessage,
    _hash_eip191_message,
    encode_typed_data,
)
from eth_typing import Hash32
from eth_utils import keccak, to_bytes, to_checksum_address
from hexbytes import HexBytes


def empty_hexbytes() -> HexBytes:
    """Return an empty HexBytes object."""
    return HexBytes(b"")


class EntryPointContracts:
    """Constants for EntryPoint contract addresses."""
    ENTRYPOINT_V07 = "0x0000000071727De22E5E9d8BAf0edAc6f37da032"
    ENTRYPOINT_V08 = "0x4337084d9e255ff0702461cf8895ce9e3b5ff108"


@dataclass
class PackedUserOperation:
    """Represents a packed UserOperation for ERC-4337."""

    sender: str
    nonce: int
    init_code: HexBytes = field(default_factory=empty_hexbytes)
    call_data: HexBytes = field(default_factory=empty_hexbytes)

    # Gas limits
    verification_gas_limit: int = 0
    call_gas_limit: int = 0
    pre_verification_gas: int = 0

    # Fee parameters
    max_priority_fee_per_gas: int = 0
    max_fee_per_gas: int = 0

    # Paymaster (optional)
    paymaster: str = None
    paymaster_verification_gas_limit: int = 0
    paymaster_post_op_gas_limit: int = 0
    paymaster_data: HexBytes = field(default_factory=empty_hexbytes)

    # Signature placeholder
    signature: HexBytes = field(default_factory=empty_hexbytes)

    def __eq__(self, other) -> bool:
        if not isinstance(other, PackedUserOperation):
            return False
        return self.to_dict() == other.to_dict()

    def __bytes__(self) -> bytes:
        return json.dumps(self.to_dict(), sort_keys=True).encode("utf-8")

    @classmethod
    def from_bytes(cls, data: bytes) -> "PackedUserOperation":
        d = json.loads(data.decode("utf-8"))
        return cls(
            sender=d["sender"],
            nonce=d["nonce"],
            init_code=HexBytes(d["init_code"] or b""),
            call_data=HexBytes(d["call_data"] or b""),
            verification_gas_limit=d["verification_gas_limit"],
            call_gas_limit=d["call_gas_limit"],
            pre_verification_gas=d["pre_verification_gas"],
            max_priority_fee_per_gas=d["max_priority_fee_per_gas"],
            max_fee_per_gas=d["max_fee_per_gas"],
            paymaster=d["paymaster"],
            paymaster_verification_gas_limit=d["paymaster_verification_gas_limit"],
            paymaster_post_op_gas_limit=d["paymaster_post_op_gas_limit"],
            paymaster_data=HexBytes(d["paymaster_data"] or b""),
            signature=HexBytes(d["signature"] or b""),
        )

    def _pack_account_gas_limits(self) -> HexBytes:
        combined = (self.verification_gas_limit << 128) | self.call_gas_limit
        return HexBytes(combined.to_bytes(32, byteorder="big"))

    def _pack_gas_fees(self) -> HexBytes:
        combined = (self.max_priority_fee_per_gas << 128) | self.max_fee_per_gas
        return HexBytes(combined.to_bytes(32, byteorder="big"))

    def _pack_paymaster_and_data(self) -> HexBytes:
        if not self.paymaster:
            return HexBytes(b"")
        paymaster_bytes = to_bytes(hexstr=self.paymaster)
        verification_bytes = self.paymaster_verification_gas_limit.to_bytes(
            16, byteorder="big"
        )
        post_op_bytes = self.paymaster_post_op_gas_limit.to_bytes(16, byteorder="big")
        return HexBytes(
            paymaster_bytes + verification_bytes + post_op_bytes + self.paymaster_data
        )

    def encode(self, entrypoint: str, chain_id: int) -> SignableMessage:
        return encode_typed_data(
            full_message=self.to_eip712_struct(entrypoint=entrypoint, chain_id=chain_id)
        )

    def hash(self, entrypoint: str, chain_id: int) -> Hash32:
        return _hash_eip191_message(
            self.encode(entrypoint=entrypoint, chain_id=chain_id)
        )

    def sign(
        self, transacting_power, entrypoint: str, chain_id: int
    ) -> Tuple[Hash32, HexBytes]:
        message = self.encode(entrypoint=entrypoint, chain_id=chain_id)
        message, signature = transacting_power.sign_message_eip712(message)
        self.signature = HexBytes(signature)
        return self.hash(entrypoint=entrypoint, chain_id=chain_id), self.signature

    def pack(self) -> dict:
        """OZ calldata-optimized format"""
        return {
            "sender": self.sender,
            "nonce": self.nonce,
            "initCode": self.init_code.hex(),
            "callData": self.call_data.hex(),
            "accountGasLimits": self._pack_account_gas_limits(),
            "preVerificationGas": self.pre_verification_gas,
            "gasFees": self._pack_gas_fees(),
            "paymasterAndData": self._pack_paymaster_and_data().hex(),
            "signature": self.signature.hex(),
        }

    def pack_raw(self) -> dict:
        """Infinitism raw struct layout"""
        return {
            "sender": self.sender,
            "nonce": self.nonce,
            "initCode": self.init_code,
            "callData": self.call_data,
            "verificationGasLimit": self.verification_gas_limit,
            "callGasLimit": self.call_gas_limit,
            "preVerificationGas": self.pre_verification_gas,
            "maxFeePerGas": self.max_fee_per_gas,
            "maxPriorityFeePerGas": self.max_priority_fee_per_gas,
            "paymasterAndData": self._pack_paymaster_and_data(),
            "signature": self.signature,
        }

    def to_eip712_struct(self, entrypoint: str, chain_id: int) -> dict:
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
                {"name": "callGasLimit", "type": "uint256"},
                {"name": "verificationGasLimit", "type": "uint256"},
                {"name": "preVerificationGas", "type": "uint256"},
                {"name": "maxPriorityFeePerGas", "type": "uint256"},
                {"name": "maxFeePerGas", "type": "uint256"},
                {"name": "paymasterAndData", "type": "bytes"},
            ],
        }
        domain = {
            "name": "ERC4337",
            "version": "1",
            "chainId": chain_id,
            "verifyingContract": entrypoint,
        }
        message = {
            "sender": self.sender,
            "nonce": self.nonce,
            "initCode": self.init_code.hex(),
            "callData": self.call_data.hex(),
            "callGasLimit": self.call_gas_limit,
            "verificationGasLimit": self.verification_gas_limit,
            "preVerificationGas": self.pre_verification_gas,
            "maxPriorityFeePerGas": self.max_priority_fee_per_gas,
            "maxFeePerGas": self.max_fee_per_gas,
            "paymasterAndData": self._pack_paymaster_and_data().hex(),
        }
        return {
            "types": types,
            "domain": domain,
            "primaryType": "UserOperation",
            "message": message,
        }

    def to_dict(self) -> dict:
        return {
            "sender": self.sender,
            "nonce": self.nonce,
            "init_code": self.init_code.hex(),
            "call_data": self.call_data.hex(),
            "verification_gas_limit": self.verification_gas_limit,
            "call_gas_limit": self.call_gas_limit,
            "pre_verification_gas": self.pre_verification_gas,
            "max_priority_fee_per_gas": self.max_priority_fee_per_gas,
            "max_fee_per_gas": self.max_fee_per_gas,
            "paymaster": self.paymaster,
            "paymaster_verification_gas_limit": self.paymaster_verification_gas_limit,
            "paymaster_post_op_gas_limit": self.paymaster_post_op_gas_limit,
            "paymaster_data": self.paymaster_data.hex(),
            "signature": self.signature.hex(),
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
) -> "PackedUserOperation":
    data = encode_function_call(
        "execute(address,uint256,bytes)",
        [to_checksum_address(to), value, empty_hexbytes()],
    )
    return PackedUserOperation(sender, nonce, empty_hexbytes(), data, **kwargs)


def create_erc20_transfer(
    sender: str, nonce: int, token: str, to: str, amount: int, **kwargs
) -> "PackedUserOperation":
    call = encode_function_call(
        "transfer(address,uint256)", [to_checksum_address(to), amount]
    )
    data = encode_function_call(
        "execute(address,uint256,bytes)", [to_checksum_address(token), 0, call]
    )
    return PackedUserOperation(sender, nonce, empty_hexbytes(), data, **kwargs)


def create_erc20_approve(
    sender: str, nonce: int, token: str, spender: str, amount: int, **kwargs
) -> "PackedUserOperation":
    call = encode_function_call(
        "approve(address,uint256)", [to_checksum_address(spender), amount]
    )
    data = encode_function_call(
        "execute(address,uint256,bytes)", [to_checksum_address(token), 0, call]
    )
    return PackedUserOperation(sender, nonce, empty_hexbytes(), data, **kwargs)


def create_contract_call(
    sender: str, nonce: int, target: str, data: HexBytes, value: int = 0, **kwargs
) -> "PackedUserOperation":
    payload = encode_function_call(
        "execute(address,uint256,bytes)", [to_checksum_address(target), value, data]
    )
    return PackedUserOperation(sender, nonce, empty_hexbytes(), payload, **kwargs)
