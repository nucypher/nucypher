import json
from typing import Dict, List, Optional, Tuple, Union

from marshmallow import fields
from web3 import Web3

from nucypher.policy.conditions.base import AccessControlCondition
from nucypher.policy.conditions.context import extract_user_address_from_context
from nucypher.policy.conditions.exceptions import (
    InvalidCondition,
    InvalidConditionContext,
)
from nucypher.policy.conditions.lingo import (
    ConditionType,
)


class WalletAllowlistCondition(AccessControlCondition):
    """
    A condition that checks if a user's wallet address is in a list of allowed addresses.
    The user must provide a signed message to prove ownership of the wallet.
    """

    CONDITION_TYPE = ConditionType.WALLET_ALLOWLIST.value

    class Schema(AccessControlCondition.Schema):
        condition_type = fields.Constant(ConditionType.WALLET_ALLOWLIST.value)
        addresses = fields.List(
            fields.String(required=True),
            required=True,
            validate=lambda addresses: 1 <= len(addresses) <= 25,
        )

    def __init__(
        self,
        addresses: List[str],
        name: Optional[str] = None,
    ):
        """
        Initialize a WalletAllowlistCondition.

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
                normalized_address = Web3.to_checksum_address(address)
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
        if context is None:
            raise InvalidConditionContext(
                "Context is required for wallet-allowlist condition"
            )

        # Extract the user's address from the context
        user_address = extract_user_address_from_context(context)

        # Simply check if the normalized address is in the allowlist
        is_allowed = Web3.to_checksum_address(user_address) in self.addresses

        return is_allowed, None

    def __eq__(self, other):
        return (
            isinstance(other, WalletAllowlistCondition)
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
        Create a WalletAllowlistCondition from a dictionary.

        Args:
            data: Dictionary containing the condition data

        Returns:
            WalletAllowlistCondition instance
        """
        # Extract values from the dict (camelCase keys are converted to snake_case by marshmallow)
        addresses = data.get("addresses", [])
        name = data.get("name")

        # Create a new instance
        return cls(addresses=addresses, name=name)

    @classmethod
    def from_json(cls, data):
        """
        Create a WalletAllowlistCondition from a JSON string.

        Args:
            data: JSON string containing the condition data

        Returns:
            WalletAllowlistCondition instance
        """
        # Parse JSON to dict
        if isinstance(data, str):
            data = json.loads(data)

        return cls.from_dict(data)
