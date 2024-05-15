from enum import Enum

from eth_account.account import Account
from eth_account.messages import HexBytes, encode_typed_data
from siwe import SiweMessage, VerificationError


class Auth:
    class AuthScheme(Enum):
        EIP712 = "EIP712"
        SIWE = "SIWE"

    class InvalidData(Exception):
        pass

    class AuthenticationFailed(Exception):
        pass

    @classmethod
    def authenticate(cls, data, signature, expected_address):
        raise NotImplementedError

    @classmethod
    def from_scheme(cls, scheme: str):
        if scheme == cls.AuthScheme.EIP712.value:
            return EIP712Auth
        elif scheme == cls.AuthScheme.SIWE.value:
            return SIWEAuth

        raise ValueError(f"Invalid authentication scheme: {scheme}")


class EIP712Auth(Auth):
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
            raise cls.InvalidData(f"Invalid auth data: {e.__class__.__name__} - {e}")

        if address_for_signature != expected_address:
            # verification failed - addresses don't match
            raise cls.AuthenticationFailed(
                f"Invalid EIP712 signature; does not match expected address, {expected_address}"
            )


class SIWEAuth(Auth):
    @classmethod
    def authenticate(cls, data, signature, expected_address):
        try:
            siwe_message = SiweMessage(message=data)
        except Exception as e:
            raise cls.InvalidData(
                f"Invalid SIWE message - {e.__class__.__name__} - {e}"
            )

        try:
            siwe_message.verify(signature=signature)
        except VerificationError as e:
            raise cls.AuthenticationFailed(
                f"Invalid SIWE signature - {e.__class__.__name__} - {e}"
            )

        if siwe_message.address != expected_address:
            # verification failed - addresses don't match
            raise cls.AuthenticationFailed(
                f"Invalid SIWE signature; does not match expected address, {expected_address}"
            )
