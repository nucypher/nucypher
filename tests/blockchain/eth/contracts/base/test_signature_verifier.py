import os

import coincurve
import pytest
from cryptography.hazmat.backends.openssl import backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from eth_tester.exceptions import TransactionFailed
from eth_utils import to_normalized_address

from umbral.keys import UmbralPrivateKey
from umbral.signing import Signature


def test_recover(testerchain):
    contract, _ = testerchain.interface.deploy_contract('SignatureVerifierMock')
    message = os.urandom(100)

    # Prepare message hash
    hash_ctx = hashes.Hash(hashes.SHA256(), backend=backend)
    hash_ctx.update(message)
    message_hash = hash_ctx.finalize()

    # Generate Umbral key and extract "address" from the public key
    umbral_privkey = UmbralPrivateKey.gen_key()
    umbral_pubkey_bytes = umbral_privkey.get_pubkey().to_bytes(is_compressed=False)
    signer_address = bytearray(testerchain.interface.w3.soliditySha3(['bytes32'], [umbral_pubkey_bytes[1:]]))
    signer_address = to_normalized_address(signer_address[12:])

    # Sign message using SHA-256 hash (because only 32 bytes hash can be used in the `ecrecover` method)
    cryptography_priv_key = umbral_privkey.to_cryptography_privkey()
    signature_der_bytes = cryptography_priv_key.sign(message, ec.ECDSA(hashes.SHA256()))
    signature = Signature.from_bytes(signature_der_bytes, der_encoded=True)

    # Get recovery id (v) before using contract
    # If we don't have recovery id while signing than we should try to recover public key with different v
    # Only the correct v will match the correct public key
    # First try v = 0
    recoverable_signature = bytes(signature) + bytes([0])
    pubkey_bytes = coincurve.PublicKey.from_signature_and_message(recoverable_signature, message_hash, hasher=None)\
        .format(compressed=False)
    if pubkey_bytes != umbral_pubkey_bytes:
        # Extracted public key is not ours, that means v = 1
        recoverable_signature = bytes(signature) + bytes([1])
        pubkey_bytes = coincurve.PublicKey.from_signature_and_message(recoverable_signature, message_hash, hasher=None)\
            .format(compressed=False)

    # Check that recovery was ok
    assert umbral_pubkey_bytes == pubkey_bytes
    # Check recovery method in the contract
    assert signer_address == to_normalized_address(
        contract.functions.recover(message_hash, recoverable_signature).call())

    # Also numbers 27 and 28 can be used for v
    recoverable_signature = recoverable_signature[0:-1] + bytes([recoverable_signature[-1] + 27])
    assert signer_address == to_normalized_address(
        contract.functions.recover(message_hash, recoverable_signature).call())

    # Only number 0,1,27,28 are supported for v
    recoverable_signature = bytes(signature) + bytes([2])
    with pytest.raises((TransactionFailed, ValueError)):
        contract.functions.recover(message_hash, recoverable_signature).call()

    # Signature must include r, s and v
    recoverable_signature = bytes(signature)
    with pytest.raises((TransactionFailed, ValueError)):
        contract.functions.recover(message_hash, recoverable_signature).call()
