import pytest

from nucypher.policy.conditions.exceptions import RequiredContextVariable
from nucypher.policy.conditions.lingo import (
    _OPERATOR_FUNCTIONS,
    VariableOperation,
)

# (Operation, value, initial, expected)
OPERATION_TEST_CASES = [
    ("+=", 2, 3, 5),
    ("-=", 2, 3, 1),
    ("*=", 2, 3, 6),
    ("/=", 2, 6, 3.0),
    ("%=", 2, 5, 1),
    ("abs", None, -3, 3),
    ("abs", None, 3, 3),
    ("avg", None, [1, 2, 3], 2),
    ("avg", None, [10, 15, 20], 15),
    ("ceil", None, 3.1, 4),
    ("ethToWei", None, 0.000000000000000001, 1),
    ("ethToWei", None, 1.5, 1500000000000000000),
    ("ethToWei", None, 1.1, 1100000000000000000),
    ("floor", None, -3.9, -4),
    ("floor", None, 3.9, 3),
    ("index", 1, [10, 20, 30], 20),
    ("index", 0, [10, 20, 30], 10),
    ("index", 2, [10, 20, 30], 30),
    (
        "index",
        4,
        ["Proper", "preparation", "prevents", "poor", "performance"],
        "performance",
    ),  # -- Ray Lewis
    ("len", None, [1, 2, 3, False, 123.0, "six"], 6),
    ("max", None, [1, 2, 3], 3),
    ("max", None, [123, 25, 35], 123),
    ("min", None, [1, 2, 3], 1),
    ("min", None, [123.4, 50.1, 52], 50.1),
    ("round", 1, 3.1415, 3.1),
    ("round", 2, 3.1415, 3.14),
    ("sum", None, [1, 2, 3], 6),
    ("sum", None, [1232, 22212, 3231], 26675),
    ("toTokenBaseUnits", 18, 1, 1000000000000000000),  # 1 token with 18 decimals
    ("toTokenBaseUnits", 18, 1.5, 1500000000000000000),  # 1.5 tokens with 18 decimals
    ("toTokenBaseUnits", 6, 100, 100000000),  # 100 USDC (6 decimals)
    ("toTokenBaseUnits", 6, 250.5, 250500000),  # 250.5 USDC (6 decimals)
    ("weiToEth", None, 1000000000000000000, 1),
    ("weiToEth", None, 1500000000000000000, 1.5),
    ("weiToEth", None, 1100000000000000000, 1.1),
    # casting
    ("bool", None, 0, False),
    ("bool", None, 1, True),
    ("bool", None, "", False),
    ("bool", None, [], False),
    ("bool", None, "Non-empty string", True),
    ("float", None, 3, 3.0),
    ("float", None, "123.456", 123.456),
    ("int", None, 3.9, 3),
    ("int", None, "123", 123),
    ("str", None, 123, "123"),
    ("str", None, 123.456, "123.456"),
    (
        "str",
        None,
        "Do not confuse one story for all stories",
        "Do not confuse one story for all stories",
    ),  # -- Anonymous
    # JSON conversion
    ("toJson", None, {"key": "value"}, '{"key": "value"}'),
    ("toJson", None, [1, 2, 3], "[1, 2, 3]"),
    ("fromJson", None, '{"key": "value"}', {"key": "value"}),
    ("fromJson", None, "[1, 2, 3]", [1, 2, 3]),
    # hex conversion
    ("toHex", None, b"\x00\x01\x02", "0x000102"),
    ("toHex", None, "test", "0x74657374"),
    ("toHex", None, 17, "0x11"),  # integers supported
    ("toHex", None, bytearray([0x11, 0x22]), "0x1122"),  # bytearray supported
    ("fromHex", None, "0x74657374", b"test"),
    # keccak hashing - returns bytes
    (
        "keccak",
        None,
        "",
        b"\xc5\xd2F\x01\x86\xf7#<\x92~}\xb2\xdc\xc7\x03\xc0\xe5\x00\xb6S\xca\x82';{\xfa\xd8\x04]\x85\xa4p",
    ),
    (
        "keccak",
        None,
        "test",
        b'\x9c"\xff_!\xf0\xb8\x1b\x11>c\xf7\xdbm\xa9O\xed\xef\x11\xb2\x11\x9b@\x88\xb8\x96d\xfb\x9a<\xb6X',
    ),
    (
        "keccak",
        None,
        24,
        b'\xf1\xadZ\xc1\x84\xf0\x82\x1d\x8f\x12\x1f\x00)\xe0\x0fF\xeeg2i\xe9O\xd8v\x97)\x13"\x9fup\xab',
    ),  # int - hashes the byte value 24, not string "24"
    (
        "keccak",
        None,
        b"testing",
        b"_\x16\xf4\xc7\xf1I\xacO\x95\x10\xd9\xcf\x8c\xf3\x84\x03\x8a\xd3H\xb3\xbc\xdc\x01\x91_\x95\xde\x12\xdf\x9d\x1b\x02",
    ),  # bytes
    # create2 - computes CREATE2 address
    (
        "create2",
        {
            "deployerAddress": "0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f",
            "bytecodeHash": "0x96e8ac4277198ff8b6f785478aa9a39f403cb768dd02cbee326c3e7da348845f",
        },
        bytes.fromhex(
            "e18a34eb0e04b04f7a0ac29a6e80748dca96319b42c54d679cb821dca90c6303"
        ),
        "0x879F8Ee9B69D56E3cd4bb78FBf5C0dA93E29bBAb",
    ),
]


def test_invalid_operation():
    with pytest.raises(ValueError, match="Not a permitted operation"):
        VariableOperation(operation="unknown_op", value=2)


@pytest.mark.parametrize("operation", [op for op, *_ in OPERATION_TEST_CASES])
def test_invalid_operation_and_value_combination(operation):
    if VariableOperation._is_unary_operation(operation):
        with pytest.raises(ValueError, match="No value should be provided"):
            VariableOperation(operation=operation, value=2)
    else:
        with pytest.raises(ValueError, match="A value must be provided"):
            VariableOperation(operation=operation)


def test_all_operations_covered():
    tested_operations = [op for op, *_ in OPERATION_TEST_CASES]
    assert set(tested_operations) == _OPERATOR_FUNCTIONS.keys()


def test_variable_operation_list_empty():
    with pytest.raises(ValueError):
        VariableOperation.evaluate_operations([], 10)


@pytest.mark.parametrize("operation", [op for op, *_ in OPERATION_TEST_CASES])
def test_type_errors_in_evaluation(operation):
    value = [
        "random",
        "list",
        "that",
        "doesn't",
        "make",
        "sense",
        "for",
        "most",
        "operations",
    ]
    if VariableOperation._is_unary_operation(operation):
        op = VariableOperation(operation=operation)
    else:
        op = VariableOperation(operation=operation, value=value)
    # Skip type error test for operations that can handle any input without raising TypeError.
    # These operations are designed to accept any input type and will not raise TypeError.
    if operation in ["bool", "str"]:
        return

    with pytest.raises(TypeError):
        if operation in ["int", "float", "fromJson", "toHex", "fromHex", "keccak"]:
            variable_value = ["some", "list"]
        elif operation in ["%=", "len", "max", "min"]:
            # special cases where the functions can handle strings as the initial variable value
            variable_value = 10
        elif operation in ["toJson"]:
            variable_value = b"abc"  # bytes are not JSON serializable
        else:
            variable_value = "initial_value_that_does_not_make_sense"

        VariableOperation.evaluate_operations([op], variable_value)


@pytest.mark.parametrize("operation,value,initial,expected", OPERATION_TEST_CASES)
def test_variable_operation_evaluation(operation, value, initial, expected):
    op = VariableOperation(operation=operation, value=value)
    result = VariableOperation.evaluate_operations([op], initial)
    assert result == expected


def test_cascading_operations():
    initial = [5, 6, 10, 20]
    operations = [
        VariableOperation(operation="index", value=2),  # 10
        VariableOperation(operation="-=", value=2),  # 8
        VariableOperation(operation="*=", value=3),  # 24
        VariableOperation(operation="/=", value=4),  # 6
        VariableOperation(operation="+=", value=10),  # 16
        VariableOperation(operation="%=", value=9),  # 7
        VariableOperation(operation="abs"),  # 7
        VariableOperation(operation="ethToWei"),  # 7000000000000000000
    ]
    result = VariableOperation.evaluate_operations(operations, initial)
    assert result == 7000000000000000000


def test_float_operations_and_precision():
    initial = 0
    operations = [
        VariableOperation(operation="+=", value=0.1),  # 0.1
        VariableOperation(operation="+=", value=0.1),  # 0.2
        VariableOperation(operation="+=", value=0.1),  # 0.3
        VariableOperation(operation="-=", value=0.3),  # 0
    ]
    result = VariableOperation.evaluate_operations(operations, initial)
    assert result == 0

    # test where initial is value is a float
    initial = 0.123
    operations = [
        VariableOperation(operation="-=", value=0.1),  # 0.023
        VariableOperation(operation="-=", value=0.02),  # 0.003
        VariableOperation(operation="-=", value=0.003),  # 0
    ]
    result = VariableOperation.evaluate_operations(operations, initial)
    assert result == 0

    # test where final result is a float
    initial = 0.123
    operations = [
        VariableOperation(operation="+=", value=0.0001),  # 0.1231
        VariableOperation(operation="+=", value=0.0009),  # 0.124
        VariableOperation(operation="+=", value=0.00001),  # 0.12401
        VariableOperation(operation="+=", value=0.0000011),  # 0.1240111
        VariableOperation(operation="-=", value=0.0000001),  # 0.1240110
    ]
    result = VariableOperation.evaluate_operations(operations, initial)
    assert result == 0.124011

    # test sum of floats
    initial = [0.123, 0.245, 0.6896]
    operations = [
        VariableOperation(operation="sum"),  # 1.0576
    ]
    result = VariableOperation.evaluate_operations(operations, initial)
    assert result == 1.0576

    # index from list then subsequent float operations
    initial = [0, 1, 2, 0.123]
    operations = [
        VariableOperation(operation="index", value=3),  # 0.123
        VariableOperation(operation="+=", value=0.245),  # 0.368
        VariableOperation(operation="+=", value=0.6896),  # 1.0576
    ]
    result = VariableOperation.evaluate_operations(operations, initial)
    assert result == 1.0576

    # index from dict then subsequent float operations
    initial = {
        "index_0": 0,
        "index_1": 1,
        "index_2": 2,
        "index_3": 0.123,
    }
    operations = [
        VariableOperation(operation="index", value="index_3"),  # 0.123
        VariableOperation(operation="+=", value=0.245),  # 0.368
        VariableOperation(operation="+=", value=0.6896),  # 1.0576
    ]
    result = VariableOperation.evaluate_operations(operations, initial)
    assert result == 1.0576


def test_overloaded_operators():
    initial = []
    operations = [
        VariableOperation(operation="+=", value=["T"]),  # T
        VariableOperation(operation="+=", value=["A"]),  # TA
        VariableOperation(operation="+=", value=["C"]),  # TAC
        VariableOperation(operation="+=", value=["o"]),  # TACo
    ]
    result = VariableOperation.evaluate_operations(operations, initial)
    assert result == ["T", "A", "C", "o"]

    initial = ""
    operations = [
        VariableOperation(operation="+=", value="T"),  # T
        VariableOperation(operation="+=", value="A"),  # TA
        VariableOperation(operation="+=", value="C"),  # TAC
        VariableOperation(operation="+=", value="o"),  # TACo
    ]
    result = VariableOperation.evaluate_operations(operations, initial)
    assert result == "TACo"

    initial = "TACo"
    operations = [
        VariableOperation(operation="*=", value=3),  # TACoTACoTACo
        VariableOperation(operation="+=", value="!"),  # TACoTACoTACo!
    ]
    result = VariableOperation.evaluate_operations(operations, initial)
    assert result == "TACoTACoTACo!"


def test_string_concatenation():
    # Test basic string concatenation
    initial = "Hello"
    operations = [
        VariableOperation(operation="+=", value=" "),
        VariableOperation(operation="+=", value="World"),
    ]
    result = VariableOperation.evaluate_operations(operations, initial)
    assert result == "Hello World"

    # Test building a sentence word by word
    initial = ""
    operations = [
        VariableOperation(operation="+=", value="Threshold"),
        VariableOperation(operation="+=", value=" "),
        VariableOperation(operation="+=", value="Access"),
        VariableOperation(operation="+=", value=" "),
        VariableOperation(operation="+=", value="Control"),
    ]
    result = VariableOperation.evaluate_operations(operations, initial)
    assert result == "Threshold Access Control"

    # Test string multiplication followed by concatenation
    initial = "Nu"
    operations = [
        VariableOperation(operation="*=", value=2),  # NuNu
        VariableOperation(operation="+=", value="Cypher"),  # NuNuCypher
    ]
    result = VariableOperation.evaluate_operations(operations, initial)
    assert result == "NuNuCypher"


def test_json_hex_conversion_operators():
    # Test JSON to hex and back
    initial = {"address": "0x123", "amount": 100}
    operations = [
        VariableOperation(operation="toJson"),  # '{"address": "0x123", "amount": 100}'
        VariableOperation(operation="toHex"),  # hex representation
        VariableOperation(operation="fromHex"),  # back to JSON string bytes
        VariableOperation(operation="fromJson"),  # back to original dict
    ]
    result = VariableOperation.evaluate_operations(operations, initial)
    assert result == initial

    # Test hex conversion round trip
    initial = b"\xde\xad\xbe\xef"
    operations = [
        VariableOperation(operation="toHex"),  # "0xdeadbeef"
    ]
    result = VariableOperation.evaluate_operations(operations, initial)
    assert result == "0xdeadbeef"

    # Convert back
    operations = [
        VariableOperation(operation="fromHex"),  # b"\xde\xad\xbe\xef"
    ]
    result = VariableOperation.evaluate_operations(operations, result)
    assert result == initial


def test_keccak_hashing():
    # Test keccak of empty string - returns bytes
    initial = ""
    operations = [
        VariableOperation(operation="keccak"),
    ]
    result = VariableOperation.evaluate_operations(operations, initial)
    assert (
        result
        == b"\xc5\xd2F\x01\x86\xf7#<\x92~}\xb2\xdc\xc7\x03\xc0\xe5\x00\xb6S\xca\x82';{\xfa\xd8\x04]\x85\xa4p"
    )

    # Test keccak of a known string - returns bytes
    initial = "test"
    operations = [
        VariableOperation(operation="keccak"),
    ]
    result = VariableOperation.evaluate_operations(operations, initial)
    assert (
        result
        == b'\x9c"\xff_!\xf0\xb8\x1b\x11>c\xf7\xdbm\xa9O\xed\xef\x11\xb2\x11\x9b@\x88\xb8\x96d\xfb\x9a<\xb6X'
    )

    # Test keccak of bytes
    initial = b"test"
    operations = [
        VariableOperation(operation="keccak"),
    ]
    result = VariableOperation.evaluate_operations(operations, initial)
    assert (
        result
        == b'\x9c"\xff_!\xf0\xb8\x1b\x11>c\xf7\xdbm\xa9O\xed\xef\x11\xb2\x11\x9b@\x88\xb8\x96d\xfb\x9a<\xb6X'
    )


def test_json_hex_comparison_use_case():
    """
    Test the practical use case of comparing hex representation with object representation
    to ensure they represent the same data.
    """
    # Start with an object
    original_object = {"address": "0xabc", "value": 42, "nested": {"key": "data"}}

    # Convert to JSON, then to hex
    operations_to_hex = [
        VariableOperation(operation="toJson"),
        VariableOperation(operation="toHex"),
    ]
    hex_representation = VariableOperation.evaluate_operations(
        operations_to_hex, original_object
    )

    # Now convert hex back to object and compare
    operations_from_hex = [
        VariableOperation(operation="fromHex"),
        VariableOperation(operation="fromJson"),
    ]
    reconstructed_object = VariableOperation.evaluate_operations(
        operations_from_hex, hex_representation
    )

    # They should be equal
    assert reconstructed_object == original_object


def test_context_variable_resolution_in_operations():
    # various operations with context variables
    initial = 10
    context = {":increment": 5, ":multiplier": 3}
    operations = [
        VariableOperation(operation="+=", value=":increment"),  # 15
        VariableOperation(operation="*=", value=":multiplier"),  # 45
        VariableOperation(operation="-=", value=10),  # 35
    ]

    with pytest.raises(RequiredContextVariable):
        VariableOperation.with_resolved_context(
            operations, context={}
        )  # missing context variables

    resolved_operations = VariableOperation.with_resolved_context(operations, **context)
    result = VariableOperation.evaluate_operations(resolved_operations, initial)
    assert result == 35


def test_tohex_type_errors():
    """Test that toHex raises TypeError for unsupported types like float"""
    op = VariableOperation(operation="toHex")

    # Test that float raises TypeError
    with pytest.raises(TypeError, match="Invalid value for hex conversion"):
        VariableOperation.evaluate_operations([op], 3.14)

    # Test that None raises TypeError
    with pytest.raises(TypeError, match="Invalid value for hex conversion"):
        VariableOperation.evaluate_operations([op], None)

    # Test that list raises TypeError
    with pytest.raises(TypeError, match="Invalid value for hex conversion"):
        VariableOperation.evaluate_operations([op], [1, 2, 3])


def test_tojson_type_errors():
    """Test that toJson raises TypeError for unsupported types like bytes"""
    op = VariableOperation(operation="toJson")

    # Test that bytes raises TypeError
    with pytest.raises(
        TypeError, match="Object of type bytes is not JSON serializable"
    ):
        VariableOperation.evaluate_operations([op], b"test")


def test_to_token_base_units_operator():
    """Test toTokenBaseUnits operator for ERC-20 token decimal conversion."""
    # USDC (6 decimals): 100 tokens -> 100000000 base units
    initial = 100
    operations = [
        VariableOperation(operation="toTokenBaseUnits", value=6),
    ]
    result = VariableOperation.evaluate_operations(operations, initial)
    assert result == 100000000

    # ETH/most tokens (18 decimals): 1 token -> 1000000000000000000 base units
    initial = 1
    operations = [
        VariableOperation(operation="toTokenBaseUnits", value=18),
    ]
    result = VariableOperation.evaluate_operations(operations, initial)
    assert result == 1000000000000000000

    # 250.5 tokens with 6 decimals
    initial = 250.5
    operations = [
        VariableOperation(operation="toTokenBaseUnits", value=6),
    ]
    result = VariableOperation.evaluate_operations(operations, initial)
    assert result == 250500000


def test_to_token_base_units_high_precision():
    """
    Test toTokenBaseUnits with high precision values that would fail with float arithmetic.

    This is the key test case that motivated replacing *pow= with toTokenBaseUnits.
    Float precision is limited to ~17 digits, so 0.123456789012345678 * 10^18 would
    fail with float arithmetic but succeeds with Decimal + int conversion.

    In practice, high precision values come from JSON as strings which get converted
    to Decimals via _convert_any_floats_to_decimal before reaching toTokenBaseUnits.
    Python float literals can't represent 18+ digits of precision, so we test with
    Decimal inputs which reflects the real-world flow.
    """
    from decimal import Decimal

    # High precision case - using Decimal as values come from JSON strings in practice
    initial = Decimal("0.123456789012345678")  # 18 decimal places
    operations = [
        VariableOperation(operation="toTokenBaseUnits", value=18),
    ]
    result = VariableOperation.evaluate_operations(operations, initial)
    assert result == 123456789012345678

    # Another high precision case
    initial = Decimal("0.999999999999999999")
    operations = [
        VariableOperation(operation="toTokenBaseUnits", value=18),
    ]
    result = VariableOperation.evaluate_operations(operations, initial)
    assert result == 999999999999999999


def test_to_token_base_units_edge_cases():
    """Test edge cases for toTokenBaseUnits operator."""
    # Zero tokens
    initial = 0
    operations = [
        VariableOperation(operation="toTokenBaseUnits", value=18),
    ]
    result = VariableOperation.evaluate_operations(operations, initial)
    assert result == 0

    # Whole number tokens
    initial = 1000
    operations = [
        VariableOperation(operation="toTokenBaseUnits", value=6),
    ]
    result = VariableOperation.evaluate_operations(operations, initial)
    assert result == 1000000000

    # Zero decimals (token with no decimals)
    initial = 100
    operations = [
        VariableOperation(operation="toTokenBaseUnits", value=0),
    ]
    result = VariableOperation.evaluate_operations(operations, initial)
    assert result == 100

    # Very small amount
    initial = 0.000001
    operations = [
        VariableOperation(operation="toTokenBaseUnits", value=18),
    ]
    result = VariableOperation.evaluate_operations(operations, initial)
    assert result == 1000000000000


def test_to_token_base_units_type_errors():
    """Test that toTokenBaseUnits raises TypeError for invalid inputs."""
    op = VariableOperation(operation="toTokenBaseUnits", value=18)

    # Test that non-numeric value raises TypeError
    with pytest.raises(TypeError, match="Invalid value for toTokenBaseUnits"):
        VariableOperation.evaluate_operations([op], "not a number")

    # Test that list raises TypeError
    with pytest.raises(TypeError, match="Invalid value for toTokenBaseUnits"):
        VariableOperation.evaluate_operations([op], [1, 2, 3])


def test_create2_operation():
    """Test CREATE2 address computation with known values."""
    # Known test vectors - deployer, salt, bytecode_hash -> expected address
    # Using the Uniswap V2 pair creation as reference pattern
    deployer = "0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f"  # Uniswap V2 Factory
    bytecode_hash = "0x96e8ac4277198ff8b6f785478aa9a39f403cb768dd02cbee326c3e7da348845f"

    # Salt from keccak256 of token pair
    salt = bytes.fromhex(
        "e18a34eb0e04b04f7a0ac29a6e80748dca96319b42c54d679cb821dca90c6303"
    )

    operations = [
        VariableOperation(
            operation="create2",
            value={
                "deployerAddress": deployer,
                "bytecodeHash": bytecode_hash,
            },
        ),
    ]
    result = VariableOperation.evaluate_operations(operations, salt)

    # Expected address computed from CREATE2 formula
    assert result == "0x879F8Ee9B69D56E3cd4bb78FBf5C0dA93E29bBAb"


def test_create2_invalid_salt_length():
    """Test that create2 fails with non-32-byte salt."""
    deployer = "0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f"
    bytecode_hash = "0x96e8ac4277198ff8b6f785478aa9a39f403cb768dd02cbee326c3e7da348845f"

    # 16-byte salt (too short)
    short_salt = bytes.fromhex("e18a34eb0e04b04f7a0ac29a6e807400")

    operations = [
        VariableOperation(
            operation="create2",
            value={
                "deployerAddress": deployer,
                "bytecodeHash": bytecode_hash,
            },
        ),
    ]

    with pytest.raises(TypeError, match="salt must be 32 bytes"):
        VariableOperation.evaluate_operations(operations, short_salt)


def test_create2_invalid_deployer_length():
    """Test that create2 fails with non-20-byte deployer address."""
    # 10-byte address (too short)
    deployer = "0x5C69bEe701ef814a2B6a"
    bytecode_hash = "0x96e8ac4277198ff8b6f785478aa9a39f403cb768dd02cbee326c3e7da348845f"
    salt = bytes.fromhex(
        "e18a34eb0e04b04f7a0ac29a6e80748dca96319b42c54d679cb821dca90c6303"
    )

    operations = [
        VariableOperation(
            operation="create2",
            value={
                "deployerAddress": deployer,
                "bytecodeHash": bytecode_hash,
            },
        ),
    ]

    with pytest.raises(TypeError, match="deployerAddress must be 20 bytes"):
        VariableOperation.evaluate_operations(operations, salt)


def test_create2_invalid_bytecode_hash_length():
    """Test that create2 fails with non-32-byte bytecode hash."""
    deployer = "0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f"
    # 16-byte hash (too short)
    bytecode_hash = "0x96e8ac4277198ff8b6f785478aa9a39f"
    salt = bytes.fromhex(
        "e18a34eb0e04b04f7a0ac29a6e80748dca96319b42c54d679cb821dca90c6303"
    )

    operations = [
        VariableOperation(
            operation="create2",
            value={
                "deployerAddress": deployer,
                "bytecodeHash": bytecode_hash,
            },
        ),
    ]

    with pytest.raises(TypeError, match="bytecodeHash must be 32 bytes"):
        VariableOperation.evaluate_operations(operations, salt)


def test_create2_missing_value_fields():
    """Test that create2 fails when required fields are missing from value."""
    salt = bytes.fromhex(
        "e18a34eb0e04b04f7a0ac29a6e80748dca96319b42c54d679cb821dca90c6303"
    )

    # Missing bytecodeHash
    operations = [
        VariableOperation(
            operation="create2",
            value={
                "deployerAddress": "0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f",
            },
        ),
    ]

    with pytest.raises(
        TypeError,
        match="create2 operation requires dictionary with 'deployerAddress' and 'bytecodeHash' values",
    ):
        VariableOperation.evaluate_operations(operations, salt)

    # Missing deployerAddress
    operations = [
        VariableOperation(
            operation="create2",
            value={
                "bytecodeHash": "0x96e8ac4277198ff8b6f785478aa9a39f403cb768dd02cbee326c3e7da348845f",
            },
        ),
    ]

    with pytest.raises(
        TypeError,
        match="create2 operation requires dictionary with 'deployerAddress' and 'bytecodeHash' values",
    ):
        VariableOperation.evaluate_operations(operations, salt)

    # Empty value
    operations = [
        VariableOperation(
            operation="create2",
            value={},
        ),
    ]

    with pytest.raises(
        TypeError,
        match="create2 operation requires dictionary with 'deployerAddress' and 'bytecodeHash' values",
    ):
        VariableOperation.evaluate_operations(operations, salt)


def test_create2_with_context_variables():
    """Test that create2 value fields support context variable resolution."""
    salt = bytes.fromhex(
        "e18a34eb0e04b04f7a0ac29a6e80748dca96319b42c54d679cb821dca90c6303"
    )

    context = {
        ":factoryAddress": "0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f",
        ":initCodeHash": "0x96e8ac4277198ff8b6f785478aa9a39f403cb768dd02cbee326c3e7da348845f",
    }

    operations = [
        VariableOperation(
            operation="create2",
            value={
                "deployerAddress": ":factoryAddress",
                "bytecodeHash": ":initCodeHash",
            },
        ),
    ]

    # Resolve context variables
    resolved_operations = VariableOperation.with_resolved_context(operations, **context)

    # Execute
    result = VariableOperation.evaluate_operations(resolved_operations, salt)

    assert result == "0x879F8Ee9B69D56E3cd4bb78FBf5C0dA93E29bBAb"


def test_create2_discord_id_to_aa_address():
    """
    Test the full pipeline from Discord ID to AA address.

    This replicates the real-world use case:
    1. Start with a Discord user ID
    2. Concatenate with "|Discord|Collab.Land"
    3. Hash with keccak256 to get the salt
    4. Compute CREATE2 address using SimpleFactory on Base Sepolia

    Values from discord-taco-web validate-aa-derivation.ts script.
    """
    # Real Discord user ID
    discord_id = 405651072460259339

    # SimpleFactory on Base Sepolia
    deployer = "0x69Aa2f9fe1572F1B640E1bbc512f5c3a734fc77c"
    # Bytecode hash for MetaMask Delegation Toolkit MultiSig
    bytecode_hash = "0x210ffc0da7f274285c4d6116aaef8420ecb9054faced33862197d6b951cb32f5"

    operations = [
        VariableOperation(operation="str"),  # "405651072460259339"
        VariableOperation(
            operation="+=", value="|Discord|Collab.Land"
        ),  # "405651072460259339|Discord|Collab.Land"
        VariableOperation(operation="keccak"),  # salt as bytes32
        VariableOperation(
            operation="create2",
            value={
                "deployerAddress": deployer,
                "bytecodeHash": bytecode_hash,
            },
        ),
    ]

    result = VariableOperation.evaluate_operations(operations, discord_id)

    # Expected AA address for this Discord ID
    assert result == "0x420AcFa51fdB2821dFb407e212A882144807737C"
