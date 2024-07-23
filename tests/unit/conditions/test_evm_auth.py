import maya
import pytest
from siwe import SiweMessage

from nucypher.blockchain.eth.signers import InMemorySigner
from nucypher.policy.conditions.auth.evm import EIP712Auth, EIP4361Auth, EvmAuth


def test_auth_scheme():
    for scheme in EvmAuth.AuthScheme:
        expected_scheme = (
            EIP712Auth if scheme == EvmAuth.AuthScheme.EIP712 else EIP4361Auth
        )
        assert EvmAuth.from_scheme(scheme=scheme.value) == expected_scheme

    # non-existent scheme
    with pytest.raises(ValueError):
        _ = EvmAuth.from_scheme(scheme="rando")


def test_authenticate_eip712(valid_eip712_auth_message, get_random_checksum_address):
    data = valid_eip712_auth_message["typedData"]
    signature = valid_eip712_auth_message["signature"]
    address = valid_eip712_auth_message["address"]

    # invalid data
    invalid_data = dict(data)  # make a copy
    del invalid_data["domain"]
    with pytest.raises(EvmAuth.InvalidData):
        EIP712Auth.authenticate(
            data=invalid_data, signature=signature, expected_address=address
        )

    invalid_data = dict(data)  # make a copy
    del invalid_data["message"]
    with pytest.raises(EvmAuth.InvalidData):
        EIP712Auth.authenticate(
            data=invalid_data, signature=signature, expected_address=address
        )

    # signature not for expected address
    incorrect_signature = (
        "0x93252ddff5f90584b27b5eef1915b23a8b01a703be56c8bf0660647c15cb75e9"
        "1983bde9877eaad11da5a3ebc9b64957f1c182536931f9844d0c600f0c41293d1b"
    )
    with pytest.raises(EvmAuth.AuthenticationFailed):
        EIP712Auth.authenticate(
            data=data, signature=incorrect_signature, expected_address=address
        )

    # invalid signature
    invalid_signature = "0xdeadbeef"
    with pytest.raises(EvmAuth.InvalidData):
        EIP712Auth.authenticate(
            data=data, signature=invalid_signature, expected_address=address
        )

    # mismatch with expected address
    with pytest.raises(EvmAuth.AuthenticationFailed):
        EIP712Auth.authenticate(
            data=data,
            signature=signature,
            expected_address=get_random_checksum_address(),
        )

    # everything valid
    EIP712Auth.authenticate(data, signature, address)


def test_authenticate_eip4361(get_random_checksum_address):
    signer = InMemorySigner()
    siwe_message_data = {
        "domain": "login.xyz",
        "address": f"{signer.accounts[0]}",
        "statement": "Sign-In With Ethereum Example Statement",
        "uri": "did:key:z6Mkf55NiCvhxbLg6waBsJ58Hq4Nx6diedT7MGv1189gxV4i",
        "version": "1",
        "nonce": "bTyXgcQxn2htgkjJn",
        "chain_id": 1,
        "issued_at": f"{maya.now().iso8601()}",
        "resources": ["ceramic://*"],
    }
    valid_message = SiweMessage(**siwe_message_data).prepare_message()
    valid_message_signature = signer.sign_message(
        account=signer.accounts[0], message=valid_message.encode()
    )
    valid_address_for_signature = signer.accounts[0]

    # everything valid
    EIP4361Auth.authenticate(
        valid_message, valid_message_signature, valid_address_for_signature
    )

    # invalid data
    invalid_data = "just a regular old string"
    with pytest.raises(EvmAuth.InvalidData):
        EIP4361Auth.authenticate(
            data=invalid_data,
            signature=valid_message_signature,
            expected_address=valid_address_for_signature,
        )

    # signature not for expected address
    incorrect_signature = (
        "0x93252ddff5f90584b27b5eef1915b23a8b01a703be56c8bf0660647c15cb75e9"
        "1983bde9877eaad11da5a3ebc9b64957f1c182536931f9844d0c600f0c41293d1b"
    )
    with pytest.raises(
        EvmAuth.AuthenticationFailed,
        match="EIP4361 verification failed - InvalidSignature",
    ):
        EIP4361Auth.authenticate(
            data=valid_message,
            signature=incorrect_signature,
            expected_address=valid_address_for_signature,
        )

    # invalid signature
    invalid_signature = "0xdeadbeef"
    with pytest.raises(
        EvmAuth.AuthenticationFailed,
        match="EIP4361 verification failed - InvalidSignature",
    ):
        EIP4361Auth.authenticate(
            data=valid_message,
            signature=invalid_signature,
            expected_address=valid_address_for_signature,
        )

    # mismatch with expected address
    with pytest.raises(
        EvmAuth.AuthenticationFailed, match="does not match expected address"
    ):
        EIP4361Auth.authenticate(
            data=valid_message,
            signature=valid_message_signature,
            expected_address=get_random_checksum_address(),
        )

    # stale message
    stale_message_data = dict(siwe_message_data)
    stale_message_data["issued_at"] = (
        f"{maya.now().subtract(hours=EIP4361Auth.FRESHNESS_IN_HOURS + 1).iso8601()}"
    )
    stale_message = SiweMessage(**stale_message_data).prepare_message()
    stale_message_signature = signer.sign_message(
        account=valid_address_for_signature, message=stale_message.encode()
    )
    with pytest.raises(EvmAuth.AuthenticationFailed, match="EIP4361 message is stale"):
        EIP4361Auth.authenticate(
            stale_message, stale_message_signature.hex(), valid_address_for_signature
        )

    # old, but not stale and still valid
    old_but_not_stale_message_data = dict(siwe_message_data)
    old_but_not_stale_message_data["issued_at"] = (
        f"{maya.now().subtract(hours=EIP4361Auth.FRESHNESS_IN_HOURS - 1).iso8601()}"
    )
    old_but_not_stale_message = SiweMessage(
        **old_but_not_stale_message_data
    ).prepare_message()
    old_not_stale_message_signature = signer.sign_message(
        account=valid_address_for_signature, message=old_but_not_stale_message.encode()
    )
    EIP4361Auth.authenticate(
        old_but_not_stale_message,
        old_not_stale_message_signature.hex(),
        valid_address_for_signature,
    )

    # old but not stale, but still fails due to expiry time used in message itself
    not_stale_but_past_expiry = dict(old_but_not_stale_message_data)
    not_stale_but_past_expiry["expiration_time"] = (
        f"{maya.now().subtract(seconds=30).iso8601()}"
    )
    not_stale_but_past_expiry_message = SiweMessage(
        **not_stale_but_past_expiry
    ).prepare_message()
    not_stale_but_past_expiry_signature = signer.sign_message(
        account=valid_address_for_signature,
        message=not_stale_but_past_expiry_message.encode(),
    )
    with pytest.raises(
        EvmAuth.AuthenticationFailed,
        match="EIP4361 verification failed - ExpiredMessage",
    ):
        EIP4361Auth.authenticate(
            not_stale_but_past_expiry_message,
            not_stale_but_past_expiry_signature.hex(),
            valid_address_for_signature,
        )

    # not before specified
    not_before_message_data = dict(siwe_message_data)
    not_before_message_data["not_before"] = f"{maya.now().add(hours=1).iso8601()}"
    not_before_message = SiweMessage(**not_before_message_data).prepare_message()
    not_before_message_signature = signer.sign_message(
        account=valid_address_for_signature, message=not_before_message.encode()
    )
    with pytest.raises(
        EvmAuth.AuthenticationFailed,
        match="EIP4361 verification failed - NotYetValidMessage",
    ):
        EIP4361Auth.authenticate(
            not_before_message,
            not_before_message_signature.hex(),
            valid_address_for_signature,
        )

    # not before specified, so stale message check not performed
    not_before_no_stale_check_message_data = dict(siwe_message_data)
    not_before_no_stale_check_message_data["not_before"] = (
        f"{maya.now().subtract(hours=EIP4361Auth.FRESHNESS_IN_HOURS - 1).iso8601()}"
    )
    # issued more than freshness check hours ago
    old_but_not_stale_message_data["issued_at"] = (
        f"{maya.now().subtract(hours=EIP4361Auth.FRESHNESS_IN_HOURS - 2).iso8601()}"
    )
    not_before_no_stale_check_message = SiweMessage(
        **not_before_no_stale_check_message_data
    ).prepare_message()
    not_before_no_stale_check_message_signature = signer.sign_message(
        account=valid_address_for_signature,
        message=not_before_no_stale_check_message.encode(),
    )
    # even though stale, "not-before" causes check to be skipped
    EIP4361Auth.authenticate(
        not_before_no_stale_check_message,
        not_before_no_stale_check_message_signature.hex(),
        valid_address_for_signature,
    )
