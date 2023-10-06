from unittest.mock import ANY

import pytest
from cryptography.hazmat.primitives.serialization import Encoding
from flask import Flask
from nucypher_core import (
    SessionStaticSecret,
    ThresholdDecryptionRequest,
    ThresholdDecryptionResponse,
)
from nucypher_core.umbral import SecretKey, Signer

from nucypher.blockchain.eth.signers.software import Web3Signer
from nucypher.characters.lawful import Alice, Bob, Enrico, Ursula
from nucypher.config.constants import TEMPORARY_DOMAIN
from nucypher.crypto.ferveo.dkg import FerveoVariant
from nucypher.crypto.keystore import Keystore
from nucypher.crypto.powers import (
    DecryptingPower,
    DelegatingPower,
    ThresholdRequestDecryptingPower,
    TLSHostingPower,
)
from nucypher.network.server import ProxyRESTServer
from nucypher.policy.conditions.lingo import ConditionLingo
from nucypher.policy.payment import SubscriptionManagerPayment
from nucypher.utilities.networking import LOOPBACK_ADDRESS
from tests.constants import (
    INSECURE_DEVELOPMENT_PASSWORD,
    MOCK_ETH_PROVIDER_URI,
    TESTERCHAIN_CHAIN_ID,
)
from tests.utils.matchers import IsType


def test_generate_alice_keystore(temp_dir_path):

    keystore = Keystore.generate(
        password=INSECURE_DEVELOPMENT_PASSWORD,
        keystore_dir=temp_dir_path
    )

    with pytest.raises(Keystore.Locked):
        _dec_keypair = keystore.derive_crypto_power(DecryptingPower).keypair

    keystore.unlock(password=INSECURE_DEVELOPMENT_PASSWORD)
    assert keystore.derive_crypto_power(DecryptingPower).keypair

    label = b'test'

    delegating_power = keystore.derive_crypto_power(DelegatingPower)
    delegating_pubkey = delegating_power.get_pubkey_from_label(label)

    bob_pubkey = SecretKey.random().public_key()
    signer = Signer(SecretKey.random())
    delegating_pubkey_again, _kfrags = delegating_power.generate_kfrags(
        bob_pubkey, signer, label, threshold=2, shares=3
    )

    assert delegating_pubkey == delegating_pubkey_again

    another_delegating_power = keystore.derive_crypto_power(DelegatingPower)
    another_delegating_pubkey = another_delegating_power.get_pubkey_from_label(label)

    assert delegating_pubkey == another_delegating_pubkey


@pytest.mark.usefixtures("mock_registry_sources")
def test_characters_use_keystore(temp_dir_path, testerchain):
    keystore = Keystore.generate(
        password=INSECURE_DEVELOPMENT_PASSWORD,
        keystore_dir=temp_dir_path
    )
    keystore.unlock(password=INSECURE_DEVELOPMENT_PASSWORD)

    pre_payment_method = SubscriptionManagerPayment(
        blockchain_endpoint=MOCK_ETH_PROVIDER_URI, domain=TEMPORARY_DOMAIN
    )

    alice = Alice(
        start_learning_now=False,
        keystore=keystore,
        domain=TEMPORARY_DOMAIN,
        eth_endpoint=MOCK_ETH_PROVIDER_URI,
        polygon_endpoint=MOCK_ETH_PROVIDER_URI,
        checksum_address=testerchain.alice_account,
        pre_payment_method=pre_payment_method,
    )
    Bob(
        eth_endpoint=MOCK_ETH_PROVIDER_URI,
        start_learning_now=False,
        keystore=keystore,
        domain=TEMPORARY_DOMAIN,
    )
    Ursula(
        eth_endpoint=MOCK_ETH_PROVIDER_URI,
        polygon_endpoint=MOCK_ETH_PROVIDER_URI,
        start_learning_now=False,
        keystore=keystore,
        rest_host=LOOPBACK_ADDRESS,
        rest_port=12345,
        domain=TEMPORARY_DOMAIN,
        pre_payment_method=pre_payment_method,
        operator_address=testerchain.ursulas_accounts[0],
        signer=Web3Signer(testerchain.client),
    )
    alice.disenchant()  # To stop Alice's publication threadpool.  TODO: Maybe only start it at first enactment?


@pytest.mark.skip('Do we really though?')
def test_tls_hosting_certificate_remains_the_same(temp_dir_path, mocker):
    keystore = Keystore.generate(
        password=INSECURE_DEVELOPMENT_PASSWORD,
        keystore_dir=temp_dir_path
    )
    keystore.unlock(password=INSECURE_DEVELOPMENT_PASSWORD)

    rest_port = 12345

    ursula = Ursula(
        start_learning_now=False,
        keystore=keystore,
        rest_host=LOOPBACK_ADDRESS,
        rest_port=rest_port,
        domain=TEMPORARY_DOMAIN,
    )

    assert ursula.keystore is keystore
    assert ursula.certificate == ursula._crypto_power.power_ups(TLSHostingPower).keypair.certificate

    original_certificate_bytes = ursula.certificate.public_bytes(encoding=Encoding.DER)
    ursula.disenchant()
    del ursula

    spy_rest_server_init = mocker.spy(ProxyRESTServer, "__init__")
    recreated_ursula = Ursula(
        start_learning_now=False,
        keystore=keystore,
        rest_host=LOOPBACK_ADDRESS,
        rest_port=rest_port,
        domain=TEMPORARY_DOMAIN,
    )

    assert recreated_ursula.keystore is keystore
    assert recreated_ursula.certificate.public_bytes(encoding=Encoding.DER) == original_certificate_bytes
    tls_hosting_power = recreated_ursula._crypto_power.power_ups(TLSHostingPower)
    spy_rest_server_init.assert_called_once_with(ANY,  # self
                                                 rest_host=LOOPBACK_ADDRESS,
                                                 rest_port=rest_port,
                                                 rest_app=IsType(Flask),
                                                 hosting_power=tls_hosting_power)
    recreated_ursula.disenchant()


@pytest.mark.usefixtures("mock_sign_message")
def test_ritualist(temp_dir_path, testerchain, dkg_public_key):
    keystore = Keystore.generate(
        password=INSECURE_DEVELOPMENT_PASSWORD, keystore_dir=temp_dir_path
    )
    keystore.unlock(password=INSECURE_DEVELOPMENT_PASSWORD)

    pre_payment_method = SubscriptionManagerPayment(
        blockchain_endpoint=MOCK_ETH_PROVIDER_URI, domain=TEMPORARY_DOMAIN
    )

    ursula = Ursula(
        start_learning_now=False,
        keystore=keystore,
        rest_host=LOOPBACK_ADDRESS,
        rest_port=12345,
        domain=TEMPORARY_DOMAIN,
        pre_payment_method=pre_payment_method,
        operator_address=testerchain.ursulas_accounts[0],
        signer=Web3Signer(testerchain.client),
        eth_endpoint=MOCK_ETH_PROVIDER_URI,
        polygon_endpoint=MOCK_ETH_PROVIDER_URI,
    )

    ritual_id = 23
    # Use actual decryption request
    plaintext = b"Records break when you don't"  # Jordan branch ad tagline
    CONDITIONS = {
        "version": ConditionLingo.VERSION,
        "condition": {
            "conditionType": "time",
            "returnValueTest": {"value": "0", "comparator": ">"},
            "method": "blocktime",
            "chain": TESTERCHAIN_CHAIN_ID,
        },
    }

    # create enrico
    signer = Web3Signer(client=testerchain.client)
    enrico = Enrico(encrypting_key=dkg_public_key, signer=signer)

    # encrypt
    threshold_message_kit = enrico.encrypt_for_dkg(
        plaintext=plaintext, conditions=CONDITIONS
    )

    decryption_request = ThresholdDecryptionRequest(
        ritual_id=ritual_id,
        variant=FerveoVariant.Simple,
        ciphertext_header=threshold_message_kit.ciphertext_header,
        acp=threshold_message_kit.acp,
    )

    #
    # test requester sends encrypted decryption request
    #
    ursula_request_public_key = (
        ursula.threshold_request_power.get_pubkey_from_ritual_id(ritual_id=ritual_id)
    )

    requester_sk = SessionStaticSecret.random()
    requester_public_key = requester_sk.public_key()
    shared_secret = requester_sk.derive_shared_secret(ursula_request_public_key)
    encrypted_decryption_request = decryption_request.encrypt(
        shared_secret=shared_secret,
        requester_public_key=requester_public_key,
    )
    # successful decryption
    decrypted_decryption_request = (
        ursula.threshold_request_power.decrypt_encrypted_request(
            encrypted_decryption_request
        )
    )
    assert bytes(decrypted_decryption_request) == bytes(decryption_request)

    # failed encryption - incorrect encrypting key used
    invalid_encrypted_decryption_request = decryption_request.encrypt(
        shared_secret=SessionStaticSecret.random().derive_shared_secret(
            ursula_request_public_key
        ),
        requester_public_key=requester_public_key,
    )
    with pytest.raises(
        ThresholdRequestDecryptingPower.ThresholdRequestDecryptionFailed
    ):
        ursula.threshold_request_power.decrypt_encrypted_request(
            invalid_encrypted_decryption_request
        )
    #
    # test ursula sends encrypted response based on request
    #
    decryption_response = ThresholdDecryptionResponse(
        ritual_id=ritual_id, decryption_share=b"decryption_share"
    )
    encrypted_decryption_response = (
        ursula.threshold_request_power.encrypt_decryption_response(
            decryption_response=decryption_response,
            requester_public_key=requester_public_key,
        )
    )
    # successful decryption
    decrypted_decryption_response = encrypted_decryption_response.decrypt(shared_secret)
    assert bytes(decrypted_decryption_response) == bytes(decryption_response)

    # failed encryption - incorrect decrypting key used
    with pytest.raises(
        ThresholdRequestDecryptingPower.ThresholdResponseEncryptionFailed
    ):
        ursula.threshold_request_power.encrypt_decryption_response(
            decryption_response=decryption_response,
            # incorrect use of Umbral key here
            requester_public_key=SecretKey.random().public_key(),
        )
