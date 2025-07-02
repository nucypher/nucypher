from typing import Any


def adjust_for_attribute_value_for_eval(attribute_value: Any) -> Any:
    """
    Adjusts the attribute value for evaluation checking.
    If the value is a string and does not start with '0x', it will be double-quoted.
    """
    if isinstance(attribute_value, str):
        if not attribute_value.startswith("0x"):
            # value needs to be double-quoted
            return f'"{attribute_value}"'

    return attribute_value
