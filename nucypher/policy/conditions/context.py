import re
from functools import partial
from typing import Any, List, Union

from eth_typing import ChecksumAddress
from eth_utils import to_checksum_address

from nucypher.policy.conditions.auth.evm import EvmAuth
from nucypher.policy.conditions.exceptions import (
    ContextVariableVerificationFailed,
    InvalidContextVariableData,
    RequiredContextVariable,
)

USER_ADDRESS_CONTEXT = ":userAddress"
USER_ADDRESS_EIP712_CONTEXT = ":userAddressEIP712"
USER_ADDRESS_EIP4361_CONTEXT = ":userAddressEIP4361"
USER_ADDRESS_EIP4361_EXTERNAL_CONTEXT = ":userAddressExternalEIP4361"

CONTEXT_PREFIX = ":"
CONTEXT_REGEX = re.compile(":[a-zA-Z_][a-zA-Z0-9_]*")

USER_ADDRESS_SCHEMES = {
    USER_ADDRESS_CONTEXT: None,  # TODO either EIP712 or EIP4361 for now, but should use the default that is eventually decided (likely EIP4361) - #tdec/178
    USER_ADDRESS_EIP712_CONTEXT: EvmAuth.AuthScheme.EIP712.value,
    USER_ADDRESS_EIP4361_CONTEXT: EvmAuth.AuthScheme.EIP4361.value,
    USER_ADDRESS_EIP4361_EXTERNAL_CONTEXT: EvmAuth.AuthScheme.EIP4361.value,
}


class UnexpectedScheme(Exception):
    pass


def _resolve_user_address(user_address_context_variable, **context) -> ChecksumAddress:
    """
    Recovers a checksum address from a signed message.

    Expected format:
    {
        ":userAddress...":
            {
                "signature": "<signature>",
                "address": "<address>",
                "scheme": "EIP712" | "EIP4361" | ...
                "typedData": ...
            }
    }
    """
    try:
        user_address_info = context[user_address_context_variable]
        signature = user_address_info["signature"]
        expected_address = to_checksum_address(user_address_info["address"])
        typed_data = user_address_info["typedData"]

        scheme = user_address_info.get("scheme", EvmAuth.AuthScheme.EIP712.value)
        expected_scheme = USER_ADDRESS_SCHEMES[user_address_context_variable]
        if expected_scheme and scheme != expected_scheme:
            raise UnexpectedScheme(
                f"Expected {expected_scheme} authentication scheme, but received {scheme}"
            )

        auth = EvmAuth.from_scheme(scheme)
        auth.authenticate(
            data=typed_data, signature=signature, expected_address=expected_address
        )
    except EvmAuth.InvalidData as e:
        raise InvalidContextVariableData(
            f"Invalid context variable data for '{user_address_context_variable}'; {e}"
        )
    except EvmAuth.AuthenticationFailed as e:
        raise ContextVariableVerificationFailed(
            f"Authentication failed for '{user_address_context_variable}'; {e}"
        )
    except Exception as e:
        # data could not be processed
        raise InvalidContextVariableData(
            f"Invalid context variable data for '{user_address_context_variable}'; {e.__class__.__name__} - {e}"
        )

    return expected_address


_DIRECTIVES = {
    USER_ADDRESS_CONTEXT: partial(
        _resolve_user_address, user_address_context_variable=USER_ADDRESS_CONTEXT
    ),
    USER_ADDRESS_EIP712_CONTEXT: partial(
        _resolve_user_address, user_address_context_variable=USER_ADDRESS_EIP712_CONTEXT
    ),
    USER_ADDRESS_EIP4361_CONTEXT: partial(
        _resolve_user_address,
        user_address_context_variable=USER_ADDRESS_EIP4361_CONTEXT,
    ),
    USER_ADDRESS_EIP4361_EXTERNAL_CONTEXT: partial(
        _resolve_user_address,
        user_address_context_variable=USER_ADDRESS_EIP4361_EXTERNAL_CONTEXT,
    ),
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
