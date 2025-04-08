from typing import Any


def process_result_for_condition_eval(result: Any):
    # strings that are not already quoted will cause a problem for literal_eval
    if not isinstance(result, str):
        return result

    # check if already quoted; if not, quote it
    if not (
        (result.startswith("'") and result.endswith("'"))
        or (result.startswith('"') and result.endswith('"'))
    ):
        quote_type_to_use = '"' if "'" in result else "'"
        result = f"{quote_type_to_use}{result}{quote_type_to_use}"

    return result
