import json
from typing import Dict, List, Optional, Tuple, Union

from eth_utils import to_checksum_address
from marshmallow import fields, validate

from nucypher.policy.conditions.base import AccessControlCondition
from nucypher.policy.conditions.context import (
    USER_ADDRESS_CONTEXT,
    resolve_any_context_variables,
)
from nucypher.policy.conditions.exceptions import (
    InvalidCondition,
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
        condition_type = fields.Constant(ConditionType.ADDRESS_ALLOWLIST.value)
        addresses = fields.List(
            fields.String(required=True),
            required=True,
            validate=validate.Length(min=1, max=25),
        )

    def __init__(
        self,
        addresses: List[str],
        name: Optional[str] = None,
    ):
        """
        Initialize a AddressAllowlistCondition.

        Args:
            addresses: List of checksummed wallet addresses that are allowed to decrypt (must be
             properly checksummed Ethereum addresses or an exception will be raised)
            name: Optional name for the condition
        """
        # Check for duplicates
        if len(set(addresses)) != len(addresses):
            raise InvalidCondition("Duplicate addresses are not allowed")

        # Validate all addresses
        for address in addresses:
            try:
                # Ensure addresses have proper checksum
                normalized_address = to_checksum_address(address)
            except ValueError as e:
                raise InvalidCondition(f"Invalid Ethereum address: {address}") from e
            if normalized_address != address:
                raise InvalidCondition(
                    f"Address {address} is not a checksummed address"
                )

        # Store the validated addresses
        self.addresses = addresses

        super().__init__(
            condition_type=self.CONDITION_TYPE,
            name=name,
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
            raise InvalidConditionContext(
                "Context is required for address-allowlist condition"
            )

        # Get user's address using resolve_any_context_variables
        user_address = resolve_any_context_variables(context[USER_ADDRESS_CONTEXT])[
            "address"
        ]
        # Simply check if the normalized address is in the allowlist
        is_allowed = to_checksum_address(user_address) in self.addresses

        return is_allowed, None

    def __eq__(self, other):
        return (
            isinstance(other, AddressAllowlistCondition)
            and self.condition_type == other.condition_type
            and set(self.addresses) == set(other.addresses)
            and self.name == other.name
        )

    def __repr__(self):
        addresses_str = ", ".join(self.addresses[:3])
        if len(self.addresses) > 3:
            addresses_str += f"... (+{len(self.addresses) - 3} more)"
        return f"{self.__class__.__name__}(addresses=[{addresses_str}])"

    @classmethod
    def from_dict(cls, data):
        """
        Create a AddressAllowlistCondition from a dictionary.

        Args:
            data: Dictionary containing the condition data

        Returns:
            AddressAllowlistCondition instance
        """
        # Extract values from the dict (camelCase keys are converted to snake_case by marshmallow)
        addresses = data.get("addresses", [])
        name = data.get("name")

        # Create a new instance
        return cls(addresses=addresses, name=name)

    @classmethod
    def from_json(cls, data):
        """
        Create a AddressAllowlistCondition from a JSON string.

        Args:
            data: JSON string containing the condition data

        Returns:
            AddressAllowlistCondition instance
        """
        # Parse JSON to dict
        if isinstance(data, str):
            data = json.loads(data)

        return cls.from_dict(data)
