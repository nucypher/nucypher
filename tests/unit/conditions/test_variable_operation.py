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
    # - bool, str: explicitly designed to handle any type
    if operation in ["bool", "str"]:
        return

    # Skip type error test for operations that may raise exceptions other than TypeError,
    # such as JSONDecodeError for 'fromJson' or ValueError for 'fromHex'.
    # Or operations that have their own specific TypeError tests.
    if operation in ["fromJson", "fromHex", "toHex", "toJson", "keccak"]:
        return

    with pytest.raises(TypeError):
        if operation in ["int", "float"]:
            variable_value = ["some", "list"]
        elif operation in ["%=", "len", "max", "min"]:
            # special cases where the functions can handle strings as the initial variable value
            variable_value = 10
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
