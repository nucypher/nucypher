import os
import pytest

from nucypher.policy.conditions.lingo import ReturnValueTest


def test_return_value_test_integer():
    test = ReturnValueTest(comparator='>', value='0')
    assert test.eval('1')
    assert not test.eval('-1')

    test = ReturnValueTest(comparator='>', value=0)
    assert test.eval(1)
    assert not test.eval(-1)


def test_return_value_test_string():
    test = ReturnValueTest(comparator='==', value='"foo"')
    assert test.eval('"foo"')
    assert not test.eval('"bar"')


def test_return_value_sanitization():
    with pytest.raises(ValueError):
        _test = ReturnValueTest('DROP', 'TABLE')


def test_eval_is_evil():
    file = f"file_{os.urandom(10).hex()}"
    assert not os.path.isfile(file)
    with pytest.raises(ValueError):
        _test = ReturnValueTest(comparator='>', value=f"(lambda: (42, __import__('os').system('touch {file}'))[0])()")
