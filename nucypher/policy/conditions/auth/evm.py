from enum import Enum
from typing import List

import maya
from siwe import SiweMessage, VerificationError


class EvmAuth:
    class AuthScheme(Enum):
        EIP4361 = "EIP4361"

        @classmethod
        def values(cls) -> List[str]:
            return [scheme.value for scheme in cls]

    class InvalidData(Exception):
        pass

    class AuthenticationFailed(Exception):
        pass

    @classmethod
    def authenticate(cls, data, signature, expected_address):
        raise NotImplementedError

    @classmethod
    def from_scheme(cls, scheme: str):
        if scheme == cls.AuthScheme.EIP4361.value:
            return EIP4361Auth

        raise ValueError(f"Invalid authentication scheme: {scheme}")


class EIP4361Auth(EvmAuth):
    FRESHNESS_IN_HOURS = 2

    @classmethod
    def authenticate(cls, data, signature, expected_address):
        try:
            siwe_message = SiweMessage(message=data)
        except Exception as e:
            raise cls.InvalidData(
                f"Invalid EIP4361 message - {str(e) or e.__class__.__name__}"
            )

        try:
            siwe_message.verify(signature=signature)
        except VerificationError as e:
            raise cls.AuthenticationFailed(
                f"EIP4361 verification failed - {str(e) or e.__class__.__name__}"
            )

        # enforce a freshness check
        # TODO: "not-before" throws off the freshness timing; so skip if specified.
        #  Is this safe / what we want?
        if not siwe_message.not_before:
            issued_at = maya.MayaDT.from_iso8601(siwe_message.issued_at)
            if maya.now() > issued_at.add(hours=cls.FRESHNESS_IN_HOURS):
                raise cls.AuthenticationFailed(
                    f"EIP4361 message is stale; more than {cls.FRESHNESS_IN_HOURS} "
                    f"hours old (issued at {issued_at.iso8601()})"
                )

        if siwe_message.address != expected_address:
            # verification failed - addresses don't match
            raise cls.AuthenticationFailed(
                f"Invalid EIP4361 signature; does not match expected address, {expected_address}"
            )
