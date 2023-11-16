import re
from typing import Any, List, Union

from eth_account.account import Account
from eth_account.messages import HexBytes, encode_structured_data
from eth_typing import ChecksumAddress
from eth_utils import to_checksum_address

from nucypher.policy.conditions.exceptions import (
    ContextVariableVerificationFailed,
    InvalidContextVariableData,
    RequiredContextVariable,
)

USER_ADDRESS_CONTEXT = ":userAddress"

CONTEXT_PREFIX = ":"
CONTEXT_REGEX = re.compile(":[a-zA-Z_][a-zA-Z0-9_]*")


def _recover_user_address(**context) -> ChecksumAddress:
    """
    Recovers a checksum address from a signed EIP712 message.

    Expected format:
    {
        ":userAddress":
            {
                "signature": "<signature>",
                "address": "<address>",
                "typedData": "<a complicated EIP712 data structure>"
            }
    }
    """

    # setup
    try:
        user_address_info = context[USER_ADDRESS_CONTEXT]
        signature = user_address_info["signature"]
        user_address = to_checksum_address(user_address_info["address"])
        eip712_message = user_address_info["typedData"]

        # convert hex data for byte fields - bytes are expected by underlying library
        # 1. salt
        salt = eip712_message["domain"]["salt"]
        eip712_message["domain"]["salt"] = HexBytes(salt)
        # 2. blockHash
        blockHash = eip712_message["message"]["blockHash"]
        eip712_message["message"]["blockHash"] = HexBytes(blockHash)

        signable_message = encode_structured_data(primitive=eip712_message)
    except Exception as e:
        # data could not be processed
        raise InvalidContextVariableData(
            f'Invalid data provided for "{USER_ADDRESS_CONTEXT}"; {e.__class__.__name__} - {e}'
        )

    # actual verification
    try:
        address_for_signature = Account.recover_message(
            signable_message=signable_message, signature=signature
        )
        if address_for_signature == user_address:
            return user_address
    except Exception as e:
        # exception during verification
        raise ContextVariableVerificationFailed(
            f"Could not determine address of signature for '{USER_ADDRESS_CONTEXT}'; {e.__class__.__name__} - {e}"
        )

    # verification failed - addresses don't match
    raise ContextVariableVerificationFailed(
        f"Signer address for '{USER_ADDRESS_CONTEXT}' signature does not match; expected {user_address}"
    )


_DIRECTIVES = {
    USER_ADDRESS_CONTEXT: _recover_user_address,
}


def is_context_variable(variable) -> bool:
    if isinstance(variable, str) and variable.startswith(CONTEXT_PREFIX):
        if CONTEXT_REGEX.fullmatch(variable):
            return True
        else:
            raise ValueError(f"Context variable name '{variable}' is not valid.")
    return False


def get_context_value(context_variable: str, **context) -> Any:
    try:
        # DIRECTIVES are special context vars that will pre-processed by ursula
        func = _DIRECTIVES[context_variable]
    except KeyError:
        # fallback for context variable without directive - assume key,value pair
        # handles the case for user customized context variables
        value = context.get(context_variable)
        if value is None:
            raise RequiredContextVariable(
                f'No value provided for unrecognized context variable "{context_variable}"'
            )
    else:
        value = func(**context)  # required inputs here

    return value


def _resolve_context_variable(param: Union[Any, List[Any]], **context):
    if isinstance(param, list):
        return [_resolve_context_variable(item, **context) for item in param]
    elif is_context_variable(param):
        return get_context_value(context_variable=param, **context)
    else:
        return param


def resolve_any_context_variables(parameters: List[Any], return_value_test, **context):
    processed_parameters = [
        _resolve_context_variable(param, **context) for param in parameters
    ]
    processed_return_value_test = return_value_test.with_resolved_context(**context)
    return processed_parameters, processed_return_value_test
