import random

import pytest
from eth_account.messages import defunct_hash_message, encode_defunct
from web3 import Web3

from nucypher.policy.conditions.auth.evm import EIP1271Auth

COHORT_SIZE = 4
COHORT_THRESHOLD = 2


@pytest.fixture
def signing_cohort(ursulas):
    cohort = ursulas[:COHORT_SIZE]
    sorted_cohort = sorted(cohort, key=lambda ursula: ursula.operator_address)
    return sorted_cohort


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

    # sorted random sample from cohort
    cohort_sample = sorted(
        random.sample(signing_cohort, COHORT_THRESHOLD),
        key=lambda ursula: ursula.operator_address,
    )
    for ursula in cohort_sample:
        operator_account = accounts[ursula.operator_address]
        message_signature = operator_account.sign_message(signable_message)
        signature_bytes = message_signature.encode_rsv()
        received_signatures.append(signature_bytes)

    # call method that takes individual signatures
    message_hash = defunct_hash_message(text=data)
    assert (
        multisig_contract_wallet.isValidSignatures(message_hash, received_signatures)
        == EIP1271Auth.MAGIC_VALUE_BYTES
    )

    # call method that takes aggregate signatures (concatenated)
    aggregated_signatures = b"".join(received_signatures)
    assert (
        multisig_contract_wallet.isValidSignature(message_hash, aggregated_signatures)
        == EIP1271Auth.MAGIC_VALUE_BYTES
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

    # sorted random sample from cohort
    cohort_sample = sorted(
        random.sample(signing_cohort, COHORT_THRESHOLD),
        key=lambda ursula: ursula.operator_address,
    )
    for ursula in cohort_sample:
        operator_account = accounts[ursula.operator_address]
        message_signature = operator_account.sign_raw_msghash(tx_hash)
        signature_bytes = message_signature.encode_rsv()
        received_signatures.append(signature_bytes)

    multisig_contract_wallet.execute(
        receiver.address, eth_amount, b"", received_signatures, sender=deployer_account
    )

    assert receiver.balance == receiver_balance + eth_amount
    assert multisig_contract_wallet.balance == contract_balance - eth_amount
