import pytest

from nucypher.policy.conditions.auth import Auth, EIP712Auth, SIWEAuth
from nucypher.policy.conditions.context import USER_ADDRESS_CONTEXT


def test_auth_scheme():
    for scheme in Auth.AuthScheme:
        expected_scheme = EIP712Auth if scheme == Auth.AuthScheme.EIP712 else SIWEAuth
        assert Auth.from_scheme(scheme=scheme.value) == expected_scheme

    # non-existent scheme
    with pytest.raises(ValueError):
        _ = Auth.from_scheme(scheme="rando")


@pytest.mark.parametrize(
    "valid_user_address_context", [Auth.AuthScheme.EIP712.value], indirect=True
)
def test_authenticate_eip712(valid_user_address_context, get_random_checksum_address):
    data = valid_user_address_context[USER_ADDRESS_CONTEXT]["typedData"]
    signature = valid_user_address_context[USER_ADDRESS_CONTEXT]["signature"]
    address = valid_user_address_context[USER_ADDRESS_CONTEXT]["address"]

    # invalid data
    invalid_data = dict(data)  # make a copy
    del invalid_data["domain"]
    with pytest.raises(Auth.InvalidData):
        EIP712Auth.authenticate(
            data=invalid_data, signature=signature, expected_address=address
        )

    invalid_data = dict(data)  # make a copy
    del invalid_data["message"]
    with pytest.raises(Auth.InvalidData):
        EIP712Auth.authenticate(
            data=invalid_data, signature=signature, expected_address=address
        )

    # signature does not match expected address
    incorrect_signature = (
        "0x93252ddff5f90584b27b5eef1915b23a8b01a703be56c8bf0660647c15cb75e9"
        "1983bde9877eaad11da5a3ebc9b64957f1c182536931f9844d0c600f0c41293d1b"
    )
    with pytest.raises(Auth.AuthenticationFailed):
        EIP712Auth.authenticate(
            data=data, signature=incorrect_signature, expected_address=address
        )

    # invalid signature
    invalid_signature = "0xdeadbeef"
    with pytest.raises(Auth.InvalidData):
        EIP712Auth.authenticate(
            data=data, signature=invalid_signature, expected_address=address
        )

    # mismatch with expected address
    with pytest.raises(Auth.AuthenticationFailed):
        EIP712Auth.authenticate(
            data=data,
            signature=signature,
            expected_address=get_random_checksum_address(),
        )

    # everything valid
    EIP712Auth.authenticate(data, signature, address)


@pytest.mark.parametrize(
    "valid_user_address_context", [Auth.AuthScheme.SIWE.value], indirect=True
)
def test_authenticate_siwe(valid_user_address_context, get_random_checksum_address):
    data = valid_user_address_context[USER_ADDRESS_CONTEXT]["typedData"]
    signature = valid_user_address_context[USER_ADDRESS_CONTEXT]["signature"]
    address = valid_user_address_context[USER_ADDRESS_CONTEXT]["address"]

    # invalid data
    invalid_data = "just a regular old string"
    with pytest.raises(Auth.InvalidData):
        SIWEAuth.authenticate(
            data=invalid_data, signature=signature, expected_address=address
        )

    # signature does not match expected address
    incorrect_signature = (
        "0x93252ddff5f90584b27b5eef1915b23a8b01a703be56c8bf0660647c15cb75e9"
        "1983bde9877eaad11da5a3ebc9b64957f1c182536931f9844d0c600f0c41293d1b"
    )
    with pytest.raises(Auth.AuthenticationFailed):
        SIWEAuth.authenticate(
            data=data, signature=incorrect_signature, expected_address=address
        )

    # invalid signature
    invalid_signature = "0xdeadbeef"
    with pytest.raises(Auth.AuthenticationFailed):
        SIWEAuth.authenticate(
            data=data, signature=invalid_signature, expected_address=address
        )

    # mismatch with expected address
    with pytest.raises(Auth.AuthenticationFailed):
        SIWEAuth.authenticate(
            data=data,
            signature=signature,
            expected_address=get_random_checksum_address(),
        )

    # everything valid
    SIWEAuth.authenticate(data, signature, address)
