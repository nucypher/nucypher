import itertools

import pytest

from nucypher.policy.conditions.context import resolve_any_context_variables
from nucypher.policy.conditions.lingo import ReturnValueTest

INVALID_CONTEXT_PARAM_NAMES = [
    ":",
    ":)",
    ":!",
    ":::::this//is       🍌 🍌 🍌 ",
    ":123 \"$%'+-?\n  jarl!! cobarde!!",
]


@pytest.mark.parametrize(
    "var1,var2", itertools.product(INVALID_CONTEXT_PARAM_NAMES, repeat=2)
)
def test_invalid_context_parameter(var1, var2):
    context = {var1: 42, var2: 42}
    # Check that parameters make sense, what about repeated variables?
    parameters = [var1, 1, 2]

    # with pytest.raises(ValueError):
    return_value_test = ReturnValueTest(comparator="==", value=var2)
    _ = resolve_any_context_variables(parameters, return_value_test, **context)
