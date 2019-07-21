import functools

from twisted.logger import Logger
from typing import Callable
import inspect
import eth_utils

from nucypher.crypto.api import keccak_digest

VERIFIED_ADDRESSES = set()


def validate_checksum_address(func: Callable) -> Callable:
    """
    EIP-55 Checksum address validation decorator.

    Inspects the decorated function for an input parameter "checksum_address",
    then uses `eth_utils` to validate the address EIP-55 checksum,
    verifying the input type on failure; Raises TypeError
    or InvalidChecksumAddress if validation fails, respectively.

    EIP-55 Specification: https://github.com/ethereum/EIPs/blob/master/EIPS/eip-55.md
    ETH Utils Implementation: https://github.com/ethereum/eth-utils

    """

    parameter_name = 'checksum_address'
    log = Logger('EIP-55-validator')

    class InvalidChecksumAddress(eth_utils.exceptions.ValidationError):
        pass

    @functools.wraps(func)
    def wrapped(*args, **kwargs):

        # Check for the presence of a checksum address in this call
        params = inspect.getcallargs(func, *args, **kwargs)
        try:
            checksum_address = params[parameter_name]

        # No checksum_address present in this call
        except KeyError:
            return func(*args, **kwargs)  # ... don't mind me!

        if checksum_address in VERIFIED_ADDRESSES:
            return func(*args, **kwargs)  # ... nothing to validate

        # Optional checksum_address present in this call
        signature = inspect.signature(func)
        checksum_address_is_optional = signature.parameters[parameter_name].default is None
        if checksum_address_is_optional and checksum_address is None:
            return func(*args, **kwargs)  # ... nothing to validate

        # Validate
        address_is_valid = eth_utils.is_checksum_address(checksum_address)
        VERIFIED_ADDRESSES.add(checksum_address)

        # OK!
        if address_is_valid:
            return func(*args, **kwargs)

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

    return wrapped


def validate_secret(func: Callable) -> Callable:
    """Decorator to enforce correct upgrade/rollback secret in upgradeable contracts"""

    parameter_name = 'existing_secret_plaintext'
    log = Logger('Upgrade-Secret-Validator')

    @functools.wraps(func)
    def wrapped(self, *args, **kwargs):

        # Check for the presence of a plaintext secret in this call
        params = inspect.getcallargs(func, self, *args, **kwargs)
        try:
            secret = params[parameter_name]
        except KeyError:  # No plaintext secret present in this call
            found_params = ', '.join("'{}'".format(p) for p in params)
            message = f"Incorrect use of decorator: '{parameter_name}' not found. " \
                      f"Found parameters are: {found_params}"
            log.debug(message)
            raise TypeError(message)

        # Validate
        secret_hash = self.contract.functions.secretHash().call()
        is_valid_secret = secret_hash == keccak_digest(secret)

        if is_valid_secret:  # Yay!  \ (•◡•) /
            return func(self, *args, **kwargs)
        else:
            message = f"The secret provided for upgrade/rollback {self.contract_name} is not valid."
            raise self.ContractDeploymentError(message)

    return wrapped
