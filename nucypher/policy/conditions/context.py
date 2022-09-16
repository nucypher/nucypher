"""
 This file is part of nucypher.

 nucypher is free software: you can redistribute it and/or modify
 it under the terms of the GNU Affero General Public License as published by
 the Free Software Foundation, either version 3 of the License, or
 (at your option) any later version.

 nucypher is distributed in the hope that it will be useful,
 but WITHOUT ANY WARRANTY; without even the implied warranty of
 MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 GNU Affero General Public License for more details.

 You should have received a copy of the GNU Affero General Public License
 along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""
from typing import Any

from eip712_structs import Bytes, EIP712Struct, String, Uint
from eth_account.account import Account
from eth_account.messages import HexBytes, SignableMessage
from eth_typing import ChecksumAddress
from eth_utils import to_checksum_address

_CONTEXT_DELIMITER = ":"

_USER_ADDRESS_CONTEXT = ":userAddress"

_EIP712_VERSION_1 = b"\x01"


class RequiredContextVariable(Exception):
    pass


class InvalidContextVariableData(Exception):
    pass


class ContextVariableVerificationFailed(Exception):
    pass


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
    class Wallet(EIP712Struct):
        address = String()
        blockNumber = Uint()
        blockHash = Bytes(32)
        signatureText = String()

    try:
        user_address_info = context[_USER_ADDRESS_CONTEXT]
        signature = user_address_info["signature"]
        user_address = to_checksum_address(user_address_info["address"])
        eip712_message = user_address_info["typedData"]
        message, domain = Wallet.from_message(eip712_message)
        signable_message = SignableMessage(
            HexBytes(_EIP712_VERSION_1),
            header=domain.hash_struct(),
            body=message.hash_struct(),
        )

        address = Account.recover_message(
            signable_message=signable_message, signature=signature
        )
        if address == user_address:
            return user_address

        # verification failed
        raise ContextVariableVerificationFailed(
            f"Invalid signature for associated user address"
        )
    except KeyError as e:
        # data could not be processed
        raise InvalidContextVariableData(
            f'Invalid data provided for ":userAddress" context variable; value not found - {e}'
        )


_DIRECTIVES = {
    _USER_ADDRESS_CONTEXT: _recover_user_address,
}


def is_context_variable(parameter: str) -> bool:
    return parameter.startswith(_CONTEXT_DELIMITER)


def get_context_value(context_variable: str, **context) -> Any:
    try:
        func = _DIRECTIVES[
            context_variable
        ]  # These are special context vars that will pre-processed by ursula
    except KeyError:
        # fallback for context variable without directive - assume key,value pair
        # handles the case for user customized context variables
        value = context.get(context_variable)
        if not value:
            raise RequiredContextVariable(
                f'"No value provided for unrecognized context variable "{context_variable}"'
            )
    else:
        value = func(**context)  # required inputs here

    return value
