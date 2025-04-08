from typing import (
    Any,
    Dict,
    List,
    Optional,
    Sequence,
    cast,
)

from eth_typing import ChecksumAddress
from web3 import Web3
from web3.auto import w3
from web3.contract.contract import ContractFunction
from web3.types import ABIFunction

from nucypher.policy.conditions import STANDARD_ABI_CONTRACT_TYPES, STANDARD_ABIS
from nucypher.policy.conditions.context import is_context_variable
from nucypher.policy.conditions.lingo import ReturnValueTest

#
# Schema logic
#

def _get_abi_types(abi: ABIFunction) -> List[str]:
    return [_collapse_if_tuple(cast(Dict[str, Any], arg)) for arg in abi["outputs"]]


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


def _validate_value_type(
    expected_type: str, comparator_value: Any, failure_message: str
) -> None:
    if is_context_variable(comparator_value):
        # context variable types cannot be known until execution time.
        return
    if not w3.is_encodable(expected_type, comparator_value):
        raise ValueError(failure_message)


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
        raise ValueError(failure_message)

    if len(output_abi_types) != len(comparator_value):
        raise ValueError(failure_message)

    for output_abi_type, component_value in zip(output_abi_types, comparator_value):
        _validate_value_type(output_abi_type, component_value, failure_message)


def _resolve_abi(
    w3: Web3,
    method: str,
    standard_contract_type: Optional[str] = None,
    function_abi: Optional[ABIFunction] = None,
) -> ABIFunction:
    """Resolves the contract an/or function ABI from a standard contract name"""

    if not (function_abi or standard_contract_type):
        raise ValueError(
            f"Ambiguous ABI - Supply either an ABI or a standard contract type ({STANDARD_ABI_CONTRACT_TYPES})."
        )

    if standard_contract_type:
        try:
            # Lookup the standard ABI given it's ERC standard name (standard contract type)
            contract_abi = STANDARD_ABIS[standard_contract_type]
        except KeyError:
            raise ValueError(
                f"Invalid standard contract type {standard_contract_type}; Must be one of {STANDARD_ABI_CONTRACT_TYPES}"
            )

        # Extract all function ABIs from the contract's ABI.
        # Will raise a ValueError if there is not exactly one match.
        function_abi = (
            w3.eth.contract(abi=contract_abi).get_function_by_name(method).abi
        )

    return ABIFunction(function_abi)


def _align_comparator_value_single_output(
    expected_type: str, comparator_value: Any, comparator_index: Optional[int]
) -> Any:
    if comparator_index is not None and _is_tuple_type(expected_type):
        type_entries = _get_tuple_type_entries(expected_type)
        expected_type = type_entries[comparator_index]

    if not w3.is_encodable(expected_type, comparator_value):
        raise ValueError(
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
            raise ValueError(
                f"Mismatched comparator type ({comparator_value} as {expected_type})"
            )

        return comparator_value

    values = list()
    for output_abi_type, component_value in zip(output_abi_types, comparator_value):
        # ensure alignment
        if not w3.is_encodable(output_abi_type, component_value):
            raise ValueError(
                f"Mismatched comparator type ({component_value} as {output_abi_type})"
            )
        values.append(component_value)
    return values


#
# Public functions.
#


def align_comparator_value_with_abi(
    abi: ABIFunction, return_value_test: ReturnValueTest
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


def validate_function_abi(
    function_abi: Dict, method_name: Optional[str] = None
) -> None:
    """
    Validates a dictionary as valid for use as a condition function ABI.

    Optionally validates the method_name
    """
    abi = ABIFunction(function_abi)

    if not abi.get("name"):
        raise ValueError(f"Invalid ABI, no function name found {abi}")
    if method_name and abi.get("name") != method_name:
        raise ValueError(f"Mismatched ABI for contract function {method_name} - {abi}")
    if abi.get("type") != "function":
        raise ValueError(f"Invalid ABI type {abi}")
    if not abi.get("outputs"):
        raise ValueError(f"Invalid ABI, no outputs found {abi}")
    if abi.get("stateMutability") not in ["pure", "view"]:
        raise ValueError(f"Invalid ABI stateMutability {abi}")


def get_unbound_contract_function(
    contract_address: ChecksumAddress,
    method: str,
    standard_contract_type: Optional[str] = None,
    function_abi: Optional[ABIFunction] = None,
) -> ContractFunction:
    """Gets an unbound contract function to evaluate"""
    w3 = Web3()
    function_abi = _resolve_abi(
        w3=w3,
        standard_contract_type=standard_contract_type,
        method=method,
        function_abi=function_abi,
    )
    try:
        contract = w3.eth.contract(address=contract_address, abi=[function_abi])
        contract_function = getattr(contract.functions, method)
        return contract_function
    except Exception as e:
        raise ValueError(
            f"Unable to find contract function, '{method}', for condition: {e}"
        ) from e


def validate_contract_function_expected_return_type(
    contract_function: ContractFunction, return_value_test: ReturnValueTest
) -> None:
    output_abi_types = _get_abi_types(contract_function.contract_abi[0])
    comparator_value = return_value_test.value
    comparator_index = return_value_test.index
    index_string = f"@index={comparator_index}" if comparator_index is not None else ""
    failure_message = (
        f"Invalid return value comparison type '{type(comparator_value)}' for "
        f"'{contract_function.fn_name}'{index_string} based on ABI types {output_abi_types}"
    )

    if len(output_abi_types) == 1:
        _validate_single_output_type(
            output_abi_types[0], comparator_value, comparator_index, failure_message
        )
    else:
        _validate_multiple_output_types(
            output_abi_types, comparator_value, comparator_index, failure_message
        )
