from eth_utils import to_checksum_address
from hexbytes import HexBytes

from nucypher.utilities.abi import encode_human_readable_call
from nucypher.utilities.erc4337_utils import UserOperation


def encode_function_call(signature: str, args: list) -> HexBytes:
    return HexBytes(encode_human_readable_call(signature, args))


def create_eth_transfer(
    sender: str, nonce: int, to: str, value: int, **kwargs
) -> "UserOperation":
    data = encode_function_call(
        "execute(address,uint256,bytes)",
        [to_checksum_address(to), value, b""],
    )
    return UserOperation(sender, nonce, None, b"", data, **kwargs)


def create_erc20_transfer(
    sender: str, nonce: int, token: str, to: str, amount: int, **kwargs
) -> "UserOperation":
    call = encode_function_call(
        "transfer(address,uint256)", [to_checksum_address(to), amount]
    )
    data = encode_function_call(
        "execute(address,uint256,bytes)", [to_checksum_address(token), 0, call]
    )
    return UserOperation(sender, nonce, None, b"", data, **kwargs)


def create_erc20_approve(
    sender: str, nonce: int, token: str, spender: str, amount: int, **kwargs
) -> "UserOperation":
    call = encode_function_call(
        "approve(address,uint256)", [to_checksum_address(spender), amount]
    )
    data = encode_function_call(
        "execute(address,uint256,bytes)", [to_checksum_address(token), 0, call]
    )
    return UserOperation(sender, nonce, None, b"", data, **kwargs)


def create_contract_call(
    sender: str, nonce: int, target: str, data: HexBytes, value: int = 0, **kwargs
) -> "UserOperation":
    payload = encode_function_call(
        "execute(address,uint256,bytes)", [to_checksum_address(target), value, data]
    )
    return UserOperation(sender, nonce, None, b"", payload, **kwargs)
