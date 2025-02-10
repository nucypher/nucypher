import re
from functools import partial
from typing import Any, Dict, List, Optional, Union

from eth_typing import ChecksumAddress
from eth_utils import to_checksum_address

from nucypher.policy.conditions.auth.evm import EvmAuth
from nucypher.policy.conditions.exceptions import (
    ContextVariableVerificationFailed,
    InvalidContextVariableData,
    RequiredContextVariable,
)
from nucypher.policy.conditions.utils import ConditionProviderManager

USER_ADDRESS_CONTEXT = ":userAddress"
USER_ADDRESS_EIP4361_EXTERNAL_CONTEXT = ":userAddressExternalEIP4361"

CONTEXT_PREFIX = ":"
CONTEXT_REGEX = re.compile(":[a-zA-Z_][a-zA-Z0-9_]*")

USER_ADDRESS_SCHEMES = {
    USER_ADDRESS_CONTEXT: None,  # allow any scheme (EIP4361, EIP1271, EIP712) for now; eventually EIP712 will be deprecated
    USER_ADDRESS_EIP4361_EXTERNAL_CONTEXT: EvmAuth.AuthScheme.EIP4361.value,
}


class UnexpectedScheme(Exception):
    pass


def _resolve_user_address(
    user_address_context_variable: str,
    providers: Optional[ConditionProviderManager] = None,
    **context,
) -> ChecksumAddress:
    """
    Recovers a checksum address from a signed message.

    Expected format:
    {
        ":userAddress...":
            {
                "signature": "<signature>",
                "address": "<address>",
                "scheme": "EIP4361" | "EIP1271" | ...
                "typedData": ...
            }
    }
    """
    try:
        user_address_info = context[user_address_context_variable]
        signature = user_address_info["signature"]
        expected_address = to_checksum_address(user_address_info["address"])
        typed_data = user_address_info["typedData"]

        # if empty assume EIP712, although EIP712 will eventually be deprecated
        scheme = user_address_info.get("scheme", EvmAuth.AuthScheme.EIP712.value)
        expected_scheme = USER_ADDRESS_SCHEMES[user_address_context_variable]
        if expected_scheme and scheme != expected_scheme:
            raise UnexpectedScheme(
                f"Expected {expected_scheme} authentication scheme, but received {scheme}"
            )

        auth = EvmAuth.from_scheme(scheme)
        auth.authenticate(
            data=typed_data,
            signature=signature,
            expected_address=expected_address,
            providers=providers,
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
    USER_ADDRESS_EIP4361_EXTERNAL_CONTEXT: partial(
        _resolve_user_address,
        user_address_context_variable=USER_ADDRESS_EIP4361_EXTERNAL_CONTEXT,
    ),
}


def is_context_variable(variable) -> bool:
    return isinstance(variable, str) and CONTEXT_REGEX.fullmatch(variable)


def string_contains_context_variable(variable: str) -> bool:
    matches = re.findall(CONTEXT_REGEX, variable)
    return bool(matches)


def get_context_value(
    context_variable: str,
    providers: Optional[ConditionProviderManager] = None,
    **context,
) -> Any:
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
        value = func(providers=providers, **context)  # required inputs here

    return value


def resolve_any_context_variables(
    param: Union[Any, List[Any], Dict[Any, Any]],
    providers: Optional[ConditionProviderManager] = None,
    **context,
):
    if isinstance(param, list):
        return [
            resolve_any_context_variables(item, providers, **context) for item in param
        ]
    elif isinstance(param, dict):
        return {
            k: resolve_any_context_variables(v, providers, **context)
            for k, v in param.items()
        }
    elif isinstance(param, str):
        # either it is a context variable OR contains a context variable within it
        # TODO separating the two cases for now out of concern of regex searching
        #  within strings (case 2)
        if is_context_variable(param):
            return get_context_value(
                context_variable=param, providers=providers, **context
            )
        else:
            matches = re.findall(CONTEXT_REGEX, param)
            for context_var in matches:
                # checking out of concern for faulty regex search within string
                if context_var in context:
                    resolved_var = get_context_value(
                        context_variable=context_var, providers=providers, **context
                    )
                    param = param.replace(context_var, str(resolved_var))
            return param
    else:
        return param
