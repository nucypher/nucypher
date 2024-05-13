import itertools
import re

import pytest

from nucypher.policy.conditions.context import (
    _resolve_context_variable,
    is_context_variable,
    resolve_parameter_context_variables,
)
from nucypher.policy.conditions.lingo import ReturnValueTest

INVALID_CONTEXT_PARAM_NAMES = [
    ":",
    ":)",
    ":!",
    ":3",
    ":superñoño",
    ":::::this//is       🍌 🍌 🍌 ",
    ":123 \"$%'+-?\n  jarl!! cobarde!!",
]

VALID_CONTEXT_PARAM_NAMES = [
    ":foo",
    ":_bar",
    ":bar_",
    ":_bar_",
    ":VAR",
    ":a1234",
    ":snake_case",
    ":camelCase",
    ":_",  # TODO: not sure if we should allow this one, tbh
]

DEFINITELY_NOT_CONTEXT_PARAM_NAMES = ["1234", "foo", "", 123]

CONTEXT = {":foo": 1234, ":bar": "'BAR'"}

VALUES_WITH_RESOLUTION = [
    (42, 42),
    (True, True),
    ("'bar'", "'bar'"),
    ([42, True, "'bar'"], [42, True, "'bar'"]),
    (":foo", 1234),
    ([":foo", True, "'bar'"], [1234, True, "'bar'"]),
    ([":foo", ":foo", 5, [99, [":bar"]]], [1234, 1234, 5, [99, ["'BAR'"]]]),
]


def test_is_context_variable():
    for variable in VALID_CONTEXT_PARAM_NAMES:
        assert is_context_variable(variable)

    for variable in DEFINITELY_NOT_CONTEXT_PARAM_NAMES:
        assert not is_context_variable(variable)

    for variable in INVALID_CONTEXT_PARAM_NAMES:
        expected_message = re.escape(
            f"Context variable name '{variable}' is not valid."
        )
        with pytest.raises(ValueError, match=expected_message):
            _ = is_context_variable(variable)


def test_resolve_context_variable():
    for value, resolution in VALUES_WITH_RESOLUTION:
        assert resolution == _resolve_context_variable(value, **CONTEXT)


def test_resolve_any_context_variables():
    for params_with_resolution, value_with_resolution in itertools.product(
        VALUES_WITH_RESOLUTION, repeat=2
    ):
        params, resolved_params = params_with_resolution
        value, resolved_value = value_with_resolution
        return_value_test = ReturnValueTest(comparator="==", value=value)
        resolved_parameters = resolve_parameter_context_variables([params], **CONTEXT)
        resolved_return_value = return_value_test.with_resolved_context(**CONTEXT)
        assert resolved_parameters == [resolved_params]
        assert resolved_return_value.comparator == return_value_test.comparator
        assert resolved_return_value.index == return_value_test.index
        assert resolved_return_value.value == resolved_value
