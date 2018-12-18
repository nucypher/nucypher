"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""
import os

import coincurve
import pytest
from cryptography.hazmat.backends.openssl import backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from eth_tester.exceptions import TransactionFailed
from eth_utils import to_canonical_address
from umbral import pre

from umbral.keys import UmbralPrivateKey
from umbral.signing import Signature, Signer


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
    recoverable_signature = make_recoverable_signature(data_hash, signature, umbral_pubkey_bytes)
    return recoverable_signature


def make_recoverable_signature(data_hash, signature, umbral_pubkey_bytes):
    recoverable_signature = bytes(signature) + bytes([0])
    pubkey_bytes = coincurve.PublicKey.from_signature_and_message(recoverable_signature, data_hash, hasher=None) \
        .format(compressed=False)
    if pubkey_bytes != umbral_pubkey_bytes:
        recoverable_signature = bytes(signature) + bytes([1])
    return recoverable_signature


def fragments(metadata):
    delegating_privkey = UmbralPrivateKey.gen_key()
    _symmetric_key, capsule = pre._encapsulate(delegating_privkey.get_pubkey())
    signing_privkey = UmbralPrivateKey.gen_key()
    signer = Signer(signing_privkey)
    priv_key_bob = UmbralPrivateKey.gen_key()
    pub_key_bob = priv_key_bob.get_pubkey()
    kfrags = pre.generate_kfrags(delegating_privkey=delegating_privkey,
                                 signer=signer,
                                 receiving_pubkey=pub_key_bob,
                                 threshold=2,
                                 N=4,
                                 sign_delegating_key=True,
                                 sign_receiving_key=True)
    capsule.set_correctness_keys(delegating_privkey.get_pubkey(), pub_key_bob, signing_privkey.get_pubkey())
    cfrag = pre.reencrypt(kfrags[0], capsule, metadata=metadata)
    return capsule, cfrag


@pytest.mark.slow
def test_challenge_cfrag(testerchain, escrow, challenge_contract):
    creator, miner, wrong_miner, *everyone_else = testerchain.interface.w3.eth.accounts

    # Prepare one miner
    tx = escrow.functions.setMinerInfo(miner, 1000).transact()
    testerchain.wait_for_receipt(tx)

    # Generate miner's Umbral key
    miner_umbral_private_key = UmbralPrivateKey.gen_key()
    miner_umbral_public_key_bytes = miner_umbral_private_key.get_pubkey().to_bytes(is_compressed=False)

    # Sign Umbral public key using eth-key
    hash_ctx = hashes.Hash(hashes.SHA256(), backend=backend)
    hash_ctx.update(miner_umbral_public_key_bytes)
    miner_umbral_public_key_hash = hash_ctx.finalize()
    provider = testerchain.interface.providers[0]
    address = to_canonical_address(miner)
    sig_key = provider.ethereum_tester.backend._key_lookup[address]
    signed_miner_umbral_public_key = bytes(sig_key.sign_msg_hash(miner_umbral_public_key_hash))

    # Prepare hash of the data
    metadata = os.urandom(33)
    some_data = os.urandom(22)
    capsule, cfrag = fragments(metadata)
    capsule_bytes = capsule.to_bytes()
    cfrag_bytes = cfrag.to_bytes()
    hash_ctx = hashes.Hash(hashes.SHA256(), backend=backend)
    hash_ctx.update(capsule_bytes + cfrag_bytes)
    data_hash = hash_ctx.finalize()
    # This capsule and cFrag are not yet challenged
    assert not challenge_contract.functions.challengedCFrags(data_hash).call()

    # Generate requester's Umbral key
    requester_umbral_private_key = UmbralPrivateKey.gen_key()
    requester_umbral_public_key_bytes = requester_umbral_private_key.get_pubkey().to_bytes(is_compressed=False)

    # Sign capsule and cFrag
    capsule_signature_by_requester = sign_data(capsule_bytes, requester_umbral_private_key)
    capsule_signature_by_requester_and_miner = sign_data(capsule_signature_by_requester, miner_umbral_private_key)
    cfrag_signature_by_miner = sign_data(cfrag_bytes, miner_umbral_private_key)

    # Challenge using good data
    args = (capsule_bytes,
            capsule_signature_by_requester,
            capsule_signature_by_requester_and_miner,
            cfrag_bytes,
            cfrag_signature_by_miner,
            requester_umbral_public_key_bytes,
            miner_umbral_public_key_bytes,
            signed_miner_umbral_public_key,
            some_data)
    tx = challenge_contract.functions.challengeCFrag(*args).transact()
    testerchain.wait_for_receipt(tx)
    # Hash of the data is saved and miner was not slashed
    assert challenge_contract.functions.challengedCFrags(data_hash).call()
    assert 1000 == escrow.functions.minerInfo(miner).call()

    # Can't challenge miner with data that already was checked
    with pytest.raises((TransactionFailed, ValueError)):
        tx = challenge_contract.functions.challengeCFrag(*args).transact()
        testerchain.wait_for_receipt(tx)

    # Challenge using bad data
    metadata = os.urandom(34)
    capsule, cfrag = fragments(metadata)
    capsule_bytes = capsule.to_bytes()
    cfrag_bytes = cfrag.to_bytes()
    hash_ctx = hashes.Hash(hashes.SHA256(), backend=backend)
    hash_ctx.update(capsule_bytes + cfrag_bytes)
    data_hash = hash_ctx.finalize()
    capsule_signature_by_requester = sign_data(capsule_bytes, requester_umbral_private_key)
    capsule_signature_by_requester_and_miner = sign_data(capsule_signature_by_requester, miner_umbral_private_key)
    cfrag_signature_by_miner = sign_data(cfrag_bytes, miner_umbral_private_key)
    args = (capsule_bytes,
            capsule_signature_by_requester,
            capsule_signature_by_requester_and_miner,
            cfrag_bytes,
            cfrag_signature_by_miner,
            requester_umbral_public_key_bytes,
            miner_umbral_public_key_bytes,
            signed_miner_umbral_public_key,
            some_data)

    assert not challenge_contract.functions.challengedCFrags(data_hash).call()
    tx = challenge_contract.functions.challengeCFrag(*args).transact()
    testerchain.wait_for_receipt(tx)
    # Hash of the data is saved and miner was slashed
    assert challenge_contract.functions.challengedCFrags(data_hash).call()
    assert 900 == escrow.functions.minerInfo(miner).call()

    # Prepare hash of the data
    metadata = os.urandom(34)
    capsule, cfrag = fragments(metadata)
    capsule_bytes = capsule.to_bytes()
    cfrag_bytes = cfrag.to_bytes()
    hash_ctx = hashes.Hash(hashes.SHA256(), backend=backend)
    hash_ctx.update(capsule_bytes + cfrag_bytes)
    data_hash = hash_ctx.finalize()
    capsule_signature_by_requester = sign_data(capsule_bytes, requester_umbral_private_key)
    capsule_signature_by_requester_and_miner = sign_data(capsule_signature_by_requester, miner_umbral_private_key)
    cfrag_signature_by_miner = sign_data(cfrag_bytes, miner_umbral_private_key)
    args = [capsule_bytes,
            capsule_signature_by_requester,
            capsule_signature_by_requester_and_miner,
            cfrag_bytes,
            cfrag_signature_by_miner,
            requester_umbral_public_key_bytes,
            miner_umbral_public_key_bytes,
            signed_miner_umbral_public_key,
            some_data]
    assert not challenge_contract.functions.challengedCFrags(data_hash).call()

    # Can't challenge miner using broken signatures
    wrong_args = args[:]
    wrong_args[1] = capsule_signature_by_requester[1:]
    with pytest.raises((TransactionFailed, ValueError)):
        tx = challenge_contract.functions.challengeCFrag(*wrong_args).transact()
        testerchain.wait_for_receipt(tx)
    wrong_args = args[:]
    wrong_args[2] = capsule_signature_by_requester_and_miner[1:]
    with pytest.raises((TransactionFailed, ValueError)):
        tx = challenge_contract.functions.challengeCFrag(*wrong_args).transact()
        testerchain.wait_for_receipt(tx)
    wrong_args = args[:]
    wrong_args[4] = cfrag_signature_by_miner[1:]
    with pytest.raises((TransactionFailed, ValueError)):
        tx = challenge_contract.functions.challengeCFrag(*wrong_args).transact()
        testerchain.wait_for_receipt(tx)
    wrong_args = args[:]
    wrong_args[7] = signed_miner_umbral_public_key[1:]
    with pytest.raises((TransactionFailed, ValueError)):
        tx = challenge_contract.functions.challengeCFrag(*wrong_args).transact()
        testerchain.wait_for_receipt(tx)

    # Can't challenge miner using wrong keys
    wrong_args = args[:]
    wrong_args[5] = UmbralPrivateKey.gen_key().get_pubkey().to_bytes(is_compressed=False)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = challenge_contract.functions.challengeCFrag(*wrong_args).transact()
        testerchain.wait_for_receipt(tx)
    wrong_args = args[:]
    wrong_args[6] = UmbralPrivateKey.gen_key().get_pubkey().to_bytes(is_compressed=False)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = challenge_contract.functions.challengeCFrag(*wrong_args).transact()
        testerchain.wait_for_receipt(tx)

    # Can't use signature for another data
    wrong_args = args[:]
    wrong_args[0] = bytes(args[0][0] + 1) + args[0][1:]
    with pytest.raises((TransactionFailed, ValueError)):
        tx = challenge_contract.functions.challengeCFrag(*wrong_args).transact()
        testerchain.wait_for_receipt(tx)
    wrong_args = args[:]
    wrong_args[3] = bytes(args[3][0] + 1) + args[3][1:]
    with pytest.raises((TransactionFailed, ValueError)):
        tx = challenge_contract.functions.challengeCFrag(*wrong_args).transact()
        testerchain.wait_for_receipt(tx)

    # Can't challenge nonexistent miner
    address = to_canonical_address(wrong_miner)
    sig_key = provider.ethereum_tester.backend._key_lookup[address]
    signed_miner_umbral_public_key = bytes(sig_key.sign_msg_hash(miner_umbral_public_key_hash))
    wrong_args = args[:]
    wrong_args[7] = signed_miner_umbral_public_key
    with pytest.raises((TransactionFailed, ValueError)):
        tx = challenge_contract.functions.challengeCFrag(*wrong_args).transact()
        testerchain.wait_for_receipt(tx)

    # Initial arguments were correct
    assert not challenge_contract.functions.challengedCFrags(data_hash).call()
    tx = challenge_contract.functions.challengeCFrag(*args).transact()
    testerchain.wait_for_receipt(tx)
    assert challenge_contract.functions.challengedCFrags(data_hash).call()
    assert 800 == escrow.functions.minerInfo(miner).call()
