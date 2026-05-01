import pytest
from nucypher_core import (
    AAVersion,
    EncryptedThresholdSignatureRequest,
    EncryptedThresholdSignatureResponse,
    PackedUserOperation,
    PackedUserOperationSignatureRequest,
    SessionSecretFactory,
    SessionStaticSecret,
    SignatureResponse,
    UserOperationSignatureRequest,
)

from nucypher.crypto.powers import (
    SigningRequestPower,
    ThresholdSigningPower,
)
from tests.utils.erc4337 import create_eth_transfer


@pytest.fixture(scope="module")
def signing_request_power():
    session_secret_factory = SessionSecretFactory.random()
    return SigningRequestPower(session_secret_factory=session_secret_factory)


@pytest.fixture(scope="module")
def user_op_signature_request(get_random_checksum_address):
    user_op = create_eth_transfer(
        sender=get_random_checksum_address(),
        nonce=123,
        to=get_random_checksum_address(),
        value=1_000_000_000,
    )
    return UserOperationSignatureRequest(
        user_op=user_op,
        aa_version=AAVersion.V08,
        chain_id=50,
        cohort_id=12,
        context=None,
    )


@pytest.fixture(scope="module")
def packed_user_op_signature_request(user_op_signature_request):
    packed_user_op = PackedUserOperation.from_user_operation(
        user_op_signature_request.user_op
    )
    return PackedUserOperationSignatureRequest(
        packed_user_op=packed_user_op,
        aa_version=user_op_signature_request.aa_version,
        chain_id=user_op_signature_request.chain_id,
        cohort_id=user_op_signature_request.cohort_id,
        context=user_op_signature_request.context,
    )


def test_signing_request_power_public_key_derivation(signing_request_power):
    assert bytes(signing_request_power.get_pubkey_from_id(id=0)) == bytes(
        signing_request_power.get_pubkey_from_id(id=0)
    )
    assert bytes(signing_request_power.get_pubkey_from_id(id=0)) != bytes(
        signing_request_power.get_pubkey_from_id(id=1)
    )


@pytest.mark.parametrize(
    "signature_request_fixture",
    ["user_op_signature_request", "packed_user_op_signature_request"],
)
def test_signing_request_power_decrypt_encrypted_request(
    signing_request_power, signature_request_fixture, request
):
    signature_request = request.getfixturevalue(signature_request_fixture)

    requester_sk = SessionStaticSecret.random()
    requester_public_key = requester_sk.public_key()

    # derive shared secret and encrypt the request (mimicking requester behavior)
    shared_secret = requester_sk.derive_shared_secret(
        signing_request_power.get_pubkey_from_id(signature_request.cohort_id)
    )
    encrypted_request = signature_request.encrypt(shared_secret, requester_public_key)
    assert isinstance(encrypted_request, EncryptedThresholdSignatureRequest)

    # ensure the node can decrypt it
    decrypted_request = signing_request_power.decrypt_encrypted_request(
        encrypted_request
    )
    assert bytes(decrypted_request) == bytes(signature_request)


def test_signing_request_power_failed_to_decrypt_encrypted_request(
    signing_request_power, mocker
):
    encrypted_request = mocker.Mock(EncryptedThresholdSignatureRequest)
    encrypted_request.requester_public_key = mocker.PropertyMock(
        SessionStaticSecret.random().public_key()
    )
    encrypted_request.cohort_id = 3
    encrypted_request.decrypt.side_effect = ValueError("Decryption failed")
    # failed decryption
    with pytest.raises(SigningRequestPower.ThresholdRequestDecryptionFailed):
        signing_request_power.decrypt_encrypted_request(encrypted_request)


def test_signing_request_power_encrypt_signature_response():
    threshold_signing_power = ThresholdSigningPower()
    message = b"Victory fades, but character lasts a lifetime"  # -- Anonymous
    message_hash, signature = threshold_signing_power.sign_message_eip191(message)
    signature_response = SignatureResponse(
        hash=message_hash,
        signature=signature,
        signature_type=0,
        signer=threshold_signing_power.account,
    )

    cohort_id = 5

    session_secret_factory = SessionSecretFactory.random()
    signing_request_power = SigningRequestPower(
        session_secret_factory=session_secret_factory
    )
    requester_sk = SessionStaticSecret.random()
    requester_public_key = requester_sk.public_key()

    # node returns encrypted response
    encrypted_response = signing_request_power.encrypt_signature_response(
        signature_response=signature_response,
        requester_public_key=requester_public_key,
        cohort_id=cohort_id,
    )
    assert isinstance(encrypted_response, EncryptedThresholdSignatureResponse)

    # derive shared secret and decrypt the response (mimicking requester behavior)
    shared_secret = requester_sk.derive_shared_secret(
        signing_request_power.get_pubkey_from_id(cohort_id)
    )
    decrypted_response = encrypted_response.decrypt(shared_secret=shared_secret)
    assert bytes(decrypted_response) == bytes(signature_response)
    assert decrypted_response.hash == signature_response.hash
    assert decrypted_response.signature == signature_response.signature
    assert decrypted_response.signature_type == signature_response.signature_type
    assert decrypted_response.signer == signature_response.signer


def test_signing_request_power_failed_to_encrypt_decryption_response(
    signing_request_power, mocker
):
    signature_response = mocker.Mock(SignatureResponse)
    signature_response.encrypt.side_effect = ValueError("Encryption failed")
    # failed encryption
    with pytest.raises(SigningRequestPower.ThresholdResponseEncryptionFailed):
        signing_request_power.encrypt_signature_response(
            signature_response=signature_response,
            requester_public_key=SessionStaticSecret.random().public_key(),
            cohort_id=4,
        )
