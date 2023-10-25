import os
import random
from collections import namedtuple
from typing import NamedTuple

import pytest
from hexbytes import HexBytes

from nucypher.policy.conditions.exceptions import ReturnValueEvaluationError
from nucypher.policy.conditions.lingo import ReturnValueTest


def test_return_value_test_schema():
    schema = ReturnValueTest.ReturnValueTestSchema()
    return_value_test = ReturnValueTest(comparator=">", value=0, index=1)

    test_dict = schema.dump(return_value_test)

    # no issues here
    errors = schema.validate(data=test_dict)
    assert not errors, f"{errors}"

    # missing comparator should cause error
    test_dict = schema.dump(return_value_test)
    del test_dict["comparator"]
    errors = schema.validate(data=test_dict)
    assert errors, f"{errors}"

    # missing value should cause error
    test_dict = schema.dump(return_value_test)
    del test_dict["value"]
    errors = schema.validate(data=test_dict)
    assert errors, f"{errors}"

    # missing index should NOT cause any error since optional
    test_dict = schema.dump(return_value_test)
    del test_dict["index"]
    errors = schema.validate(data=test_dict)
    assert not errors, f"{errors}"


def test_return_value_index_invalid():
    with pytest.raises(ReturnValueTest.InvalidExpression):
        _ = ReturnValueTest(comparator=">", value="0", index="james")


def test_return_value_index():
    test = ReturnValueTest(comparator=">", value="0", index=0)
    assert test.eval([1])
    assert not test.eval([-1])

    test = ReturnValueTest(comparator="==", value='"james"', index=3)
    assert test.eval([0, 1, 2, '"james"'])

    with pytest.raises(ReturnValueEvaluationError):
        test.eval([0, 1, 2])


def test_return_value_index_tuple():
    test = ReturnValueTest(comparator=">", value="0", index=0)
    assert test.eval((1,))
    assert not test.eval((-1,))


@pytest.mark.parametrize(
    "comparator",
    [
        "eq",
        "=",
        "+",
        "*",
        "/",
        "DROP",
    ],
)
def test_return_value_test_invalid_comparators(comparator):
    with pytest.raises(
        ReturnValueTest.InvalidExpression, match="not a permitted comparator"
    ):
        _ = ReturnValueTest(comparator=comparator, value=1)


def test_eval_is_evil():
    # TODO look into more malicious fuzzing cases
    file = f"file_{os.urandom(10).hex()}"
    assert not os.path.isfile(file)
    with pytest.raises(ReturnValueTest.InvalidExpression):
        _test = ReturnValueTest(
            comparator=">",
            value=f"(lambda: (42, __import__('os').system('touch {file}'))[0])()",
        )
    assert not os.path.isfile(file)


def test_return_value_test_with_context_variable_cant_run_eval():
    # known context variable
    test = ReturnValueTest(comparator="==", value=":userAddress")
    with pytest.raises(RuntimeError):
        test.eval("0xaDD9D957170dF6F33982001E4c22eCCdd5539118")

    # fake context variable
    test = ReturnValueTest(comparator="==", value=":fakeContextVar")
    with pytest.raises(RuntimeError):
        test.eval(0)


def test_return_value_test_integer():
    # >
    test = ReturnValueTest(comparator='>', value='0')
    assert test.eval('1')
    assert not test.eval('-1')
    # mixing types can work
    assert test.eval(1)
    assert not test.eval(-1)

    test = ReturnValueTest(comparator='>', value=0)
    assert test.eval(1)
    assert not test.eval(0)
    assert not test.eval(-1)
    # mixed types
    assert test.eval("1")
    assert not test.eval("0")

    # >=
    test = ReturnValueTest(comparator=">=", value=1)
    assert test.eval(2)
    assert test.eval(1)
    assert not test.eval(-2)

    # <
    test = ReturnValueTest(comparator="<", value=2)
    assert not test.eval(3)
    assert not test.eval(2)
    assert test.eval(-3)

    # <=
    test = ReturnValueTest(comparator="<=", value=-1)
    assert not test.eval(3)
    assert test.eval(-1)
    assert test.eval(-3)

    # ==
    test = ReturnValueTest(comparator="==", value=4)
    assert not test.eval(1)
    assert test.eval(4)
    assert not test.eval(-2)

    # !=
    test = ReturnValueTest(comparator="!=", value=20)
    assert test.eval(1)
    assert not test.eval(20)
    assert test.eval(-2)


def test_return_value_test_string():
    # string values must be quoted
    with pytest.raises(ReturnValueTest.InvalidExpression):
        _test = ReturnValueTest(comparator="==", value="foo")

    test = ReturnValueTest(comparator='==', value='"foo"')
    assert test.eval('"foo"')
    assert not test.eval('"bar"')

    test = ReturnValueTest(comparator="!=", value='"foo"')
    assert not test.eval('"foo"')
    assert test.eval('"bar"')

    # mixing types works because the value is evaluated as an int, not a string
    test = ReturnValueTest(
        comparator="==", value="0xaDD9D957170dF6F33982001E4c22eCCdd5539118"
    )
    assert test.eval(992513598061863249514433594012370110655092723992)
    assert test.eval("0xaDD9D957170dF6F33982001E4c22eCCdd5539118")
    assert not test.eval("0xdeadbeef")

    test = ReturnValueTest(
        comparator="!=", value="0xaDD9D957170dF6F33982001E4c22eCCdd5539118"
    )
    assert not test.eval("0xaDD9D957170dF6F33982001E4c22eCCdd5539118")
    assert test.eval("0xdeadbeef")


def test_return_value_test_bool():
    test = ReturnValueTest(comparator="==", value=True)
    assert test.eval(True)
    assert not test.eval(False)
    assert test.eval("True")
    assert not test.eval("False")

    test = ReturnValueTest(comparator="!=", value=False)
    assert test.eval(True)
    assert not test.eval(False)
    assert test.eval("True")
    assert not test.eval("False")

    test = ReturnValueTest(comparator="==", value="True")
    assert test.eval(True)
    assert not test.eval(False)
    assert test.eval("True")
    assert not test.eval("False")

    test = ReturnValueTest(comparator="!=", value="False")
    assert test.eval(True)
    assert not test.eval(False)
    assert test.eval("True")
    assert not test.eval("False")


def test_return_value_test_bytes():
    value = b"\xe4\xe4u\x18\x03\x81i\xb74\x0e\xf5\xeb\x18\xf0\x0f\x82"  # bytes

    # use hex value for bytes
    test = ReturnValueTest(comparator="==", value=HexBytes(value).hex())

    # ensure serialization/deserialization
    schema = ReturnValueTest.ReturnValueTestSchema()
    reloaded = schema.loads(schema.dumps(test))
    assert (test.comparator == reloaded.comparator) and (test.value == reloaded.value)

    # ensure correct bytes/hex comparison
    assert reloaded.eval(value), "bytes compared correctly to hex"
    assert not reloaded.eval(
        b"Here every creed and race find an equal place"
    )  # TT national anthem


def test_return_value_test_bytes_in_list_of_values():
    # test as part of a list
    value = [1, True, "test", 1.23, b"some bytes"]

    json_serializable_condition_value = [
        value[0],
        value[1],
        value[2],
        value[3],
        HexBytes(value[4]).hex(),
    ]
    test = ReturnValueTest(comparator="==", value=json_serializable_condition_value)

    # ensure serialization/deserialization
    schema = ReturnValueTest.ReturnValueTestSchema()
    reloaded = schema.loads(schema.dumps(test))
    assert (test.comparator == reloaded.comparator) and (test.value == reloaded.value)
    # ensure correct bytes/hex comparison
    assert reloaded.eval(value), "bytes compared correctly to hex"
    assert not reloaded.eval([1, 2, 3])


def test_return_value_test_tuples():
    value = (1, True, "test", 1.23, b"some bytes")

    # only list can be provided from json for condition (tuples are serialized to lists)
    value_as_list = [value[0], value[1], value[2], value[3], HexBytes(value[4]).hex()]

    # use hex value for bytes
    test = ReturnValueTest(comparator="==", value=value_as_list)

    # ensure serialization/deserialization
    schema = ReturnValueTest.ReturnValueTestSchema()
    reloaded = schema.loads(schema.dumps(test))
    assert (test.comparator == reloaded.comparator) and (test.value == reloaded.value)

    # ensure correct tuple/list comparison
    assert reloaded.eval(value)
    assert not reloaded.eval([1, 2, 3])  # TT national anthem


@pytest.mark.parametrize(
    "test_scenario",
    [
        ("'foo'", "foo"),  # string
        (
            "0xaDD9D957170dF6F33982001E4c22eCCdd5539118",
            int("0xaDD9D957170dF6F33982001E4c22eCCdd5539118", 16),
        ),  # hex string that is evaluated as int
        (125, None),  # int
        (1.223, None),  # float
        # (Decimal('10.5'), None),  # decimal
        (True, None),  # bool
        (False, None),  # bool as string
        ({"name": "John", "age": 22}, None),  # dict
        ([1, 1.23, True, "foo"], None),  # list of different types
    ],
)
def test_return_value_sanitize(test_scenario):
    value, expected_sanitized_value = test_scenario
    sanitized_value = ReturnValueTest._sanitize_value(value)
    if expected_sanitized_value:
        assert sanitized_value == expected_sanitized_value
    else:
        assert sanitized_value == value  # same value

    # sanity check comparison
    test = ReturnValueTest(comparator="==", value=value)
    # ensure serialization/deserialization
    schema = ReturnValueTest.ReturnValueTestSchema()
    reloaded = schema.loads(schema.dumps(test))
    assert reloaded.eval(value)


@pytest.mark.parametrize(
    "test_value",
    [
        '"foo"',  # string
        ":userAddress",  # context variable is an exception case for a string value
        "0xaDD9D957170dF6F33982001E4c22eCCdd5539118",  # string that is evaluated as int
        125,  # int
        -123456789,  # negative int
        1.223,  # float
        True,  # bool
        [1, 1.2314, False, "love"],  # list of different types
        ["a", "b", "c"],  # list
        [True, False],  # list of bools
        {"name": "John", "age": 22},  # dict
        namedtuple("MyStruct", ["field1", "field2"])(1, "a"),
    ],
)
def test_return_value_json_serialization(test_value):
    schema = ReturnValueTest.ReturnValueTestSchema()
    comparator = random.choice(ReturnValueTest.COMPARATORS)
    test = ReturnValueTest(comparator=comparator, value=test_value)
    reloaded = schema.loads(schema.dumps(test))
    assert (test.comparator == reloaded.comparator) and (
        test.value == reloaded.value
    ), f"test for '{comparator} {test_value}'"


def test_return_value_non_json_serializable_adjustments():
    # bytes
    bytes_value = os.urandom(32)
    return_value_test = ReturnValueTest(comparator="==", value=bytes_value)
    assert return_value_test.value == HexBytes(bytes_value).hex()

    # tuple
    tuple_value = (1, True, "love")
    return_value_test = ReturnValueTest(comparator="!=", value=tuple_value)
    assert return_value_test.value == list(tuple_value)

    # set
    set_value = {1, 2, 3, 5}
    return_value_test = ReturnValueTest(comparator="<=", value=set_value)
    assert return_value_test.value == list(set_value)

    # not json serializable - named tuple w/ bytes (no adjustment)
    class NotJSONSerializable(NamedTuple):
        index: int
        data: bytes

    not_json_serializable = NotJSONSerializable(index=1, data=b"1234")
    with pytest.raises(
        ReturnValueTest.InvalidExpression, match="No JSON serializable equivalent"
    ):
        ReturnValueTest(comparator="==", value=not_json_serializable)
