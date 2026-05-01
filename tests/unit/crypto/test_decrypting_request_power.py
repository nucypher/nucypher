import pytest
from nucypher_core import (
    EncryptedThresholdDecryptionRequest,
    EncryptedThresholdDecryptionResponse,
    SessionSecretFactory,
    SessionStaticSecret,
    ThresholdDecryptionRequest,
    ThresholdDecryptionResponse,
)
from nucypher_core.ferveo import FerveoVariant

from nucypher.blockchain.eth.signers import InMemorySigner
from nucypher.characters.lawful import Enrico
from nucypher.crypto.powers import DecryptingRequestPower
from nucypher.policy.conditions.lingo import ConditionLingo


@pytest.fixture(scope="module")
def decrypting_request_power():
    session_secret_factory = SessionSecretFactory.random()
    return DecryptingRequestPower(session_secret_factory=session_secret_factory)


def test_decrypting_request_power_public_key_derivation(decrypting_request_power):
    assert bytes(decrypting_request_power.get_pubkey_from_id(id=0)) == bytes(
        decrypting_request_power.get_pubkey_from_id(id=0)
    )
    assert bytes(decrypting_request_power.get_pubkey_from_id(id=0)) != bytes(
        decrypting_request_power.get_pubkey_from_id(id=1)
    )


def test_decrypting_request_power_decrypt_encrypted_request(
    decrypting_request_power, dkg_public_key, time_condition, mocker
):
    # create enrico
    enrico = Enrico(encrypting_key=dkg_public_key, signer=InMemorySigner())

    plaintext = b"Democracy is the worst form of government except for all those other forms that have been tried from time to time"  # -- Unknown via Winston Churchill

    # encrypt
    threshold_message_kit = enrico.encrypt_for_dkg(
        plaintext=plaintext, conditions=ConditionLingo(time_condition).to_dict()
    )

    ritual_id = 144

    decryption_request = ThresholdDecryptionRequest(
        ritual_id=ritual_id,
        variant=FerveoVariant.Simple,
        ciphertext_header=threshold_message_kit.ciphertext_header,
        acp=threshold_message_kit.acp,
        context=None,
    )

    requester_sk = SessionStaticSecret.random()
    requester_public_key = requester_sk.public_key()

    # derive shared secret and encrypt the request (mimicking requester behavior)
    shared_secret = requester_sk.derive_shared_secret(
        decrypting_request_power.get_pubkey_from_id(decryption_request.ritual_id)
    )
    encrypted_request = decryption_request.encrypt(shared_secret, requester_public_key)
    assert isinstance(encrypted_request, EncryptedThresholdDecryptionRequest)

    # ensure the node can decrypt it
    decrypted_request = decrypting_request_power.decrypt_encrypted_request(
        encrypted_request
    )
    assert bytes(decrypted_request) == bytes(decryption_request)


def test_decrypting_request_power_failed_to_decrypt_encrypted_request(
    decrypting_request_power, mocker
):
    encrypted_request = mocker.Mock(EncryptedThresholdDecryptionRequest)
    encrypted_request.requester_public_key = mocker.PropertyMock(
        SessionStaticSecret.random().public_key()
    )
    encrypted_request.ritual_id = 1
    encrypted_request.decrypt.side_effect = ValueError("Decryption failed")
    # failed decryption
    with pytest.raises(DecryptingRequestPower.ThresholdRequestDecryptionFailed):
        decrypting_request_power.decrypt_encrypted_request(encrypted_request)


def test_decrypting_request_power_encrypt_decryption_response(decrypting_request_power):
    ritual_id = 144
    decryption_response = ThresholdDecryptionResponse(
        ritual_id=ritual_id, decryption_share=b"decryption_share"
    )
    requester_sk = SessionStaticSecret.random()
    requester_public_key = requester_sk.public_key()

    # node returns encrypted response
    encrypted_response = decrypting_request_power.encrypt_decryption_response(
        decryption_response=decryption_response,
        requester_public_key=requester_public_key,
    )
    assert isinstance(encrypted_response, EncryptedThresholdDecryptionResponse)

    # derive shared secret and decrypt the response (mimicking requester behavior)
    shared_secret = requester_sk.derive_shared_secret(
        decrypting_request_power.get_pubkey_from_id(ritual_id)
    )
    decrypted_decryption_response = encrypted_response.decrypt(
        shared_secret=shared_secret
    )
    assert bytes(decrypted_decryption_response) == bytes(decryption_response)
    assert (
        decrypted_decryption_response.decryption_share
        == decryption_response.decryption_share
    )
    assert decrypted_decryption_response.ritual_id == decryption_response.ritual_id


def test_decrypting_request_power_failed_to_encrypt_decryption_response(
    decrypting_request_power, mocker
):
    decryption_response = mocker.Mock(ThresholdDecryptionResponse)
    decryption_response.ritual_id = 1
    decryption_response.encrypt.side_effect = ValueError("Encryption failed")
    # failed encryption
    with pytest.raises(DecryptingRequestPower.ThresholdResponseEncryptionFailed):
        decrypting_request_power.encrypt_decryption_response(
            decryption_response,
            requester_public_key=SessionStaticSecret.random().public_key(),
        )
