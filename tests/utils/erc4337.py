from eth_utils import to_checksum_address
from hexbytes import HexBytes
from nucypher_core import UserOperation

from nucypher.utilities.abi import encode_human_readable_call

COMMON_REQUIRED_USER_OP_GAS_VALUES = dict(
    call_gas_limit=1,
    verification_gas_limit=2,
    pre_verification_gas=3,
    max_fee_per_gas=4,
    max_priority_fee_per_gas=5,
)


def encode_function_call(signature: str, args: list) -> HexBytes:
    return HexBytes(encode_human_readable_call(signature, args))


def create_eth_transfer(
    sender: str, nonce: int, to: str, value: int, **kwargs
) -> "UserOperation":
    data = encode_function_call(
        "execute(address,uint256,bytes)",
        [to_checksum_address(to), value, b""],
    )
    return UserOperation(
        sender=sender,
        nonce=nonce,
        call_data=data,
        **{**COMMON_REQUIRED_USER_OP_GAS_VALUES, **kwargs}
    )


def create_erc20_transfer(
    sender: str, nonce: int, token: str, to: str, amount: int, **kwargs
) -> "UserOperation":
    call = encode_function_call(
        "transfer(address,uint256)", [to_checksum_address(to), amount]
    )
    data = encode_function_call(
        "execute(address,uint256,bytes)", [to_checksum_address(token), 0, call]
    )
    return UserOperation(
        sender=sender,
        nonce=nonce,
        call_data=data,
        **{**COMMON_REQUIRED_USER_OP_GAS_VALUES, **kwargs}
    )


def create_erc20_approve(
    sender: str, nonce: int, token: str, spender: str, amount: int, **kwargs
) -> "UserOperation":
    call = encode_function_call(
        "approve(address,uint256)", [to_checksum_address(spender), amount]
    )
    data = encode_function_call(
        "execute(address,uint256,bytes)", [to_checksum_address(token), 0, call]
    )
    return UserOperation(
        sender=sender,
        nonce=nonce,
        call_data=data,
        **{**COMMON_REQUIRED_USER_OP_GAS_VALUES, **kwargs}
    )


def create_contract_call(
    sender: str, nonce: int, target: str, data: HexBytes, value: int = 0, **kwargs
) -> "UserOperation":
    payload = encode_function_call(
        "execute(address,uint256,bytes)", [to_checksum_address(target), value, data]
    )
    return UserOperation(
        sender=sender,
        nonce=nonce,
        call_data=payload,
        **{**COMMON_REQUIRED_USER_OP_GAS_VALUES, **kwargs}
    )
