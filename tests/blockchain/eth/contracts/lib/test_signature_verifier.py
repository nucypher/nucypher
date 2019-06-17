"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""


import os

import pytest
from cryptography.hazmat.backends.openssl import backend
from cryptography.hazmat.primitives import hashes
from eth_tester.exceptions import TransactionFailed
from eth_utils import to_normalized_address

from umbral.keys import UmbralPrivateKey
from umbral.signing import Signer

from nucypher.crypto.api import keccak_digest
from nucypher.crypto.utils import get_signature_recovery_value

ALGORITHM_KECCAK256 = 0
ALGORITHM_SHA256 = 1
ALGORITHM_RIPEMD160 = 2


@pytest.fixture()
def signature_verifier(testerchain):
    contract, _ = testerchain.deploy_contract('SignatureVerifierMock')
    return contract


@pytest.mark.slow
def test_recover(testerchain, signature_verifier):
    message = os.urandom(100)

    # Prepare message hash
    hash_ctx = hashes.Hash(hashes.SHA256(), backend=backend)
    hash_ctx.update(message)
    message_hash = hash_ctx.finalize()

    # Generate Umbral key and extract "address" from the public key
    umbral_privkey = UmbralPrivateKey.gen_key()
    umbral_pubkey = umbral_privkey.get_pubkey()
    umbral_pubkey_bytes = umbral_privkey.get_pubkey().to_bytes(is_compressed=False)
    signer_address = keccak_digest(umbral_pubkey_bytes[1:])
    signer_address = to_normalized_address(signer_address[12:])

    # Sign message
    signer = Signer(umbral_privkey)
    signature = signer(message)

    # Get recovery id (v) before using contract
    # If we don't have recovery id while signing then we should try to recover public key with different v
    # Only the correct v will match the correct public key
    v = get_signature_recovery_value(message, signature, umbral_pubkey)
    recoverable_signature = bytes(signature) + v

    # Check recovery method in the contract
    assert signer_address == to_normalized_address(
        signature_verifier.functions.recover(message_hash, recoverable_signature).call())

    # Also numbers 27 and 28 can be used for v
    recoverable_signature = recoverable_signature[:-1] + bytes([recoverable_signature[-1] + 27])
    assert signer_address == to_normalized_address(
        signature_verifier.functions.recover(message_hash, recoverable_signature).call())

    # Only number 0,1,27,28 are supported for v
    recoverable_signature = bytes(signature) + bytes([2])
    with pytest.raises((TransactionFailed, ValueError)):
        signature_verifier.functions.recover(message_hash, recoverable_signature).call()

    # Signature must include r, s and v
    recoverable_signature = bytes(signature)
    with pytest.raises((TransactionFailed, ValueError)):
        signature_verifier.functions.recover(message_hash, recoverable_signature).call()


@pytest.mark.slow
def test_address(testerchain, signature_verifier):
    # Generate Umbral key and extract "address" from the public key
    umbral_privkey = UmbralPrivateKey.gen_key()
    umbral_pubkey = umbral_privkey.get_pubkey()
    umbral_pubkey_bytes = umbral_pubkey.to_bytes(is_compressed=False)[1:]
    signer_address = keccak_digest(umbral_pubkey_bytes)
    signer_address = to_normalized_address(signer_address[12:])

    # Check extracting address in library
    result_address = signature_verifier.functions.toAddress(umbral_pubkey_bytes).call()
    assert signer_address == to_normalized_address(result_address)


@pytest.mark.slow
def test_hash(testerchain, signature_verifier):
    message = os.urandom(100)

    # Prepare message hash
    hash_ctx = hashes.Hash(hashes.SHA256(), backend=backend)
    hash_ctx.update(message)
    message_hash = hash_ctx.finalize()

    # Verify hash function
    assert message_hash == signature_verifier.functions.hash(message, ALGORITHM_SHA256).call()


@pytest.mark.slow
def test_verify(testerchain, signature_verifier):
    message = os.urandom(100)

    # Generate Umbral key
    umbral_privkey = UmbralPrivateKey.gen_key()
    umbral_pubkey = umbral_privkey.get_pubkey()
    umbral_pubkey_bytes = umbral_pubkey.to_bytes(is_compressed=False)

    # Sign message using SHA-256 hash
    signer = Signer(umbral_privkey)
    signature = signer(message)

    # Get recovery id (v) before using contract
    v = get_signature_recovery_value(message, signature, umbral_pubkey)
    recoverable_signature = bytes(signature) + v

    # Verify signature
    assert signature_verifier.functions.verify(message,
                                               recoverable_signature,
                                               umbral_pubkey_bytes[1:],
                                               ALGORITHM_SHA256).call()

    # Verify signature using wrong key
    umbral_privkey = UmbralPrivateKey.gen_key()
    umbral_pubkey_bytes = umbral_privkey.get_pubkey().to_bytes(is_compressed=False)
    assert not signature_verifier.functions.verify(message,
                                                   recoverable_signature,
                                                   umbral_pubkey_bytes[1:],
                                                   ALGORITHM_SHA256).call()
