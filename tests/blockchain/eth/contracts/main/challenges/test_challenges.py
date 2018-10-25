import os

import coincurve
import pytest
from eth_tester.exceptions import TransactionFailed
from eth_utils import to_canonical_address
from umbral import pre, keys

from umbral.keys import UmbralPrivateKey
from cryptography.hazmat.backends.openssl import backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from umbral.signing import Signature, Signer
from itertools import chain


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


@pytest.mark.slow
def test_serialization(testerchain):
    contract, _ = testerchain.interface.deploy_contract('SerializationLibraryMock')

    capsule_bytes = os.urandom(98)
    result = contract.functions.toOriginalCapsule(capsule_bytes).call()
    assert capsule_bytes == bytes().join(result)

    delegating_privkey = keys.UmbralPrivateKey.gen_key()
    # params = delegating_privkey.params
    _symmetric_key, capsule = pre._encapsulate(delegating_privkey.get_pubkey())
    capsule_bytes = capsule.to_bytes()
    result = contract.functions.toOriginalCapsule(capsule_bytes).call()
    assert bytes(capsule._point_e) == result[0]
    assert bytes(capsule._point_v) == result[1]
    assert capsule._bn_sig.to_bytes() == result[2]

    proof_bytes = os.urandom(228)
    result = contract.functions.toCorrectnessProof(proof_bytes).call()
    assert proof_bytes == bytes().join(result)

    proof_bytes = os.urandom(270)
    result = contract.functions.toCorrectnessProof(proof_bytes).call()
    assert proof_bytes == bytes().join(result)

    signing_privkey = keys.UmbralPrivateKey.gen_key()
    signer = Signer(signing_privkey)

    priv_key_bob = keys.UmbralPrivateKey.gen_key()
    pub_key_bob = priv_key_bob.get_pubkey()

    kfrags = pre.split_rekey(delegating_privkey, signer, pub_key_bob, 1, 2)
    metadata = b"This is an example of metadata for re-encryption request"

    cfrag = pre.reencrypt(kfrags[0], capsule, metadata=metadata)
    proof = cfrag.proof
    proof_bytes = proof.to_bytes()

    result = contract.functions.toCorrectnessProof(proof_bytes).call()
    assert bytes(proof._point_e2) == result[0]
    assert bytes(proof._point_v2) == result[1]
    assert bytes(proof._point_kfrag_commitment) == result[2]
    assert bytes(proof._point_kfrag_pok) == result[3]
    assert proof.bn_sig.to_bytes() == result[4]
    assert bytes(proof.kfrag_signature) == result[5]
    assert bytes(proof.metadata) == result[6]

    cfrag_bytes = os.urandom(164)
    full_cfrag_bytes = cfrag_bytes + proof_bytes
    result = contract.functions.toCapsuleFrag(full_cfrag_bytes).call()
    assert cfrag_bytes == bytes().join(result)
    result = contract.functions.toCorrectnessProofFromCapsuleFrag(full_cfrag_bytes).call()
    assert proof_bytes == bytes().join(result)

    cfrag_bytes = cfrag.to_bytes()
    result = contract.functions.toCapsuleFrag(cfrag_bytes).call()
    assert bytes(cfrag._point_e1) == result[0]
    assert bytes(cfrag._point_v1) == result[1]
    assert bytes(cfrag._kfrag_id) == result[2]
    assert bytes(cfrag._point_noninteractive) == result[3]
    assert bytes(cfrag._point_xcoord) == result[4]
    result = contract.functions.toCorrectnessProofFromCapsuleFrag(cfrag_bytes).call()
    assert bytes(proof._point_e2) == result[0]
    assert bytes(proof._point_v2) == result[1]
    assert bytes(proof._point_kfrag_commitment) == result[2]
    assert bytes(proof._point_kfrag_pok) == result[3]
    assert proof.bn_sig.to_bytes() == result[4]
    assert bytes(proof.kfrag_signature) == result[5]
    assert bytes(proof.metadata) == result[6]
