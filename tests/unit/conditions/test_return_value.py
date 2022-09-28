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

import os
import random

import pytest

from nucypher.policy.conditions.lingo import ReturnValueTest


def test_return_value_test_invalid_comparators():
    with pytest.raises(ReturnValueTest.InvalidExpression):
        _ = ReturnValueTest(comparator="eq", value=1)

    with pytest.raises(ReturnValueTest.InvalidExpression):
        _ = ReturnValueTest(comparator="=", value=1)

    with pytest.raises(ReturnValueTest.InvalidExpression):
        _ = ReturnValueTest(comparator="+", value=1)

    with pytest.raises(ReturnValueTest.InvalidExpression):
        _ = ReturnValueTest(comparator="*", value=1)

    with pytest.raises(ReturnValueTest.InvalidExpression):
        _ = ReturnValueTest(comparator="/", value=1)

    with pytest.raises(ReturnValueTest.InvalidExpression):
        _test = ReturnValueTest(comparator="DROP", value=1)


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


def test_return_value_test_none():
    test = ReturnValueTest(comparator="!=", value=None)
    assert test.eval("0xaDD9D957170dF6F33982001E4c22eCCdd5539118")

    test = ReturnValueTest(comparator="==", value=None)
    assert not test.eval("0xaDD9D957170dF6F33982001E4c22eCCdd5539118")

    test = ReturnValueTest(comparator="==", value=None)
    assert test.eval("None")
    assert not test.eval('"None"')


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


@pytest.mark.parametrize(
    "test_value",
    [
        '"foo"',  # string
        ":userAddress",  # context variable is an exception case for a string value
        "0xaDD9D957170dF6F33982001E4c22eCCdd5539118",  # string that is evaluated as int
        125,  # int
        1.223,  # float
        os.urandom(16),  # bytes
        True,  # bool
        "True",  # bool as string
        None,  # None
        "None",  # None as string
        (1, True, "love"),  # tuple
        ["a", "b", "c"],  # list
        {"name": "John", "age": 22},  # dict
        {True, False},  # set
    ],
)
def test_return_value_serialization(test_value):
    schema = ReturnValueTest.ReturnValueTestSchema()
    comparator = random.choice(ReturnValueTest.COMPARATORS)
    test = ReturnValueTest(comparator=comparator, value=test_value)
    reloaded = schema.load(schema.dump(test))
    assert test == reloaded, f"test for '{comparator} {test_value}'"
