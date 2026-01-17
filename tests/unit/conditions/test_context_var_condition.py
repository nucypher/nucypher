import pytest
from eth_utils import to_checksum_address

from nucypher.policy.conditions.context import USER_ADDRESS_CONTEXT
from nucypher.policy.conditions.exceptions import (
    InvalidCondition,
    InvalidConditionLingo,
    RequiredContextVariable,
)
from nucypher.policy.conditions.lingo import ConditionType, ReturnValueTest
from nucypher.policy.conditions.var import ContextVariableCondition


def test_invalid_context_variable_condition():
    # invalid condition type
    with pytest.raises(InvalidCondition, match=ConditionType.CONTEXT_VARIABLE.value):
        _ = ContextVariableCondition(
            condition_type=ConditionType.TIME.value,
            context_variable=":myContextVar",
            return_value_test=ReturnValueTest(comparator="==", value=0),
        )

    # not context var
    with pytest.raises(InvalidCondition, match="Invalid value for context variable"):
        _ = ContextVariableCondition(
            context_variable="noColon",
            return_value_test=ReturnValueTest(comparator="==", value=0),
        )

    # no context var
    with pytest.raises(InvalidCondition, match="Field may not be null"):
        _ = ContextVariableCondition(
            context_variable=None,
            return_value_test=ReturnValueTest(comparator="==", value=0),
        )

    # no return value test via from_dict (standalone) - should fail
    with pytest.raises(InvalidConditionLingo, match="returnValueTest"):
        _ = ContextVariableCondition.from_dict(
            {
                "conditionType": "context-variable",
                "contextVariable": USER_ADDRESS_CONTEXT,
                # no returnValueTest - should fail for standalone
            }
        )

    # no return value test via direct construction - now allowed
    # (returns True, value when verified)
    condition = ContextVariableCondition(
        context_variable=USER_ADDRESS_CONTEXT, return_value_test=None
    )
    assert condition.return_value_test is None


def test_context_variable_condition_initialization():
    context_variable = ":contextVar"

    condition = ContextVariableCondition(
        context_variable=context_variable,
        return_value_test=ReturnValueTest("==", 19),
    )

    assert condition.context_variable == context_variable
    assert condition.return_value_test.comparator == "=="
    assert condition.return_value_test.value == 19
    assert condition.return_value_test.eval(19)


def test_context_variable_condition_schema_validation():
    condition = ContextVariableCondition(
        context_variable=":contextVar",
        return_value_test=ReturnValueTest("==", 20),
    )
    condition_dict = condition.to_dict()

    # no issues here
    ContextVariableCondition.from_dict(condition_dict)

    # no issues with optional name
    condition_dict["name"] = "my_context_var_condition"
    ContextVariableCondition.from_dict(condition_dict)

    with pytest.raises(InvalidConditionLingo):
        # no context var defined
        condition_dict = condition.to_dict()
        del condition_dict["contextVariable"]
        ContextVariableCondition.from_dict(condition_dict)

    with pytest.raises(InvalidConditionLingo):
        # no return value test defined
        condition_dict = condition.to_dict()
        del condition_dict["returnValueTest"]
        ContextVariableCondition.from_dict(condition_dict)


def test_context_variable_condition_repr():
    condition = ContextVariableCondition(
        context_variable=":contextVar",
        return_value_test=ReturnValueTest("==", 19),
    )
    condition_str = str(condition)
    assert condition.__class__.__name__ in condition_str
    assert "contextVariable=:contextVar" in condition_str


def test_context_variable_condition_verify(condition_provider_manager):
    condition = ContextVariableCondition(
        context_variable=":contextVar",
        return_value_test=ReturnValueTest("==", 19),
    )
    value = 19
    context = {":contextVar": value}
    success, result = condition.verify(providers=condition_provider_manager, **context)
    assert success is True
    assert result == value

    value = "'When the debate is lost, slander becomes the tool of the loser'"
    context = {":contextVar": value}
    success, result = condition.verify(providers=condition_provider_manager, **context)
    assert success is False
    assert result == value


def test_context_variable_condition_verify_list(condition_provider_manager):
    expected = [1, True, "test"]
    condition = ContextVariableCondition(
        context_variable=":contextVar",
        return_value_test=ReturnValueTest("==", expected),
    )
    context = {":contextVar": expected}
    success, result = condition.verify(providers=condition_provider_manager, **context)
    assert success is True
    assert result == expected

    value = [1, "here comes the 2 to the 3 to the 4"]
    context = {":contextVar": value}
    success, result = condition.verify(providers=condition_provider_manager, **context)
    assert success is False
    assert result == value

    # Test verification with missing context
    with pytest.raises(RequiredContextVariable):
        condition.verify(providers=condition_provider_manager)


def test_context_variable_user_address_allowlist(
    condition_provider_manager,
    valid_eip4361_auth_message_factory,
    get_random_checksum_address,
):
    allowed_auth_message = valid_eip4361_auth_message_factory()
    condition = ContextVariableCondition(
        context_variable=USER_ADDRESS_CONTEXT,
        return_value_test=ReturnValueTest(
            "in", [allowed_auth_message["address"], get_random_checksum_address()]
        ),
    )
    context = {USER_ADDRESS_CONTEXT: allowed_auth_message}
    success, result = condition.verify(providers=condition_provider_manager, **context)
    assert success is True
    assert result == allowed_auth_message["address"]

    disallowed_auth_message = valid_eip4361_auth_message_factory()
    context = {USER_ADDRESS_CONTEXT: disallowed_auth_message}
    success, result = condition.verify(providers=condition_provider_manager, **context)
    assert success is False
    assert result == disallowed_auth_message["address"]

    # Test verification with missing context
    with pytest.raises(RequiredContextVariable):
        condition.verify(providers=condition_provider_manager)


def test_context_variable_user_address_allowlist_case_insensitive(
    condition_provider_manager, valid_eip4361_auth_message_factory
):
    """Test the verification of AddressAllowlistCondition."""
    # Create test accounts

    auth_message1 = valid_eip4361_auth_message_factory()
    allowed_account1 = auth_message1["address"]

    auth_message2 = valid_eip4361_auth_message_factory()
    allowed_account2 = auth_message2["address"]

    auth_message_not_allowed = valid_eip4361_auth_message_factory()

    # ensure that verify is case-insensitive since EVM addresses are case-insensitive
    allowed_addresses = [allowed_account1, allowed_account2]
    checksummed_addresses = [
        to_checksum_address(address) for address in allowed_addresses
    ]
    lowercase_addresses = [address.lower() for address in allowed_addresses]
    uppercase_addresses = [address.upper() for address in allowed_addresses]

    for addresses in [checksummed_addresses, lowercase_addresses, uppercase_addresses]:
        # Create condition with allowed accounts
        condition = ContextVariableCondition(
            context_variable=USER_ADDRESS_CONTEXT,
            return_value_test=ReturnValueTest("in", addresses),
        )

        # Test successful verification with allowed account
        context = {USER_ADDRESS_CONTEXT: auth_message1}
        result, _ = condition.verify(providers=condition_provider_manager, **context)
        assert result is True

        # Test verification with disallowed account
        context = {USER_ADDRESS_CONTEXT: auth_message_not_allowed}
        result, _ = condition.verify(providers=condition_provider_manager, **context)
        assert result is False

        # Test with another allowed account
        context = {USER_ADDRESS_CONTEXT: auth_message2}
        result, _ = condition.verify(providers=condition_provider_manager, **context)
        assert result is True
