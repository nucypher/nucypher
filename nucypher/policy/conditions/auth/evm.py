from enum import Enum
from typing import List

import maya
from eth_account.account import Account
from eth_account.messages import HexBytes, encode_typed_data
from siwe import SiweMessage, VerificationError


class EvmAuth:
    class AuthScheme(Enum):
        EIP712 = "EIP712"
        EIP4361 = "EIP4361"

        @classmethod
        def values(cls) -> List[str]:
            return [scheme.value for scheme in cls]

    class InvalidData(Exception):
        pass

    class AuthenticationFailed(Exception):
        pass

    class StaleMessage(AuthenticationFailed):
        """The message is too old."""
        pass

    @classmethod
    def authenticate(cls, data, signature, expected_address):
        raise NotImplementedError

    @classmethod
    def from_scheme(cls, scheme: str):
        if scheme == cls.AuthScheme.EIP712.value:
            return EIP712Auth
        elif scheme == cls.AuthScheme.EIP4361.value:
            return EIP4361Auth

        raise ValueError(f"Invalid authentication scheme: {scheme}")


class EIP712Auth(EvmAuth):
    @classmethod
    def authenticate(cls, data, signature, expected_address):
        try:
            # convert hex data for byte fields - bytes are expected by underlying library
            # 1. salt
            salt = data["domain"]["salt"]
            data["domain"]["salt"] = HexBytes(salt)
            # 2. blockHash
            blockHash = data["message"]["blockHash"]
            data["message"]["blockHash"] = HexBytes(blockHash)

            signable_message = encode_typed_data(full_message=data)
            address_for_signature = Account.recover_message(
                signable_message=signable_message, signature=signature
            )
        except Exception as e:
            # data could not be processed
            raise cls.InvalidData(
                f"Invalid EIP712 message: {str(e) or e.__class__.__name__}"
            )

        if address_for_signature != expected_address:
            # verification failed - addresses don't match
            raise cls.AuthenticationFailed(
                f"EIP712 verification failed; signature not valid for expected address, {expected_address}"
            )


class EIP4361Auth(EvmAuth):
    FRESHNESS_IN_HOURS = 2

    @classmethod
    def authenticate(cls, data, signature, expected_address):
        try:
            siwe_message = SiweMessage.from_message(message=data)
        except Exception as e:
            raise cls.InvalidData(
                f"Invalid EIP4361 message - {str(e) or e.__class__.__name__}"
            )

        try:
            # performs various validation checks on message eg. expiration, not-before, signature etc.
            siwe_message.verify(signature=signature)
        except VerificationError as e:
            raise cls.AuthenticationFailed(
                f"EIP4361 verification failed - {str(e) or e.__class__.__name__}"
            )

        # enforce a freshness check - reference point is issued at
        issued_at = maya.MayaDT.from_iso8601(siwe_message.issued_at)
        now = maya.now()
        if issued_at > now:
            raise cls.AuthenticationFailed(
                f"EIP4361 issued-at datetime is in the future: {issued_at.iso8601()}"
            )
        if now > issued_at.add(hours=cls.FRESHNESS_IN_HOURS):
            raise cls.StaleMessage(
                f"EIP4361 message is more than {cls.FRESHNESS_IN_HOURS} "
                f"hours old (issued at {issued_at.iso8601()})"
            )

        if siwe_message.address != expected_address:
            # verification failed - addresses don't match
            raise cls.AuthenticationFailed(
                f"Invalid EIP4361 signature; signature not valid for expected address, {expected_address}"
            )
