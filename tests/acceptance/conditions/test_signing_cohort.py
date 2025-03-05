import os
import random

import pytest
from ape.exceptions import ContractLogicError
from eth_account.messages import defunct_hash_message, encode_defunct
from web3 import Web3

from nucypher.policy.conditions.auth.evm import EIP1271Auth

COHORT_SIZE = 4
COHORT_THRESHOLD = 2


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


@pytest.fixture
def signing_cohort(ursulas):
    cohort = ursulas[:COHORT_SIZE]
    return cohort


@pytest.fixture
def multisig_contract_wallet(project, deployer_account, signing_cohort):
    owners = [ursula.operator_address for ursula in signing_cohort]
    _multisig_contract_wallet = deployer_account.deploy(
        project.ThresholdSigningMultisig, owners, COHORT_THRESHOLD
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

    # should fail
    with pytest.raises(ContractLogicError):
        multisig_contract_wallet.execute(
            receiver.address,
            eth_amount,
            b"",
            os.urandom(len(aggregated_signature)),
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
        message_hash, received_signatures, sender=deployer_account
    )

    assert (
        multisig_contract_wallet.isValidSignature(message_hash, aggregated_signatures)
        == EIP1271Auth.MAGIC_VALUE_BYTES
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
        message_hash, received_signatures, sender=deployer_account
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

    # signature is ignored since old signature was saved
    # TODO: is this correct?
    assert (
        multisig_contract_wallet.isValidSignature(
            message_hash, os.urandom(len(aggregated_signatures))
        )
        == EIP1271Auth.MAGIC_VALUE_BYTES
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
