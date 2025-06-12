import re
from typing import List, Tuple, Union

import eth_abi
from eth_utils import function_signature_to_4byte_selector

FUNCTION_NAME_PATTERN = r"^[a-zA-Z_][a-zA-Z0-9_]*$"


def _extract_arg_types(human_signature: str) -> List[str]:
    # Extract argument types from signature
    start = human_signature.find("(")
    end = human_signature.rfind(")")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("Invalid function signature format")

    if end != len(human_signature) - 1:
        # case where 'fn(...) extra'
        raise ValueError("Invalid additional data in signature")

    sig_args = human_signature[start + 1 : end]
    arg_types = []
    depth = 0
    current = []

    for char in sig_args:
        if char == "," and depth == 0:
            arg_types.append("".join(current).strip())
            current = []
        else:
            # account for nested structures i.e. tuples
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
            current.append(char)
    if current:
        arg_types.append("".join(current).strip())

    return arg_types


def is_valid_human_readable_signature(human_signature: str) -> bool:
    """
    Check if the provided human-readable signature is valid.
    """
    try:
        method_name = human_signature[: human_signature.index("(")].strip()
        if not re.fullmatch(FUNCTION_NAME_PATTERN, method_name):
            return False

        arg_types = _extract_arg_types(human_signature)
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
    types = _extract_arg_types(human_signature)
    return selector + eth_abi.encode(types, args)


def decode_human_readable_call(
    human_signature: str, call_data: bytes, return_method_name: bool = True
) -> Tuple[Union[str, bytes], List]:
    """
    Decode a human-readable function call signature and its arguments from the
    provided call data into method name OR method selector, and arguments
    """
    # Get expected selector
    selector = function_signature_to_4byte_selector(human_signature)
    if call_data[:4] != selector:
        raise ValueError("Call data does not match function selector")

    arg_types = _extract_arg_types(human_signature)

    # Decode the arguments
    args_data = call_data[4:]
    decoded = list(eth_abi.decode(arg_types, args_data))

    if not return_method_name:
        return selector, decoded
    else:
        method_name = human_signature[: human_signature.index("(")].strip()
        return method_name, decoded
