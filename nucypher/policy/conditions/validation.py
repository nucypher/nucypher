from typing import (
    Any,
    Dict,
    List,
    Optional,
    Sequence,
    cast,
)

from web3.auto import w3
from web3.types import ABIFunction

from nucypher.policy.conditions.context import is_context_variable
from nucypher.policy.conditions.exceptions import (
    InvalidCondition,
)
from nucypher.policy.conditions.lingo import ReturnValueTest


def _validate_single_output_type(
    expected_type: str,
    comparator_value: Any,
    comparator_index: Optional[int],
    failure_message: str,
) -> None:
    if comparator_index is not None and _is_tuple_type(expected_type):
        type_entries = _get_tuple_type_entries(expected_type)
        expected_type = type_entries[comparator_index]
    _validate_value_type(expected_type, comparator_value, failure_message)


def _get_abi_types(abi: ABIFunction) -> List[str]:
    return [_collapse_if_tuple(cast(Dict[str, Any], arg)) for arg in abi["outputs"]]


def _validate_value_type(
    expected_type: str, comparator_value: Any, failure_message: str
) -> None:
    if is_context_variable(comparator_value):
        # context variable types cannot be known until execution time.
        return
    if not w3.is_encodable(expected_type, comparator_value):
        raise InvalidCondition(failure_message)


def _collapse_if_tuple(abi: Dict[str, Any]) -> str:
    abi_type = abi["type"]
    if not abi_type.startswith("tuple"):
        return abi_type
    delimited = ",".join(_collapse_if_tuple(c) for c in abi["components"])
    collapsed = f"({delimited})"
    return collapsed


def _is_tuple_type(abi_type: str):
    return abi_type.startswith("(") and abi_type.endswith(")")


def _get_tuple_type_entries(tuple_type: str) -> List[str]:
    if not _is_tuple_type(tuple_type):
        raise ValueError(
            f"Invalid type provided '{tuple_type}'; not a tuple type definition"
        )
    result = tuple_type.replace("(", "").replace(")", "")
    result = result.split(",")
    return result


def _validate_multiple_output_types(
    output_abi_types: List[str],
    comparator_value: Any,
    comparator_index: Optional[int],
    failure_message: str,
) -> None:
    if comparator_index is not None:
        expected_type = output_abi_types[comparator_index]
        _validate_value_type(expected_type, comparator_value, failure_message)
        return

    if is_context_variable(comparator_value):
        # context variable types cannot be known until execution time.
        return

    if not isinstance(comparator_value, Sequence):
        raise InvalidCondition(failure_message)

    if len(output_abi_types) != len(comparator_value):
        raise InvalidCondition(failure_message)

    for output_abi_type, component_value in zip(output_abi_types, comparator_value):
        _validate_value_type(output_abi_type, component_value, failure_message)


def _align_comparator_value_single_output(
    expected_type: str, comparator_value: Any, comparator_index: Optional[int]
) -> Any:
    if comparator_index is not None and _is_tuple_type(expected_type):
        type_entries = _get_tuple_type_entries(expected_type)
        expected_type = type_entries[comparator_index]

    if not w3.is_encodable(expected_type, comparator_value):
        raise InvalidCondition(
            f"Mismatched comparator type ({comparator_value} as {expected_type})"
        )
    return comparator_value


def _align_comparator_value_multiple_output(
    output_abi_types: List[str], comparator_value: Any, comparator_index: Optional[int]
) -> Any:
    if comparator_index is not None:
        expected_type = output_abi_types[comparator_index]
        # ensure alignment
        if not w3.is_encodable(expected_type, comparator_value):
            raise InvalidCondition(
                f"Mismatched comparator type ({comparator_value} as {expected_type})"
            )

        return comparator_value

    values = list()
    for output_abi_type, component_value in zip(output_abi_types, comparator_value):
        # ensure alignment
        if not w3.is_encodable(output_abi_type, component_value):
            raise InvalidCondition(
                f"Mismatched comparator type ({component_value} as {output_abi_type})"
            )
        values.append(component_value)
    return values


def _align_comparator_value_with_abi(
    abi, return_value_test: ReturnValueTest
) -> ReturnValueTest:
    output_abi_types = _get_abi_types(abi)
    comparator = return_value_test.comparator
    comparator_value = return_value_test.value
    comparator_index = return_value_test.index

    if len(output_abi_types) == 1:
        comparator_value = _align_comparator_value_single_output(
            output_abi_types[0], comparator_value, comparator_index
        )
        return ReturnValueTest(
            comparator=comparator,
            value=comparator_value,
            index=comparator_index,
        )
    else:
        comparator_value = _align_comparator_value_multiple_output(
            output_abi_types, comparator_value, comparator_index
        )
        return ReturnValueTest(
            comparator=comparator, value=comparator_value, index=comparator_index
        )


def _validate_condition_function_abi(function_abi: Dict, method_name: str) -> None:
    """validates a dictionary as valid for use as a condition function ABI"""
    abi = ABIFunction(function_abi)

    if not abi.get("name"):
        raise ValueError(f"Invalid ABI, no function name found {abi}")
    if abi.get("name") != method_name:
        raise ValueError(f"Mismatched ABI for contract function {method_name} - {abi}")
    if abi.get("type") != "function":
        raise ValueError(f"Invalid ABI type {abi}")
    if not abi.get("outputs"):
        raise ValueError(f"Invalid ABI, no outputs found {abi}")
    if abi.get("stateMutability") not in ["pure", "view"]:
        raise ValueError(f"Invalid ABI stateMutability {abi}")


def _validate_condition_abi(
    standard_contract_type: str,
    function_abi: Dict,
    method_name: str,
) -> None:
    if not (bool(standard_contract_type) ^ bool(function_abi)):
        raise ValueError(
            f"Provide 'standardContractType' or 'functionAbi'; got ({standard_contract_type}, {function_abi})."
        )
    if function_abi:
        _validate_condition_function_abi(function_abi, method_name=method_name)
