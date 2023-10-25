from typing import (
    Any,
    Dict,
    List,
    Optional,
    Sequence,
    cast,
)

from hexbytes import HexBytes
from web3.auto import w3
from web3.types import ABIFunction

from nucypher.policy.conditions.context import is_context_variable
from nucypher.policy.conditions.exceptions import (
    InvalidCondition,
)
from nucypher.policy.conditions.lingo import ReturnValueTest


def _align_comparator_value(
    comparator_value: Any, expected_type: str, failure_message: str
) -> Any:
    if expected_type.startswith("bytes"):
        try:
            comparator_value = bytes(HexBytes(comparator_value))
        except Exception:
            raise InvalidCondition(failure_message)
    return comparator_value


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
    if abi["type"] == "fallback":
        return []
    else:
        return [_collapse_if_tuple(cast(Dict[str, Any], arg)) for arg in abi["outputs"]]


def _validate_value_type(
    expected_type: str, comparator_value: Any, failure_message: str
) -> None:
    if is_context_variable(comparator_value):
        # can't know type for context variable
        return

    comparator_value = _align_comparator_value(
        comparator_value, expected_type, failure_message
    )
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
            f"Invalid type provided '{tuple_type}; not a tuple type definition"
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

    if not isinstance(comparator_value, Sequence):
        raise InvalidCondition(failure_message)

    if len(output_abi_types) != len(comparator_value):
        raise InvalidCondition(failure_message)

    for output_abi_type, component_value in zip(output_abi_types, comparator_value):
        _validate_value_type(output_abi_type, component_value, failure_message)


def _align_comparator_value_with_abi(
    abi, return_value_test: ReturnValueTest
) -> ReturnValueTest:
    output_abi_types = _get_abi_types(abi)
    comparator = return_value_test.comparator
    comparator_value = return_value_test.value
    comparator_index = return_value_test.index
    if isinstance(comparator_value, tuple):
        # must be list
        comparator_value = list(comparator_value)

    if len(output_abi_types) == 1:
        expected_type = output_abi_types[0]
        if comparator_index is not None and _is_tuple_type(expected_type):
            type_entries = _get_tuple_type_entries(expected_type)
            expected_type = type_entries[comparator_index]
        comparator_value = _align_comparator_value(
            comparator_value, expected_type, failure_message="Unencodable type"
        )
        return ReturnValueTest(
            comparator=comparator,
            value=comparator_value,
            index=comparator_index,
        )
    elif len(output_abi_types) > 1:
        if comparator_index is not None:
            # only index entry we care about
            expected_type = output_abi_types[comparator_index]
            comparator_value = _align_comparator_value(
                comparator_value,
                expected_type,
                failure_message="Unencodable type",
            )
            return ReturnValueTest(
                comparator=comparator,
                value=comparator_value,
                index=comparator_index,
            )

        values = list()
        for output_abi_type, component_value in zip(output_abi_types, comparator_value):
            comparator_value = _align_comparator_value(
                comparator_value,
                output_abi_type,
                failure_message="Unencodable type",
            )
            values.append(component_value)
        return ReturnValueTest(
            comparator=comparator, value=values, index=comparator_index
        )
    else:
        raise RuntimeError("No outputs for ABI function.")  # should never happen
