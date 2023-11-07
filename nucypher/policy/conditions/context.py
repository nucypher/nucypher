from typing import Any, List

from eth_account.account import Account
from eth_account.messages import HexBytes, encode_structured_data
from eth_typing import ChecksumAddress
from eth_utils import to_checksum_address

from nucypher.policy.conditions.exceptions import (
    ContextVariableVerificationFailed,
    InvalidContextVariableData,
    RequiredContextVariable,
)
from nucypher.policy.conditions.lingo import ReturnValueTest

USER_ADDRESS_CONTEXT = ":userAddress"

_CONTEXT_PREFIX = ":"


def _recover_user_address(**context) -> ChecksumAddress:
    # Expected format:
    # {
    #     ":userAddress":
    #         {
    #             "signature": "<signature>",
    #             "address": "<address>",
    #             "typedData": "<a complicated EIP712 data structure>"
    #         }
    # }

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
    return isinstance(variable, str) and variable.startswith(_CONTEXT_PREFIX)


def get_context_value(context_variable: str, **context) -> Any:
    try:
        func = _DIRECTIVES[
            context_variable
        ]  # These are special context vars that will pre-processed by ursula
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


def resolve_any_context_variables(
    parameters: List[Any], return_value_test: ReturnValueTest, **context
):
    processed_parameters = []
    for p in parameters:
        # TODO needs additional support for ERC1155 which has lists of values
        # context variables can only be strings, but other types of parameters can be passed
        if is_context_variable(p):
            p = get_context_value(context_variable=p, **context)
        processed_parameters.append(p)

    v = return_value_test.value
    if is_context_variable(v):
        v = get_context_value(context_variable=v, **context)
    i = return_value_test.index
    processed_return_value_test = ReturnValueTest(
        return_value_test.comparator, value=v, index=i
    )

    return processed_parameters, processed_return_value_test
