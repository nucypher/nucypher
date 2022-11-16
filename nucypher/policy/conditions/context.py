
from typing import Any

from eip712_structs import Bytes, EIP712Struct, String, Uint
from eth_account.account import Account
from eth_account.messages import HexBytes, SignableMessage
from eth_typing import ChecksumAddress
from eth_utils import to_checksum_address

from nucypher.policy.conditions.exceptions import (
    ContextVariableVerificationFailed,
    InvalidContextVariableData,
    RequiredContextVariable,
)

USER_ADDRESS_CONTEXT = ":userAddress"

_CONTEXT_PREFIX = ":"

_EIP712_VERSION_BYTE = b"\x01"


class UserAddress(EIP712Struct):
    address = String()
    blockNumber = Uint()
    blockHash = Bytes(32)
    signatureText = String()


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
        message, domain = UserAddress.from_message(eip712_message)
        signable_message = SignableMessage(
            HexBytes(_EIP712_VERSION_BYTE),
            header=domain.hash_struct(),
            body=message.hash_struct(),
        )
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
                f'"No value provided for unrecognized context variable "{context_variable}"'
            )
    else:
        value = func(**context)  # required inputs here

    return value
