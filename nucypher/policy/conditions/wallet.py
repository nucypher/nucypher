import json
from typing import Any, Dict, List, Optional, Tuple, Union

from eth_account.account import Account
from eth_account.messages import encode_defunct
from eth_typing import ChecksumAddress
from marshmallow import fields
from web3 import Web3

from nucypher.policy.conditions.base import AccessControlCondition
from nucypher.policy.conditions.context import extract_user_address_from_context
from nucypher.policy.conditions.exceptions import (
    ConditionEvaluationFailed,
    InvalidCondition,
    InvalidConditionContext,
)
from nucypher.policy.conditions.lingo import (
    ConditionType,
)
from nucypher.policy.conditions.utils import ConditionProviderManager


class WalletAllowlistCondition(AccessControlCondition):
    """
    A condition that checks if a user's wallet address is in a list of allowed addresses.
    The user must provide a signed message to prove ownership of the wallet.
    """

    CONDITION_TYPE = ConditionType.WALLET_ALLOWLIST.value
    MESSAGE_PREFIX = "Authorizing decryption with wallet: "

    class Schema(AccessControlCondition.Schema):
        condition_type = fields.Constant(ConditionType.WALLET_ALLOWLIST.value)
        addresses = fields.List(
            fields.String(required=True),
            required=True,
            validate=lambda addresses: 1 <= len(addresses) <= 10,
        )

    def __init__(
        self,
        addresses: List[str],
        name: Optional[str] = None,
    ):
        """
        Initialize a WalletAllowlistCondition.

        Args:
            addresses: List of wallet addresses that are allowed to decrypt
            name: Optional name for the condition
        """
        # Validate and normalize all addresses
        normalized_addresses = []
        for address in addresses:
            try:
                # Ensure addresses have proper checksum
                normalized_address = Web3.to_checksum_address(address)
                normalized_addresses.append(normalized_address)
            except ValueError as e:
                raise InvalidCondition(f"Invalid Ethereum address: {address}") from e

        # Check for duplicates
        if len(set(normalized_addresses)) != len(normalized_addresses):
            raise InvalidCondition("Duplicate addresses are not allowed")

        # Set addresses before init to ensure it's available during validation
        self.addresses = normalized_addresses

        super().__init__(
            condition_type=self.CONDITION_TYPE,
            name=name,
        )

    def verify(
        self,
        **context
    ) -> Tuple[bool, Union[None, Dict]]:
        """
        Verify if the user's wallet address is in the allowlist.

        Args:
            context: Dictionary containing context data, including the user's address
        
        Returns:
            Tuple of (is_allowed, None) where is_allowed indicates if the address
            is in the allowlist
        
        Returns:
            Tuple containing:
                - Boolean indicating if verification passed
                - None (no additional data returned)
        """
        if context is None:
            raise InvalidConditionContext("Context is required for wallet-allowlist condition")

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
