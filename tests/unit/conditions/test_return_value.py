import pytest

from nucypher.policy.conditions import ReturnValueTest


def test_return_result_test_simple():
    test = ReturnValueTest(comparator='>', value=0)
    assert test.eval(1)
    assert not test.eval(-1)


def test_return_value_sanitization():
    with pytest.raises(ValueError):
        _test = ReturnValueTest('DROP', 'TABLE')

