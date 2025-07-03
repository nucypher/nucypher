from typing import Dict, List, Optional, Tuple, Union

from eth_utils import to_checksum_address
from hexbytes import HexBytes
from marshmallow import (
    ValidationError,
    fields,
    post_load,
    validate,
    validates,
)

from nucypher.policy.conditions.base import AccessControlCondition
from nucypher.policy.conditions.context import (
    USER_ADDRESS_CONTEXT,
    resolve_any_context_variables,
)
from nucypher.policy.conditions.exceptions import (
    InvalidConditionContext,
)
from nucypher.policy.conditions.lingo import (
    ConditionType,
)


class AddressAllowlistCondition(AccessControlCondition):
    """
    A condition that checks if a user's wallet address is in a list of allowed addresses.
    The user must provide a signed message to prove ownership of the wallet.
    """

    CONDITION_TYPE = ConditionType.ADDRESS_ALLOWLIST.value

    class Schema(AccessControlCondition.Schema):

        # Maximum number of addresses allowed in the address allowlist
        MAX_ALLOWLIST_ADDRESSES = 25

        condition_type = fields.Str(
            validate=validate.Equal(ConditionType.ADDRESS_ALLOWLIST.value),
            required=True,
        )
        user_address = fields.Str(
            validate=validate.Equal(USER_ADDRESS_CONTEXT),
            required=True,
        )
        addresses = fields.List(
            fields.String(required=True),
            required=True,
            validate=validate.Length(min=1, max=MAX_ALLOWLIST_ADDRESSES),
        )

        @validates("addresses")
        def validate_addresses(self, addresses):
            # Check for duplicates
            if len(set(addresses)) != len(addresses):
                raise ValidationError("Duplicate addresses are not allowed")

            # Validate all addresses
            for address in addresses:
                try:
                    # Ensure addresses are valid
                    to_checksum_address(address)
                except ValueError as e:
                    raise ValidationError(
                        f"Invalid Ethereum address: '{address}', provided in the list of addresses"
                    ) from e

        @post_load
        def make(self, data, **kwargs):
            return AddressAllowlistCondition(**data)

    def __init__(
        self,
        addresses: List[str],
        user_address: str = USER_ADDRESS_CONTEXT,
        condition_type: str = ConditionType.ADDRESS_ALLOWLIST.value,
        name: Optional[str] = None,
        *args,
        **kwargs,
    ):
        self.user_address = user_address

        self.addresses = addresses

        super().__init__(
            condition_type=condition_type,
            name=name,
            *args,
            **kwargs,
        )

    def verify(self, **context) -> Tuple[bool, Union[None, Dict]]:
        """
        Verify if the user's wallet address is in the allowlist.

        Args:
            context: Dictionary containing context data, including the user's address

        Returns:
            Tuple containing:
                - Boolean indicating if verification passed
                - None (no additional data returned)
        """
        if not context:
            raise InvalidConditionContext("No value provided for context variable")

        # Get user's address using resolve_any_context_variables
        user_address = resolve_any_context_variables(self.user_address, **context)

        user_address_bytes = bytes(HexBytes(user_address))
        # the addresses are supposed to be already validated, in taco-web, to have a valid checksum
        addresses_bytes = [bytes(HexBytes(address)) for address in self.addresses]
        # Simply check if the user address is in the allowlist
        is_allowed = user_address_bytes in addresses_bytes

        return is_allowed, None

    def __repr__(self):
        return f"{self.__class__.__name__}(addresses_count={len(self.addresses)})"
