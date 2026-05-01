import re
from typing import Any, List, Tuple, Union

import eth_abi
from eth_utils import function_signature_to_4byte_selector

FUNCTION_NAME_PATTERN = r"^[a-zA-Z_][a-zA-Z0-9_]*$"


def _split_comma_separated_types(type_string: str) -> List[str]:
    """
    Split a comma-separated string of ABI types, respecting nested parentheses.

    Returns a list of individual type strings. Raises ValueError on mismatched
    parentheses.
    """
    fields = []
    depth = 0
    current = []

    for char in type_string:
        if char == "," and depth == 0:
            fields.append("".join(current).strip())
            current = []
        else:
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
            current.append(char)
    if current:
        fields.append("".join(current).strip())

    if depth != 0:
        raise ValueError(f"Mismatched parentheses in type string: {type_string}")

    return fields


def extract_arg_types(human_signature: str) -> List[str]:
    """
    Extra list of arg types from human ABI signature.

    Raises ValueError if human ABI signature is incorrectly formatted.
    """
    start = human_signature.find("(")
    end = human_signature.rfind(")")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("Invalid function signature format")

    if end != len(human_signature) - 1:
        # case where 'fn(...) extra'
        raise ValueError("Invalid additional data in signature")

    sig_args = human_signature[start + 1 : end]
    return _split_comma_separated_types(sig_args)


def is_valid_human_readable_signature(human_signature: str) -> bool:
    """
    Check if the provided human-readable signature is valid.
    """
    try:
        method_name = human_signature[: human_signature.index("(")].strip()
        if not re.fullmatch(FUNCTION_NAME_PATTERN, method_name):
            return False

        arg_types = extract_arg_types(human_signature)
        for arg_type in arg_types:
            if not eth_abi.is_encodable_type(arg_type):
                return False

        return True
    except (ValueError, IndexError):
        return False


def encode_human_readable_call(human_signature: str, args: list) -> bytes:
    """
    Encode a human-readable function call signature and its arguments into
    a call data format suitable for Ethereum transactions.
    """
    selector = function_signature_to_4byte_selector(human_signature)
    types = extract_arg_types(human_signature)
    return selector + eth_abi.encode(types, args)


def parse_tuple_fields(tuple_type: str) -> List[str]:
    """
    Parse a tuple type string into its component field types.

    Examples:
        "(address,uint256,bytes)" -> ["address", "uint256", "bytes"]
        "((address,uint256),bytes)" -> ["(address,uint256)", "bytes"]

    Raises ValueError if the string is not a valid tuple type.
    """
    if not (tuple_type.startswith("(") and tuple_type.endswith(")")):
        raise ValueError(f"Not a tuple type: {tuple_type}")

    inner = tuple_type[1:-1]
    return _split_comma_separated_types(inner)


def resolve_abi_type_with_indices(abi_type: str, sub_indices: List[int]) -> str:
    """
    Navigate through an ABI type using sub_indices and return the final type.

    At each step:
    - If the type ends with "[]", it's an array - strip "[]" and continue
    - If the type is "(...)"-wrapped, it's a tuple - extract the field at the index

    Args:
        abi_type: The starting ABI type string (e.g., "(address,uint256,bytes)[]")
        sub_indices: List of indices to navigate through the type

    Returns:
        The final type after applying all indices

    Raises:
        ValueError: If indices don't match the type structure
    """
    current_type = abi_type

    for i, idx in enumerate(sub_indices):
        if current_type.endswith("[]"):
            # Array type - strip [] to get element type
            # Note: We can't validate array bounds at schema time (runtime only)
            current_type = current_type[:-2]
        elif current_type.startswith("(") and current_type.endswith(")"):
            # Tuple type - extract the field at index
            fields = parse_tuple_fields(current_type)
            if idx >= len(fields):
                raise ValueError(
                    f"Index {idx} at sub_indices position {i} is out of range "
                    f"for tuple with {len(fields)} fields: {current_type}"
                )
            current_type = fields[idx]
        else:
            raise ValueError(
                f"Cannot apply index at sub_indices position {i}: "
                f"type '{current_type}' is not indexable (not an array or tuple)"
            )

    return current_type


def decode_human_readable_call(
    human_signature: str, call_data: bytes, return_method_name: bool = True
) -> Tuple[Union[str, bytes], List[Any]]:
    """
    Decode a human-readable function call signature and its arguments from the
    provided call data into method name OR method selector, and arguments
    """
    # Get expected selector
    selector = function_signature_to_4byte_selector(human_signature)
    if call_data[:4] != selector:
        raise ValueError("Call data does not match function selector")

    arg_types = extract_arg_types(human_signature)

    # Decode the arguments
    args_data = call_data[4:]
    decoded = list(eth_abi.decode(arg_types, args_data))

    if not return_method_name:
        return selector, decoded
    else:
        method_name = human_signature[: human_signature.index("(")].strip()
        return method_name, decoded
