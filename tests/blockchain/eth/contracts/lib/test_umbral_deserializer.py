import os

import pytest
from eth_tester.exceptions import TransactionFailed

from umbral import pre, keys
from umbral.signing import Signer


@pytest.fixture()
def deserializer(testerchain):
    contract, _ = testerchain.interface.deploy_contract('UmbralDeserializerMock')
    return contract


@pytest.fixture()
def fragments():
    delegating_privkey = keys.UmbralPrivateKey.gen_key()
    _symmetric_key, capsule = pre._encapsulate(delegating_privkey.get_pubkey())
    signing_privkey = keys.UmbralPrivateKey.gen_key()
    signer = Signer(signing_privkey)
    priv_key_bob = keys.UmbralPrivateKey.gen_key()
    pub_key_bob = priv_key_bob.get_pubkey()
    kfrags = pre.generate_kfrags(delegating_privkey=delegating_privkey,
                                 signer=signer,
                                 receiving_pubkey=pub_key_bob,
                                 threshold=2,
                                 N=4,
                                 sign_delegating_key=True,
                                 sign_receiving_key=True)
    metadata = b"This is an example of metadata for re-encryption request"
    capsule.set_correctness_keys(delegating_privkey.get_pubkey(), pub_key_bob, signing_privkey.get_pubkey())
    cfrag = pre.reencrypt(kfrags[0], capsule, metadata=metadata)
    return capsule, cfrag


@pytest.mark.slow
def test_capsule(testerchain, deserializer, fragments):
    # Wrong number of bytes to deserialize capsule
    with pytest.raises((TransactionFailed, ValueError)):
        deserializer.functions.toCapsule(os.urandom(97)).call()
    with pytest.raises((TransactionFailed, ValueError)):
        deserializer.functions.toCapsule(os.urandom(99)).call()

    # Check random capsule bytes
    capsule_bytes = os.urandom(98)
    result = deserializer.functions.toCapsule(capsule_bytes).call()
    assert capsule_bytes == bytes().join(bytes(item) for item in result)

    # Check real capsule
    capsule, _cfrag = fragments
    capsule_bytes = capsule.to_bytes()
    result = deserializer.functions.toCapsule(capsule_bytes).call()
    assert bytes(capsule._point_e) == result[0] + result[1]
    assert bytes(capsule._point_v) == result[2] + result[3]
    assert capsule._bn_sig.to_bytes() == bytes(result[4])


@pytest.mark.slow
def test_proof(testerchain, deserializer, fragments):
    # Wrong number of bytes to deserialize proof
    with pytest.raises((TransactionFailed, ValueError)):
        deserializer.functions.toCorrectnessProof(os.urandom(227)).call()

    # Check random proof bytes without metadata
    proof_bytes = os.urandom(228)
    result = deserializer.functions.toCorrectnessProof(proof_bytes).call()
    assert proof_bytes == bytes().join(result)

    # Check random proof bytes with metadata
    proof_bytes = os.urandom(270)
    result = deserializer.functions.toCorrectnessProof(proof_bytes).call()
    assert proof_bytes == bytes().join(result)

    # Get real cfrag and proof
    _capsule, cfrag = fragments
    proof = cfrag.proof
    proof_bytes = proof.to_bytes()

    # Check real proof
    result = deserializer.functions.toCorrectnessProof(proof_bytes).call()
    assert bytes(proof._point_e2) == result[0] + result[1]
    assert bytes(proof._point_v2) == result[2] + result[3]
    assert bytes(proof._point_kfrag_commitment) == result[4] + result[5]
    assert bytes(proof._point_kfrag_pok) == result[6] + result[7]
    assert proof.bn_sig.to_bytes() == result[8]
    assert bytes(proof.kfrag_signature) == result[9]
    assert bytes(proof.metadata) == result[10]


@pytest.mark.slow
def test_cfrag(testerchain, deserializer, fragments):
    # Wrong number of bytes to deserialize cfrag
    with pytest.raises((TransactionFailed, ValueError)):
        deserializer.functions.toCapsuleFrag(os.urandom(358)).call()

    # Check random cfrag bytes
    cfrag_bytes = os.urandom(131)
    proof_bytes = os.urandom(228)
    full_cfrag_bytes = cfrag_bytes + proof_bytes
    result = deserializer.functions.toCapsuleFrag(full_cfrag_bytes).call()
    assert cfrag_bytes == bytes().join(result)
    result = deserializer.functions.toCorrectnessProofFromCapsuleFrag(full_cfrag_bytes).call()
    assert proof_bytes == bytes().join(result)

    # Check real cfrag
    _capsule, cfrag = fragments
    proof = cfrag.proof
    cfrag_bytes = cfrag.to_bytes()
    result = deserializer.functions.toCapsuleFrag(cfrag_bytes).call()
    assert bytes(cfrag._point_e1) == result[0] + result[1]
    assert bytes(cfrag._point_v1) == result[2] + result[3]
    assert bytes(cfrag._kfrag_id) == result[4]
    assert bytes(cfrag._point_precursor) == result[5] + result[6]
    result = deserializer.functions.toCorrectnessProofFromCapsuleFrag(cfrag_bytes).call()
    assert bytes(proof._point_e2) == result[0] + result[1]
    assert bytes(proof._point_v2) == result[2] + result[3]
    assert bytes(proof._point_kfrag_commitment) == result[4] + result[5]
    assert bytes(proof._point_kfrag_pok) == result[6] + result[7]
    assert proof.bn_sig.to_bytes() == result[8]
    assert bytes(proof.kfrag_signature) == result[9]
    assert bytes(proof.metadata) == result[10]
