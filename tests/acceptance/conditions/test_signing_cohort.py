import calendar
import json
import os
import random
import uuid
from datetime import datetime, timezone
from typing import Tuple

import jwt
import maya
import pytest
from ape.exceptions import ContractLogicError
from cryptography.hazmat.primitives import serialization
from ecdsa import SECP256k1, SigningKey, VerifyingKey
from eth_account.messages import defunct_hash_message, encode_defunct
from eth_keys.datatypes import PrivateKey
from eth_utils import keccak, to_checksum_address
from hexbytes import HexBytes
from jwcrypto.jwk import JWK
from py_ecc.secp256k1 import secp256k1
from py_ecc.secp256k1.secp256k1 import bytes_to_int
from web3 import Web3

from nucypher.policy.conditions.auth.evm import EIP1271Auth

COHORT_SIZE = 5
COHORT_THRESHOLD = 3


def ursula_sign_data(accounts, ursula, signable_message):
    operator_account = accounts[ursula.operator_address]
    message_signature = operator_account.sign_message(signable_message)
    signature_bytes = message_signature.encode_rsv()
    return signature_bytes


def ursula_sign_raw_hash(accounts, ursula, raw_hash: bytes):
    operator_account = accounts[ursula.operator_address]
    message_signature = operator_account.sign_raw_msghash(raw_hash)
    signature_bytes = message_signature.encode_rsv()
    return signature_bytes


def ursula_generate_vrf_randomness(accounts, ursula, message):
    #
    # To clarify, this is not a real vrf implementation, but a simple mock
    #
    private_key = PrivateKey(
        bytes(HexBytes(accounts[ursula.operator_address].private_key))
    )
    message_scalar = bytes_to_int(message) % secp256k1.N

    randomness = secp256k1.multiply(secp256k1.G, message_scalar)
    proof = secp256k1.multiply(randomness, bytes_to_int(private_key.to_bytes()))

    return randomness, proof


def get_pem_key_pair(private_key_bytes) -> Tuple[str, str]:
    # Load the private key from bytes
    private_key = SigningKey.from_string(private_key_bytes, curve=SECP256k1)

    # Generate the corresponding public key
    public_key = private_key.get_verifying_key()

    return public_key.to_pem().decode(), private_key.to_pem().decode()


def signer_address_from_public_pem(pem_public_key):
    public_key = VerifyingKey.from_pem(pem_public_key)
    public_key_bytes = public_key.to_string(encoding="uncompressed")

    return signer_address_from_uncompressed_bytes(public_key_bytes)


def signer_address_from_uncompressed_bytes(uncompressed_bytes):
    # Drop the first byte (0x04) which is the prefix for uncompressed keys
    public_key_raw = uncompressed_bytes[1:]

    # Compute Keccak-256 hash of the public key
    address_hash = keccak(public_key_raw)

    # Take the last 20 bytes to form the Ethereum address
    eth_address = to_checksum_address("0x" + address_hash[-20:].hex())
    return eth_address


def point_to_bytes(point):
    return point[0].to_bytes(32, "big") + point[1].to_bytes(32, "big")


@pytest.fixture
def signing_cohort(ursulas):
    cohort = ursulas[:COHORT_SIZE]
    return cohort


@pytest.fixture
def multisig_contract_wallet(project, deployer_account, signing_cohort):
    owners = [ursula.operator_address for ursula in signing_cohort]
    _multisig_contract_wallet = deployer_account.deploy(
        project.ThresholdSigningCohortMultisig
    )
    _multisig_contract_wallet.initialize(
        owners, COHORT_THRESHOLD, deployer_account.address, sender=deployer_account
    )

    # transfer some funds into smart contract wallet
    eth_amount = Web3.to_wei(10, "ether")
    encoded_deposit_function = _multisig_contract_wallet.deposit.encode_input().hex()
    deployer_account.transfer(
        account=_multisig_contract_wallet.address,
        value=eth_amount,
        data=encoded_deposit_function,
    )

    return _multisig_contract_wallet


def test_simple_data_message_signing(
    multisig_contract_wallet, accounts, signing_cohort, deployer_account
):
    data = "Labor omnia vincit improbus."
    signable_message = encode_defunct(text=data)

    received_signatures = []

    # random sample from cohort
    cohort_sample = random.sample(signing_cohort, COHORT_THRESHOLD)
    for ursula in cohort_sample:
        signature_bytes = ursula_sign_data(accounts, ursula, signable_message)
        received_signatures.append(signature_bytes)

    message_hash = defunct_hash_message(text=data)
    aggregated_signatures = b"".join(received_signatures)

    assert (
        multisig_contract_wallet.isValidSignature(message_hash, aggregated_signatures)
        == EIP1271Auth.MAGIC_VALUE_BYTES
    )

    # invalid signature bytes
    assert (
        multisig_contract_wallet.isValidSignature(
            message_hash, os.urandom(len(aggregated_signatures))
        )
        != EIP1271Auth.MAGIC_VALUE_BYTES
    )


def test_simple_tx_signing(
    multisig_contract_wallet, accounts, signing_cohort, deployer_account
):
    receiver = accounts[accounts.unassigned_accounts[0]]
    receiver_balance = receiver.balance

    contract_balance = multisig_contract_wallet.balance

    # send some ETH from the smart contract wallet to the receiver
    eth_amount = Web3.to_wei(2.25, "ether")

    tx_hash = multisig_contract_wallet.getUnsignedTransactionHash(
        deployer_account.address,
        receiver.address,
        eth_amount,
        b"",
        multisig_contract_wallet.nonce,
    )
    received_signatures = []

    # use random sample from cohort for signing
    cohort_sample = random.sample(signing_cohort, COHORT_THRESHOLD)
    for ursula in cohort_sample:
        signature_bytes = ursula_sign_raw_hash(accounts, ursula, tx_hash)
        received_signatures.append(signature_bytes)

    aggregated_signature = b"".join(received_signatures)

    # should fail - invalid signature
    with pytest.raises(ContractLogicError):
        multisig_contract_wallet.execute(
            receiver.address,
            eth_amount,
            b"",
            os.urandom(len(aggregated_signature)),
            sender=deployer_account,
        )
    # (t-1) signatures are valid but the last signature is invalid -> still invalid
    signature_size = len(received_signatures[0])
    not_full_valid_signature = aggregated_signature[:-signature_size] + os.urandom(
        signature_size
    )
    with pytest.raises(ContractLogicError):
        multisig_contract_wallet.execute(
            receiver.address,
            eth_amount,
            b"",
            not_full_valid_signature,
            sender=deployer_account,
        )

    multisig_contract_wallet.execute(
        receiver.address, eth_amount, b"", aggregated_signature, sender=deployer_account
    )

    assert receiver.balance == receiver_balance + eth_amount
    assert multisig_contract_wallet.balance == contract_balance - eth_amount


def test_saved_data_message_signing(
    multisig_contract_wallet, accounts, signing_cohort, deployer_account
):
    data = "Labor omnia vincit improbus."
    signable_message = encode_defunct(text=data)

    received_signatures = []

    # random sample from cohort
    cohort_sample = random.sample(signing_cohort, COHORT_THRESHOLD)

    for ursula in cohort_sample:
        signature_bytes = ursula_sign_data(accounts, ursula, signable_message)
        received_signatures.append(signature_bytes)

    message_hash = defunct_hash_message(text=data)

    aggregated_signatures = b"".join(received_signatures)

    # invalid signature
    assert (
        multisig_contract_wallet.isValidSignature(
            message_hash, os.urandom(len(aggregated_signatures))
        )
        != EIP1271Auth.MAGIC_VALUE_BYTES
    )

    assert (
        multisig_contract_wallet.isValidSignature(message_hash, aggregated_signatures)
        == EIP1271Auth.MAGIC_VALUE_BYTES
    )

    # save signatures
    multisig_contract_wallet.saveSignature(
        message_hash, aggregated_signatures, sender=deployer_account
    )

    assert (
        multisig_contract_wallet.isValidSignature(message_hash, aggregated_signatures)
        == EIP1271Auth.MAGIC_VALUE_BYTES
    )

    # still invalid if incorrect signature provided for cached message
    assert (
        multisig_contract_wallet.isValidSignature(
            message_hash, os.urandom(len(aggregated_signatures))
        )
        != EIP1271Auth.MAGIC_VALUE_BYTES
    )


def test_cohort_handover(
    multisig_contract_wallet, accounts, signing_cohort, deployer_account, ursulas
):
    data = "Labor omnia vincit improbus."
    signable_message = encode_defunct(text=data)

    received_signatures = []

    # random sample from cohort
    cohort_sample = random.sample(signing_cohort, COHORT_THRESHOLD)

    for ursula in cohort_sample:
        signature_bytes = ursula_sign_data(accounts, ursula, signable_message)
        received_signatures.append(signature_bytes)

    # call method that takes individual signatures
    message_hash = defunct_hash_message(text=data)
    aggregated_signatures = b"".join(received_signatures)

    # save signatures
    multisig_contract_wallet.saveSignature(
        message_hash, aggregated_signatures, sender=deployer_account
    )

    assert (
        multisig_contract_wallet.isValidSignature(message_hash, aggregated_signatures)
        == EIP1271Auth.MAGIC_VALUE_BYTES
    )
    assert multisig_contract_wallet.getSigners() == [
        ursula.operator_address for ursula in signing_cohort
    ]

    # handover to new cohort
    new_cohort = ursulas[COHORT_SIZE : COHORT_SIZE * 2]
    for i, new_signer in enumerate(new_cohort):
        multisig_contract_wallet.replaceSigner(
            signing_cohort[i].operator_address,
            new_signer.operator_address,
            sender=deployer_account,
        )

    # check updated signers
    assert sorted(multisig_contract_wallet.getSigners()) == sorted(
        [ursula.operator_address for ursula in new_cohort]
    )

    # check old saved signature
    assert (
        multisig_contract_wallet.isValidSignature(message_hash, aggregated_signatures)
        == EIP1271Auth.MAGIC_VALUE_BYTES
    )

    # signature not ignored since old signature was saved
    assert (
        multisig_contract_wallet.isValidSignature(
            message_hash, os.urandom(len(aggregated_signatures))
        )
        != EIP1271Auth.MAGIC_VALUE_BYTES
    )

    new_data = "Labor omnia vincit."
    new_signable_message = encode_defunct(text=new_data)
    new_message_hash = defunct_hash_message(text=new_data)

    # old signers can't sign anything new
    old_cohort_new_signatures = []
    for ursula in signing_cohort:
        signature_bytes = ursula_sign_data(accounts, ursula, new_signable_message)
        old_cohort_new_signatures.append(signature_bytes)
    assert (
        multisig_contract_wallet.isValidSignature(
            new_message_hash, b"".join(old_cohort_new_signatures)
        )
        != EIP1271Auth.MAGIC_VALUE_BYTES
    )

    # new signers can sign
    new_signatures = []
    new_cohort_sample = random.sample(new_cohort, COHORT_THRESHOLD)
    for ursula in new_cohort_sample:
        signature_bytes = ursula_sign_data(accounts, ursula, new_signable_message)
        new_signatures.append(signature_bytes)

    assert (
        multisig_contract_wallet.isValidSignature(
            new_message_hash, b"".join(new_signatures)
        )
        == EIP1271Auth.MAGIC_VALUE_BYTES
    )


def test_on_chain_random_number_generation(
    deployer_account, multisig_contract_wallet, signing_cohort, accounts
):
    random_numbers = set()
    numbers_to_generate = 3

    for i in range(numbers_to_generate):
        receipt = multisig_contract_wallet.requestRandomNumber(sender=deployer_account)
        assert receipt.events[0]["requester"] == deployer_account.address

        request_hash = receipt.events[0]["requestHash"]

        cohort_sample = random.sample(signing_cohort, COHORT_THRESHOLD)
        for ursula in cohort_sample:
            randomness, proof = ursula_generate_vrf_randomness(
                accounts, ursula, request_hash
            )
            multisig_contract_wallet.submitRandomness(
                request_hash,
                point_to_bytes(randomness),
                point_to_bytes(proof),
                sender=accounts[ursula.operator_address],
            )

        # random number should now be generated
        random_number = int(multisig_contract_wallet.getRandomNumber(request_hash))
        random_number_second_call = multisig_contract_wallet.getRandomNumber(
            request_hash
        )
        assert random_number == random_number_second_call
        random_numbers.add(random_number)

    assert len(random_numbers) == numbers_to_generate, "random numbers are unique"


def test_on_chain_token_issuance(
    deployer_account, multisig_contract_wallet, signing_cohort, accounts
):
    delegatee = accounts.unassigned_accounts[0]
    one_hour_from_now = maya.now().add(hours=1).epoch
    token_data = {
        "sub": delegatee,
        "exp": one_hour_from_now,
        "permissions": ["read_data"],
    }
    token_data_str = json.dumps(token_data)

    receipt = multisig_contract_wallet.requestTokenIssuance(
        token_data_str, sender=deployer_account
    )
    request_hash = receipt.events[0]["requestHash"]

    # submit signatures
    aggregated_signature = b""
    cohort_sample = random.sample(signing_cohort, COHORT_THRESHOLD)
    for ursula in cohort_sample:
        signature_bytes = ursula_sign_raw_hash(accounts, ursula, request_hash)
        multisig_contract_wallet.approveTokenIssuance(
            request_hash, signature_bytes, sender=accounts[ursula.operator_address]
        )
        aggregated_signature += signature_bytes

    # token should now be valid
    assert multisig_contract_wallet.verifyOnChainTokenSignature(
        token_data_str, aggregated_signature
    )


def test_jwt_issuance(
    deployer_account, multisig_contract_wallet, signing_cohort, accounts
):
    delegatee = accounts.unassigned_accounts[0]
    token_payload = {
        "exp": calendar.timegm(datetime.now(tz=timezone.utc).utctimetuple()) + 60 * 60,
        "iat": calendar.timegm(datetime.now(tz=timezone.utc).utctimetuple()),
        "subject": delegatee,
        "permissions": ["read_data"],
        "verification": {
            "signingCohortId": str(uuid.uuid4()),  # some id - doesn't really matter
            # include list of signers, and threshold in payload
            # (ursulas will validate these values before signing)
            "allowedSigners": [ursula.operator_address for ursula in signing_cohort],
            "threshold": COHORT_THRESHOLD,
        },
    }
    token_payload_str = json.dumps(token_payload, separators=(",", ":"))
    # match b64 encoding done by library
    token_payload_b64 = jwt.utils.base64url_encode(token_payload_str.encode()).decode()

    # match b64 encoding done by library
    # collect signatures off-chain (node REST call_
    jws_json = {
        "payload": token_payload_b64,
        "signatures": [],
    }

    #
    # Node Signing (node endpoint calls and aggregation by caller)
    #
    cohort_sample = random.sample(signing_cohort, COHORT_THRESHOLD)
    for ursula in cohort_sample:
        # ursulas would check before signing:
        # - check that allowedSigners is correct for cohort ID
        # - check that threshold is correct for cohort ID
        # - check member of cohort based on cohort ID
        # - the contract for policies determine whether to sign or not
        # ...
        # For example
        # check allowed signers
        assert set(token_payload["verification"]["allowedSigners"]) == set(
            multisig_contract_wallet.getSigners()
        )
        # check threshold
        assert (
            token_payload["verification"]["threshold"]
            == multisig_contract_wallet.threshold()
        )
        # (Skip other checks and go straight to signing)

        pem_public_key, pem_private_key = get_pem_key_pair(
            bytes(HexBytes(accounts[ursula.operator_address].private_key))
        )

        jwt_token = jwt.encode(
            payload=token_payload, key=pem_private_key, algorithm="ES256K"
        )
        protected, payload_64, signature = jwt_token.split(".")

        # Purely for testing purposes - but the payload_64 should always be the same for all signers
        # already set, ensure consistency
        assert jws_json["payload"] == payload_64

        # to be returned from node
        # TODO used the jwcrypto library just to generate this JWK in a dictionary form from pem
        signing_key = JWK.from_pem(pem_private_key.encode())
        verifying_jwk = signing_key.export_public(
            as_dict=True
        )  # public key in dict form

        result = {
            "protected": protected,
            "header": {
                "jwk": verifying_jwk
            },  # include public verifying key in unprotected header
            "signature": signature,
        }

        # aggregated by caller
        jws_json["signatures"].append(result)

    #
    # JWS Verification (local with no calls to contract)
    #
    num_verifications = 0
    prev_payload = None
    for i, sig in enumerate(jws_json["signatures"]):
        header_b64 = sig["protected"]
        signature_b64 = sig["signature"]
        header_jwk = jwt.PyJWK.from_dict(sig["header"]["jwk"])

        jwt_token = f"{header_b64}.{jws_json['payload']}.{signature_b64}"
        jwt_payload = jwt.decode(jwt_token, key=header_jwk)

        if prev_payload:
            # same payload for all signers
            assert jwt_payload == prev_payload
        else:
            prev_payload = jwt_payload

        # verify signer address
        raw_bytes = header_jwk.key.public_bytes(
            encoding=serialization.Encoding.X962,
            format=serialization.PublicFormat.UncompressedPoint,
        )
        signer_address = signer_address_from_uncompressed_bytes(raw_bytes)
        assert signer_address in set(jwt_payload["verification"]["allowedSigners"])

        num_verifications += 1
        if num_verifications >= jwt_payload["verification"]["threshold"]:
            break

    assert num_verifications == COHORT_THRESHOLD
