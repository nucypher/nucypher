import json
from dataclasses import dataclass, field

import eth_abi
from eth_account import Account
from eth_account.messages import SignableMessage, encode_typed_data
from eth_utils import keccak, to_bytes, to_checksum_address
from hexbytes import HexBytes


def empty_hexbytes() -> HexBytes:
    """Return an empty HexBytes object."""
    return HexBytes(b"")


@dataclass
class PackedUserOperation:
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

    def encode(self, entrypoint: str, chain_id: int) -> SignableMessage:
        return encode_typed_data(
            self.to_eip712_struct(entrypoint=entrypoint, chain_id=chain_id)
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
        return (
            paymaster_bytes + verification_bytes + post_op_bytes + self.paymaster_data
        )

    def pack(self) -> dict:
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
            "name": "UserOperation",
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

    def sign(self, private_key: str, entrypoint: str, chain_id: int):
        message = self.encode(entrypoint=entrypoint, chain_id=chain_id)
        signed = Account.sign_message(message, private_key=private_key)
        self.signature = signed.signature
        return signed

    def to_dict(self) -> dict:
        data = {
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
        return data

    def __bytes__(self) -> bytes:
        """Serialize the PackedUserOperation to bytes."""
        data = self.to_dict()
        json_str = json.dumps(data, sort_keys=True)
        return json_str.encode("utf-8")

    @classmethod
    def from_bytes(cls, data: bytes) -> "PackedUserOperation":
        """Deserialize bytes to a PackedUserOperation instance."""
        # Decode bytes to JSON string
        json_str = data.decode("utf-8")
        data_dict = json.loads(json_str)

        # Convert hex strings back to bytes
        init_code = (
            HexBytes(data_dict["init_code"])
            if data_dict["init_code"]
            else empty_hexbytes()
        )
        call_data = (
            HexBytes(data_dict["call_data"])
            if data_dict["call_data"]
            else empty_hexbytes()
        )
        paymaster_data = (
            HexBytes(data_dict["paymaster_data"])
            if data_dict["paymaster_data"]
            else empty_hexbytes()
        )
        signature = (
            HexBytes(data_dict["signature"])
            if data_dict["signature"]
            else empty_hexbytes()
        )

        # Create and return the instance
        return cls(
            sender=data_dict["sender"],
            nonce=data_dict["nonce"],
            init_code=init_code,
            call_data=call_data,
            verification_gas_limit=data_dict["verification_gas_limit"],
            call_gas_limit=data_dict["call_gas_limit"],
            pre_verification_gas=data_dict["pre_verification_gas"],
            max_priority_fee_per_gas=data_dict["max_priority_fee_per_gas"],
            max_fee_per_gas=data_dict["max_fee_per_gas"],
            paymaster=data_dict["paymaster"],
            paymaster_verification_gas_limit=data_dict[
                "paymaster_verification_gas_limit"
            ],
            paymaster_post_op_gas_limit=data_dict["paymaster_post_op_gas_limit"],
            paymaster_data=paymaster_data,
            signature=signature,
        )

    def to_hex(self) -> str:
        """Serialize to hex string (useful for storage/transmission)."""
        return bytes(self).hex()

    @classmethod
    def from_hex(cls, hex_str: str) -> "PackedUserOperation":
        """Deserialize from hex string."""
        return cls.from_bytes(bytes.fromhex(hex_str))

    def __eq__(self, other) -> bool:
        """Enable equality comparison between PackedUserOperation instances."""
        if not isinstance(other, PackedUserOperation):
            return False
        return (
            self.sender == other.sender
            and self.nonce == other.nonce
            and self.init_code == other.init_code
            and self.call_data == other.call_data
            and self.verification_gas_limit == other.verification_gas_limit
            and self.call_gas_limit == other.call_gas_limit
            and self.pre_verification_gas == other.pre_verification_gas
            and self.max_priority_fee_per_gas == other.max_priority_fee_per_gas
            and self.max_fee_per_gas == other.max_fee_per_gas
            and self.paymaster == other.paymaster
            and self.paymaster_verification_gas_limit
            == other.paymaster_verification_gas_limit
            and self.paymaster_post_op_gas_limit == other.paymaster_post_op_gas_limit
            and self.paymaster_data == other.paymaster_data
            and self.signature == other.signature
        )


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
) -> PackedUserOperation:
    data = encode_function_call(
        "execute(address,uint256,bytes)",
        [to_checksum_address(to), value, empty_hexbytes()],
    )
    return PackedUserOperation(sender, nonce, empty_hexbytes(), data, **kwargs)


def create_erc20_transfer(
    sender: str, nonce: int, token: str, to: str, amount: int, **kwargs
) -> PackedUserOperation:
    call = encode_function_call(
        "transfer(address,uint256)", [to_checksum_address(to), amount]
    )
    data = encode_function_call(
        "execute(address,uint256,bytes)", [to_checksum_address(token), 0, call]
    )
    return PackedUserOperation(sender, nonce, empty_hexbytes(), data, **kwargs)


def create_erc20_approve(
    sender: str, nonce: int, token: str, spender: str, amount: int, **kwargs
) -> PackedUserOperation:
    call = encode_function_call(
        "approve(address,uint256)", [to_checksum_address(spender), amount]
    )
    data = encode_function_call(
        "execute(address,uint256,bytes)", [to_checksum_address(token), 0, call]
    )
    return PackedUserOperation(sender, nonce, empty_hexbytes(), data, **kwargs)


def create_erc721_transfer(
    sender: str, nonce: int, token: str, to: str, token_id: int, **kwargs
) -> PackedUserOperation:
    call = encode_function_call(
        "safeTransferFrom(address,address,uint256)",
        [to_checksum_address(sender), to_checksum_address(to), token_id],
    )
    data = encode_function_call(
        "execute(address,uint256,bytes)", [to_checksum_address(token), 0, call]
    )
    return PackedUserOperation(sender, nonce, empty_hexbytes(), data, **kwargs)


def create_erc721_set_approval_for_all(
    sender: str, nonce: int, token: str, operator: str, approved: bool, **kwargs
) -> PackedUserOperation:
    call = encode_function_call(
        "setApprovalForAll(address,bool)", [to_checksum_address(operator), approved]
    )
    data = encode_function_call(
        "execute(address,uint256,bytes)", [to_checksum_address(token), 0, call]
    )
    return PackedUserOperation(sender, nonce, empty_hexbytes(), data, **kwargs)


def create_erc1155_transfer_single(
    sender: str,
    nonce: int,
    token: str,
    to: str,
    id: int,
    value: int,
    data_bytes: HexBytes = empty_hexbytes(),
    **kwargs
) -> PackedUserOperation:
    call = encode_function_call(
        "safeTransferFrom(address,address,uint256,uint256,bytes)",
        [to_checksum_address(sender), to_checksum_address(to), id, value, data_bytes],
    )
    data = encode_function_call(
        "execute(address,uint256,bytes)", [to_checksum_address(token), 0, call]
    )
    return PackedUserOperation(sender, nonce, empty_hexbytes(), data, **kwargs)


def create_erc1155_transfer_batch(
    sender: str,
    nonce: int,
    token: str,
    to: str,
    ids: list,
    values: list,
    data_bytes: HexBytes = empty_hexbytes(),
    **kwargs
) -> PackedUserOperation:
    call = encode_function_call(
        "safeBatchTransferFrom(address,address,uint256[],uint256[],bytes)",
        [to_checksum_address(sender), to_checksum_address(to), ids, values, data_bytes],
    )
    data = encode_function_call(
        "execute(address,uint256,bytes)", [to_checksum_address(token), 0, call]
    )
    return PackedUserOperation(sender, nonce, empty_hexbytes(), data, **kwargs)


def create_contract_call(
    sender: str, nonce: int, target: str, data: HexBytes, value: int = 0, **kwargs
) -> PackedUserOperation:
    payload = encode_function_call(
        "execute(address,uint256,bytes)", [to_checksum_address(target), value, data]
    )
    return PackedUserOperation(sender, nonce, empty_hexbytes(), payload, **kwargs)
