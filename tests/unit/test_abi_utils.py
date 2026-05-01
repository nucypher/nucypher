import os

import pytest
from eth_utils import keccak

from nucypher.utilities.abi import (
    decode_human_readable_call,
    encode_human_readable_call,
    is_valid_human_readable_signature,
    parse_tuple_fields,
    resolve_abi_type_with_indices,
)


@pytest.mark.parametrize(
    "human_signature, expected",
    [
        # Valid signatures
        ("transfer(address,uint256)", True),
        ("approve(address,uint256)", True),
        ("transferFrom(address,address,uint256)", True),
        ("mint(address,uint256)", True),
        ("burn(uint256)", True),
        ("baseTypes(uint,int,bool,address,bytes,string)", True),
        ("otherTypes(uint256,uint128,int32,int8,bytes1,bytes32)", True),
        ("tupleType((string,uint256,address))", True),
        ("arrayType(uint256[],address[])", True),
        ("tupleArrayType((string,uint256,address)[])", True),
        ("nestedTupleType(address,(string,uint256,(address,bool)))", True),
        # Failure cases
        ("invalidSignature", False),  # Invalid signature
        ("123start(address,uint256)", False),  # Invalid function name
        ("!start(address,uint256)", False),  # Invalid function name
        ("bad(!!!, address)", False),  # Invalid typ
        ("transfer(address,uint257)", False),  # Invalid type
        ("transfer(address,uint256", False),  # Missing closing parenthesis
        (
            "execute(address,uint256,(address,uint256,bytes)",
            False,
        ),  # Missing closing parenthesis
        ("transfer(,uint256)", False),  # Empty argument type
        ("transfer(address,uint256) extra", False),  # Extra text after signature
    ],
)
def test_valid_human_readable_signature(human_signature, expected):
    assert is_valid_human_readable_signature(human_signature) == expected


@pytest.mark.parametrize(
    "human_signature, expected_method_name, args",
    [
        (
            "transfer(address,uint256)",
            "transfer",
            ["0x1234567890abcdef1234567890abcdef12345678", 100],
        ),
        (
            "approve(address,uint256)",
            "approve",
            ["0x1234567890abcdef1234567890abcdef12345678", 100],
        ),
        (
            "transferFrom(address,address,uint256)",
            "transferFrom",
            [
                "0xc83eb7e5431211ee841ccbb917f2133ec9f3ed8f",
                "0x7dd2cd8f0ac7ec77842c40db6938cadd2a4deb36",
                10000,
            ],
        ),
        (
            "mint(address,int256)",
            "mint",
            ["0x1234567890abcdef1234567890abcdef12345678", -1],
        ),
        ("burn(uint256,bool)", "burn", [100, True]),
        (
            "baseTypes(uint,int,bool,address,bytes,string)",
            "baseTypes",
            [
                1,
                2,
                False,
                "0x1234567890abcdef1234567890abcdef12345678",
                os.urandom(15),
                "test",
            ],
        ),
        (
            "otherTypes(uint256,uint128,int32,int8,bytes1,bytes32)",
            "otherTypes",
            [1000, 128, -32, -8, os.urandom(1), os.urandom(32)],
        ),
        (
            "tupleType((string,uint256,address))",
            "tupleType",
            [("Alice", 30, "0x1234567890abcdef1234567890abcdef12345678")],
        ),
        # note array values are returned as tuples (for the following test scenario)
        (
            "arrayType(uint256[],address[])",
            "arrayType",
            [
                (1, 2, 3),
                (
                    "0x1234567890abcdef1234567890abcdef12345678",
                    "0xabcdef1234567890abcdef1234567890abcdef12",
                ),
            ],
        ),
        (
            "tupleArrayType((string,uint256,address)[])",
            "tupleArrayType",
            [
                (
                    ("Alice", 30, "0x1234567890abcdef1234567890abcdef12345678"),
                    ("Bob", 45, "0xabcdef1234567890abcdef1234567890abcdef12"),
                )
            ],
        ),
        (
            "nestedTupleType(address,(string,uint256,(address,bool)))",
            "nestedTupleType",
            [
                "0x1234567890abcdef1234567890abcdef12345678",
                ("Alice", 30, ("0xabcdef1234567890abcdef1234567890abcdef12", False)),
            ],
        ),
    ],
)
def test_encode_decode_human_readable_abi(human_signature, expected_method_name, args):
    # Encode
    encoded_call_data = encode_human_readable_call(human_signature, args)
    assert isinstance(encoded_call_data, bytes)

    # Decode (method name instead of bytes selector)
    method, decoded_args = decode_human_readable_call(
        human_signature, encoded_call_data, return_method_name=True
    )
    assert method == expected_method_name
    assert decoded_args == args

    # Decode (bytes selector instead of method name)
    method, decoded_args = decode_human_readable_call(
        human_signature, encoded_call_data, return_method_name=False
    )
    assert method == keccak(text=human_signature)[:4]
    assert decoded_args == args

    # Decoded selector does not match encoded call data
    with pytest.raises(ValueError, match="Call data does not match function selector"):
        decode_human_readable_call(
            "differentHumanSignatureFromValuesInTest(address)",
            encoded_call_data,
            return_method_name=True,
        )


@pytest.mark.parametrize(
    "tuple_type, expected_fields",
    [
        ("(address,uint256,bytes)", ["address", "uint256", "bytes"]),
        ("(address)", ["address"]),
        ("((address,uint256),bytes)", ["(address,uint256)", "bytes"]),
        ("(address[],(uint256,bool),bytes)", ["address[]", "(uint256,bool)", "bytes"]),
        (
            "((address,uint256)[],bytes,uint256)",
            ["(address,uint256)[]", "bytes", "uint256"],
        ),
    ],
)
def test_parse_tuple_fields(tuple_type, expected_fields):
    assert parse_tuple_fields(tuple_type) == expected_fields


def test_parse_tuple_fields_invalid():
    with pytest.raises(ValueError, match="Not a tuple type"):
        parse_tuple_fields("address")

    with pytest.raises(ValueError, match="Not a tuple type"):
        parse_tuple_fields("uint256[]")


@pytest.mark.parametrize(
    "abi_type, sub_indices, expected_type",
    [
        # Simple array indexing
        ("address[]", [0], "address"),
        ("uint256[]", [0], "uint256"),
        # Simple tuple indexing
        ("(address,uint256,bytes)", [0], "address"),
        ("(address,uint256,bytes)", [1], "uint256"),
        ("(address,uint256,bytes)", [2], "bytes"),
        # Array of tuples (array first, then tuple)
        ("(address,uint256,bytes)[]", [0], "(address,uint256,bytes)"),
        ("(address,uint256,bytes)[]", [0, 0], "address"),
        ("(address,uint256,bytes)[]", [0, 1], "uint256"),
        ("(address,uint256,bytes)[]", [0, 2], "bytes"),
        # Tuple of arrays (tuple first, then array)
        ("(address[],uint256[],bytes)", [0], "address[]"),
        ("(address[],uint256[],bytes)", [0, 0], "address"),
        ("(address[],uint256[],bytes)", [1, 0], "uint256"),
        # Deeply nested
        ("((address,uint256)[],bytes)[]", [0], "((address,uint256)[],bytes)"),
        ("((address,uint256)[],bytes)[]", [0, 0], "(address,uint256)[]"),
        ("((address,uint256)[],bytes)[]", [0, 0, 0], "(address,uint256)"),
        ("((address,uint256)[],bytes)[]", [0, 0, 0, 0], "address"),
        ("((address,uint256)[],bytes)[]", [0, 0, 0, 1], "uint256"),
        ("((address,uint256)[],bytes)[]", [0, 1], "bytes"),
        # Empty indices returns original type
        ("(address,uint256,bytes)[]", [], "(address,uint256,bytes)[]"),
    ],
)
def test_resolve_abi_type_with_indices(abi_type, sub_indices, expected_type):
    assert resolve_abi_type_with_indices(abi_type, sub_indices) == expected_type


def test_resolve_abi_type_with_indices_errors():
    # Index into non-indexable type
    with pytest.raises(ValueError, match="not indexable"):
        resolve_abi_type_with_indices("address", [0])

    with pytest.raises(ValueError, match="not indexable"):
        resolve_abi_type_with_indices("uint256", [0])

    # Tuple index out of range
    with pytest.raises(ValueError, match="out of range"):
        resolve_abi_type_with_indices("(address,uint256)", [5])

    # Multiple steps with error at second step
    with pytest.raises(ValueError, match="not indexable"):
        resolve_abi_type_with_indices(
            "(address,uint256)[]", [0, 0, 0]
        )  # address is not indexable
