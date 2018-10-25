import os

import coincurve
import pytest
from cryptography.hazmat.backends.openssl import backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from eth_tester.exceptions import TransactionFailed
from eth_utils import to_canonical_address

from umbral.keys import UmbralPrivateKey
from umbral.signing import Signature


def sign_data(data, umbral_privkey):
    umbral_pubkey_bytes = umbral_privkey.get_pubkey().to_bytes(is_compressed=False)

    # Prepare hash of the data
    hash_ctx = hashes.Hash(hashes.SHA256(), backend=backend)
    hash_ctx.update(data)
    data_hash = hash_ctx.finalize()

    # Sign data and calculate recoverable signature
    cryptography_priv_key = umbral_privkey.to_cryptography_privkey()
    signature_der_bytes = cryptography_priv_key.sign(data, ec.ECDSA(hashes.SHA256()))
    signature = Signature.from_bytes(signature_der_bytes, der_encoded=True)
    recoverable_signature = bytes(signature) + bytes([0])
    pubkey_bytes = coincurve.PublicKey.from_signature_and_message(recoverable_signature, data_hash, hasher=None) \
        .format(compressed=False)
    if pubkey_bytes != umbral_pubkey_bytes:
        recoverable_signature = bytes(signature) + bytes([1])
    return data_hash, recoverable_signature


@pytest.mark.slow
def test_challenge_cfrag(testerchain, escrow, challenge_contract):
    creator, miner, wrong_miner, *everyone_else = testerchain.interface.w3.eth.accounts

    # Prepare one miner
    tx = escrow.functions.setMinerInfo(miner, 1000).transact()
    testerchain.wait_for_receipt(tx)

    # Generate miner's Umbral key
    umbral_privkey = UmbralPrivateKey.gen_key()
    umbral_pubkey_bytes = umbral_privkey.get_pubkey().to_bytes(is_compressed=False)

    # Sign Umbral public key using eth-key
    hash_ctx = hashes.Hash(hashes.SHA256(), backend=backend)
    hash_ctx.update(umbral_pubkey_bytes)
    umbral_pubkey_hash = hash_ctx.finalize()
    provider = testerchain.interface.providers[0]
    address = to_canonical_address(miner)
    sig_key = provider.ethereum_tester.backend._key_lookup[address]
    signed_umbral_pubkey = bytes(sig_key.sign_msg_hash(umbral_pubkey_hash))

    # Prepare hash of the data
    capsule = os.urandom(100)
    cfrag = os.urandom(100)
    data = capsule + cfrag
    data_hash, recoverable_signature = sign_data(data, umbral_privkey)

    # Challenge using good data
    assert not challenge_contract.functions.challengedCFrags(data_hash).call()
    tx = challenge_contract.functions.challengeCFrag(
        capsule, cfrag, recoverable_signature, umbral_pubkey_bytes, signed_umbral_pubkey).transact()
    testerchain.wait_for_receipt(tx)
    # Hash of the data is saved and miner is not slashed
    assert challenge_contract.functions.challengedCFrags(data_hash).call()
    assert 1000 == escrow.functions.minerInfo(miner).call()

    # Can't challenge miner with data that already was checked
    with pytest.raises((TransactionFailed, ValueError)):
        tx = challenge_contract.functions.challengeCFrag(
            capsule, cfrag, recoverable_signature, umbral_pubkey_bytes, signed_umbral_pubkey).transact()
        testerchain.wait_for_receipt(tx)

    # Challenge using bad data
    cfrag = os.urandom(101)
    data = capsule + cfrag
    data_hash, recoverable_signature = sign_data(data, umbral_privkey)
    assert not challenge_contract.functions.challengedCFrags(data_hash).call()
    tx = challenge_contract.functions.challengeCFrag(
        capsule, cfrag, recoverable_signature, umbral_pubkey_bytes, signed_umbral_pubkey).transact()
    testerchain.wait_for_receipt(tx)
    # Hash of the data is saved and miner is slashed
    assert challenge_contract.functions.challengedCFrags(data_hash).call()
    assert 900 == escrow.functions.minerInfo(miner).call()

    # Prepare hash of the data
    capsule = os.urandom(100)
    cfrag = os.urandom(100)
    data = capsule + cfrag
    data_hash, recoverable_signature = sign_data(data, umbral_privkey)

    # Can't challenge miner using broken signatures
    with pytest.raises((TransactionFailed, ValueError)):
        tx = challenge_contract.functions.challengeCFrag(
            capsule, cfrag, recoverable_signature[1:], umbral_pubkey_bytes, signed_umbral_pubkey).transact()
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = challenge_contract.functions.challengeCFrag(
            capsule, cfrag, recoverable_signature, umbral_pubkey_bytes, signed_umbral_pubkey[1:]).transact()
        testerchain.wait_for_receipt(tx)

    # Can't use signature for another data
    wrong_capsule = os.urandom(100)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = challenge_contract.functions.challengeCFrag(
            wrong_capsule, cfrag, recoverable_signature, umbral_pubkey_bytes, signed_umbral_pubkey).transact()
        testerchain.wait_for_receipt(tx)

    # Can't challenge nonexistent miner
    address = to_canonical_address(wrong_miner)
    sig_key = provider.ethereum_tester.backend._key_lookup[address]
    signed_umbral_pubkey = bytes(sig_key.sign_msg_hash(umbral_pubkey_hash))
    with pytest.raises((TransactionFailed, ValueError)):
        tx = challenge_contract.functions.challengeCFrag(
            capsule, cfrag, recoverable_signature, umbral_pubkey_bytes, signed_umbral_pubkey).transact()
        testerchain.wait_for_receipt(tx)
