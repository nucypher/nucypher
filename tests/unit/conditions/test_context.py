import copy
import itertools
import re

import pytest

from nucypher.policy.conditions.auth import Auth
from nucypher.policy.conditions.context import (
    USER_ADDRESS_CONTEXT,
    _recover_user_address,
    _resolve_context_variable,
    get_context_value,
    is_context_variable,
    resolve_any_context_variables,
)
from nucypher.policy.conditions.exceptions import (
    ContextVariableVerificationFailed,
    InvalidConditionContext,
    InvalidContextVariableData,
)
from nucypher.policy.conditions.lingo import (
    ReturnValueTest,
)

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
        resolved_parameters, resolved_return_value = resolve_any_context_variables(
            [params], return_value_test, **CONTEXT
        )
        assert resolved_parameters == [resolved_params]
        assert resolved_return_value.comparator == return_value_test.comparator
        assert resolved_return_value.index == return_value_test.index
        assert resolved_return_value.value == resolved_value


@pytest.mark.parametrize("expected_entry", ["address", "signature", "typedData"])
@pytest.mark.parametrize(
    "valid_user_address_context", Auth.AuthScheme.values(), indirect=True
)
def test_user_address_context_missing_required_entries(
    expected_entry, valid_user_address_context
):
    context = copy.deepcopy(valid_user_address_context)
    del context[USER_ADDRESS_CONTEXT][expected_entry]
    with pytest.raises(InvalidContextVariableData):
        get_context_value(USER_ADDRESS_CONTEXT, **context)


@pytest.mark.parametrize(
    "valid_user_address_context", Auth.AuthScheme.values(), indirect=True
)
def test_user_address_context_invalid_typed_data(valid_user_address_context):
    # invalid typed data
    context = copy.deepcopy(valid_user_address_context)
    context[USER_ADDRESS_CONTEXT]["typedData"] = dict(
        randomSaying="Comparison is the thief of joy."  # -– Theodore Roosevelt
    )
    with pytest.raises(InvalidContextVariableData):
        get_context_value(USER_ADDRESS_CONTEXT, **context)


@pytest.mark.parametrize(
    "valid_user_address_context", Auth.AuthScheme.values(), indirect=True
)
def test_user_address_context_variable_verification(
    valid_user_address_context, get_random_checksum_address
):
    # call underlying directive directly (appease codecov)
    address = _recover_user_address(expected_scheme=None, **valid_user_address_context)
    assert address == valid_user_address_context[USER_ADDRESS_CONTEXT]["address"]

    # valid user address context
    address = get_context_value(USER_ADDRESS_CONTEXT, **valid_user_address_context)
    assert address == valid_user_address_context[USER_ADDRESS_CONTEXT]["address"]

    # invalid user address context - signature does not match address
    # internals are mutable - deepcopy
    mismatch_with_address_context = copy.deepcopy(valid_user_address_context)
    mismatch_with_address_context[USER_ADDRESS_CONTEXT][
        "address"
    ] = get_random_checksum_address()
    with pytest.raises(ContextVariableVerificationFailed):
        get_context_value(USER_ADDRESS_CONTEXT, **mismatch_with_address_context)

    # invalid user address context - signature does not match address
    # internals are mutable - deepcopy
    mismatch_with_address_context = copy.deepcopy(valid_user_address_context)
    signature = (
        "0x93252ddff5f90584b27b5eef1915b23a8b01a703be56c8bf0660647c15cb75e9"
        "1983bde9877eaad11da5a3ebc9b64957f1c182536931f9844d0c600f0c41293d1b"
    )
    mismatch_with_address_context[USER_ADDRESS_CONTEXT]["signature"] = signature
    with pytest.raises(ContextVariableVerificationFailed):
        get_context_value(USER_ADDRESS_CONTEXT, **mismatch_with_address_context)

    # invalid signature
    # internals are mutable - deepcopy
    invalid_signature_context = copy.deepcopy(valid_user_address_context)
    invalid_signature_context[USER_ADDRESS_CONTEXT][
        "signature"
    ] = "0xdeadbeef"  # invalid signature
    with pytest.raises(InvalidConditionContext):
        get_context_value(USER_ADDRESS_CONTEXT, **invalid_signature_context)
