"""
 This file is part of nucypher.

 nucypher is free software: you can redistribute it and/or modify
 it under the terms of the GNU Affero General Public License as published by
 the Free Software Foundation, either version 3 of the License, or
 (at your option) any later version.

 nucypher is distributed in the hope that it will be useful,
 but WITHOUT ANY WARRANTY; without even the implied warranty of
 MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 GNU Affero General Public License for more details.

 You should have received a copy of the GNU Affero General Public License
 along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""


from eth_typing import HexStr
from web3 import Web3
from web3._utils.abi import get_constructor_abi, merge_args_and_kwargs
from web3._utils.contracts import encode_abi
from web3.contract import ContractConstructor



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


def encode_constructor_arguments(web3: Web3,
                                 constructor_function: ContractConstructor,
                                 *constructor_args, **constructor_kwargs) -> HexStr:
    """
    Takes a web3 constructor function and the arguments passed to it, and produces an encoding hex string
    of the constructor arguments, following the standard ABI encoding conventions.
    If there's no constructor, it returns None.
    """
    constructor_abi = get_constructor_abi(constructor_function.abi)
    if constructor_abi:
        arguments = merge_args_and_kwargs(constructor_abi, constructor_args, constructor_kwargs)
        data = encode_abi(web3, constructor_abi, arguments)
    else:
        data = None
    return data


def connect_web3_provider(provider_uri: str) -> None:
    """
    Convenience function for connecting to an ethereum provider now.
    This may be used to optimize the startup time of some applications by
    establishing the connection eagarly.
    """
    from nucypher.blockchain.eth.interfaces import BlockchainInterfaceFactory

    if not BlockchainInterfaceFactory.is_interface_initialized(provider_uri=provider_uri):
        BlockchainInterfaceFactory.initialize_interface(provider_uri=provider_uri)
    interface = BlockchainInterfaceFactory.get_interface(provider_uri=provider_uri)
    interface.connect()
