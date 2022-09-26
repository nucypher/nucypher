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

import pytest

from nucypher.policy.conditions.lingo import ReturnValueTest


def test_return_value_test_integer():
    # >
    test = ReturnValueTest(comparator='>', value='0')
    assert test.eval('1')
    assert not test.eval('-1')

    test = ReturnValueTest(comparator='>', value=0)
    assert test.eval(1)
    assert not test.eval(0)
    assert not test.eval(-1)

    # >=
    test = ReturnValueTest(comparator=">=", value=0)
    assert test.eval(2)
    assert test.eval(0)
    assert not test.eval(-2)

    # <
    test = ReturnValueTest(comparator="<", value=0)
    assert not test.eval(3)
    assert not test.eval(0)
    assert test.eval(-3)

    # <=
    test = ReturnValueTest(comparator="<=", value=0)
    assert not test.eval(3)
    assert test.eval(0)
    assert test.eval(-3)

    # ==
    test = ReturnValueTest(comparator="==", value=0)
    assert not test.eval(1)
    assert test.eval(0)
    assert not test.eval(-2)

    # !=
    test = ReturnValueTest(comparator="!=", value=0)
    assert test.eval(1)
    assert not test.eval(0)
    assert test.eval(-2)


def test_return_value_test_string():
    test = ReturnValueTest(comparator='==', value='"foo"')
    assert test.eval('"foo"')
    assert not test.eval('"bar"')

    test = ReturnValueTest(comparator="!=", value='"foo"')
    assert not test.eval('"foo"')
    assert test.eval('"bar"')


def test_return_value_sanitization():
    with pytest.raises(ValueError):
        _test = ReturnValueTest('DROP', 'TABLE')


def test_eval_is_evil():
    file = f"file_{os.urandom(10).hex()}"
    assert not os.path.isfile(file)
    with pytest.raises(ValueError):
        _test = ReturnValueTest(comparator='>', value=f"(lambda: (42, __import__('os').system('touch {file}'))[0])()")
