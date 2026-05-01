import pytest
from eth_account import Account
from nucypher_core import (
    AAVersion,
    PackedUserOperation,
    PackedUserOperationSignatureRequest,
    UserOperationSignatureRequest,
)

from nucypher.blockchain.eth.signers import InMemorySigner
from nucypher.crypto.powers import ThresholdSigningPower
from nucypher.network.signing import (
    UnsupportedSignatureRequest,
    get_signature_request_object,
    sign_signature_request_data,
)
from tests.utils.erc4337 import create_eth_transfer


@pytest.fixture()
def user_op(get_random_checksum_address):
    return create_eth_transfer(
        sender=get_random_checksum_address(),
        nonce=123,
        to=get_random_checksum_address(),
        value=1_000_000_000,
    )


@pytest.fixture()
def packed_user_op(user_op):
    return PackedUserOperation.from_user_operation(user_op)


@pytest.fixture()
def threshold_signing_power():
    signer = InMemorySigner()
    return ThresholdSigningPower(signer=signer)


def test_get_signature_request_object_invalid_object():
    signature_request = "just a string"
    with pytest.raises(UnsupportedSignatureRequest):
        _ = get_signature_request_object(signature_request)


def test_get_signature_request_object_user_operation(user_op):
    signing_request = UserOperationSignatureRequest(
        user_op=user_op,
        aa_version=AAVersion.V08,
        chain_id=50,
        cohort_id=12,
        context=None,
    )

    request_obj = get_signature_request_object(request=signing_request)
    assert bytes(request_obj) == bytes(user_op)


def test_get_signature_request_object_packed_user_operation(packed_user_op):
    signing_request = PackedUserOperationSignatureRequest(
        packed_user_op=packed_user_op,
        aa_version=AAVersion.V08,
        chain_id=50,
        cohort_id=12,
        context=None,
    )

    request_obj = get_signature_request_object(request=signing_request)
    assert bytes(request_obj) == bytes(packed_user_op)


def test_sign_invalid_request(threshold_signing_power):
    signing_request = "just a string"
    with pytest.raises(UnsupportedSignatureRequest):
        _ = sign_signature_request_data(signing_request, threshold_signing_power)


def test_sign_user_operation_request(user_op, threshold_signing_power):
    signing_request = UserOperationSignatureRequest(
        user_op=user_op,
        aa_version=AAVersion.V08,
        chain_id=50,
        cohort_id=12,
        context=None,
    )
    message_hash, signature = sign_signature_request_data(
        signing_request, threshold_signing_power
    )
    assert len(message_hash) > 0
    assert len(signature) == 65  # ECDSA signature
    recovered_address = Account._recover_hash(
        message_hash=message_hash, signature=signature
    )
    assert recovered_address == threshold_signing_power.account


def test_sign_packed_user_operation_request(packed_user_op, threshold_signing_power):
    signing_request = PackedUserOperationSignatureRequest(
        packed_user_op=packed_user_op,
        aa_version=AAVersion.MDT,
        chain_id=50,
        cohort_id=12,
        context=None,
    )
    message_hash, signature = sign_signature_request_data(
        signing_request, threshold_signing_power
    )
    assert len(message_hash) > 0
    assert len(signature) == 65  # ECDSA signature
    recovered_address = Account._recover_hash(
        message_hash=message_hash, signature=signature
    )
    assert recovered_address == threshold_signing_power.account
