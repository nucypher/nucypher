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

import eth_utils
import functools
import inspect
from constant_sorrow.constants import (
    CONTRACT_ATTRIBUTE,
    CONTRACT_CALL,
    TRANSACTION,
    UNKNOWN_CONTRACT_INTERFACE,
    NO_BLOCKCHAIN_CONNECTION
)
from datetime import datetime
from typing import Callable, Optional, Union

from nucypher.types import ContractReturnValue
from nucypher.utilities.logging import Logger

ContractInterfaces = Union[
    CONTRACT_CALL,
    TRANSACTION,
    CONTRACT_ATTRIBUTE,
    UNKNOWN_CONTRACT_INTERFACE
]


__VERIFIED_ADDRESSES = set()


class InvalidChecksumAddress(eth_utils.exceptions.ValidationError):
    pass


def validate_checksum_address(func: Callable) -> Callable:
    """
    EIP-55 Checksum address validation decorator.

    Inspects the decorated function for input parameters ending with "_address",
    then uses `eth_utils` to validate the addresses' EIP-55 checksum,
    verifying the input type on failure; Raises TypeError
    or InvalidChecksumAddress if validation fails, respectively.

    EIP-55 Specification: https://github.com/ethereum/EIPs/blob/master/EIPS/eip-55.md
    ETH Utils Implementation: https://github.com/ethereum/eth-utils

    """

    parameter_name_suffix = '_address'
    aliases = ('account', 'address')
    log = Logger('EIP-55-validator')

    @functools.wraps(func)
    def wrapped(*args, **kwargs):

        # Check for the presence of checksum addresses in this call
        params = inspect.getcallargs(func, *args, **kwargs)
        addresses_as_parameters = (parameter_name for parameter_name in params
                                   if parameter_name.endswith(parameter_name_suffix)
                                   or parameter_name in aliases)

        for parameter_name in addresses_as_parameters:
            checksum_address = params[parameter_name]

            if checksum_address in __VERIFIED_ADDRESSES:
                continue

            signature = inspect.signature(func)
            parameter_is_optional = signature.parameters[parameter_name].default is None
            if parameter_is_optional and checksum_address is None or checksum_address is NO_BLOCKCHAIN_CONNECTION:
                continue

            address_is_valid = eth_utils.is_checksum_address(checksum_address)
            # OK!
            if address_is_valid:
                __VERIFIED_ADDRESSES.add(checksum_address)
                continue

            # Invalid Type
            if not isinstance(checksum_address, str):
                actual_type_name = checksum_address.__class__.__name__
                message = '{} is an invalid type for parameter "{}".'.format(actual_type_name, parameter_name)
                log.debug(message)
                raise TypeError(message)

            # Invalid Value
            message = '"{}" is not a valid EIP-55 checksum address.'.format(checksum_address)
            log.debug(message)
            raise InvalidChecksumAddress(message)
        else:
            return func(*args, **kwargs)

    return wrapped


def only_me(func: Callable) -> Callable:
    """Decorator to enforce invocation of permissioned actor methods"""
    @functools.wraps(func)
    def wrapped(actor=None, *args, **kwargs):
        if not actor.is_me:
            raise actor.StakerError("You are not {}".format(actor.__class.__.__name__))
        return func(actor, *args, **kwargs)
    return wrapped


def save_receipt(actor_method) -> Callable:  # TODO: rename to "save_result"?
    """Decorator to save the result of a function with a timestamp"""
    @functools.wraps(actor_method)
    def wrapped(self, *args, **kwargs) -> dict:
        receipt_or_txhash = actor_method(self, *args, **kwargs)
        self._saved_receipts.append((datetime.utcnow(), receipt_or_txhash))
        return receipt_or_txhash
    return wrapped


#
# Contract Function Handling
#


# TODO: Auto disable collection in prod (detect test package?)
COLLECT_CONTRACT_API = True


def contract_api(interface: Optional[ContractInterfaces] = UNKNOWN_CONTRACT_INTERFACE) -> Callable:
    """Decorator factory for contract API markers"""

    def decorator(agent_method: Callable) -> Callable[..., ContractReturnValue]:
        """
        Marks an agent method as containing contract interactions (transaction or call)
        and validates outbound checksum addresses for EIP-55 compliance.

        If `COLLECT_CONTRACT_API` is True when running tests,
        all marked methods will be collected for automatic mocking
        and integration with pytest fixtures.
        """
        if COLLECT_CONTRACT_API:
            agent_method.contract_api = interface
        agent_method = validate_checksum_address(func=agent_method)
        return agent_method

    return decorator
