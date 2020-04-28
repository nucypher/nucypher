from web3 import Web3


def to_bytes32(value=None, hexstr=None) -> bytes:
    return Web3.toBytes(primitive=value, hexstr=hexstr).rjust(32, b'\0')


def to_32byte_hex(value=None, hexstr=None) -> str:
    return Web3.toHex(to_bytes32(value=value, hexstr=hexstr))


def get_mapping_entry_location(key: bytes, mapping_location: int) -> int:
    if not(isinstance(key, bytes) and len(key) == 32):
        raise ValueError("Mapping key must be a 32-long bytestring")
    # See https://solidity.readthedocs.io/en/latest/internals/layout_in_storage.html#mappings-and-dynamic-arrays
    entry_location = Web3.toInt(Web3.keccak(key + mapping_location.to_bytes(32, "big")))
    return entry_location


def get_array_data_location(array_location: int) -> int:
    # See https://solidity.readthedocs.io/en/latest/internals/layout_in_storage.html#mappings-and-dynamic-arrays
    data_location = Web3.toInt(Web3.keccak(to_bytes32(array_location)))
    return data_location
