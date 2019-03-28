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

import coincurve
import pytest
from cryptography.hazmat.backends.openssl import backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from eth_tester.exceptions import TransactionFailed
from eth_utils import to_canonical_address, to_checksum_address
from typing import Tuple
from web3.contract import Contract

from umbral import pre
from umbral.config import default_params
from umbral.curvebn import CurveBN
from umbral.keys import UmbralPrivateKey
from umbral.point import Point
from umbral.random_oracles import hash_to_curvebn, ExtendedKeccak
from umbral.signing import Signature, Signer

from nucypher.policy.models import IndisputableEvidence


ALGORITHM_KECCAK256 = 0
ALGORITHM_SHA256 = 1
BASE_PENALTY = 100
PENALTY_HISTORY_COEFFICIENT = 10
PERCENTAGE_PENALTY_COEFFICIENT = 8
REWARD_COEFFICIENT = 2
secret = (123456).to_bytes(32, byteorder='big')
secret2 = (654321).to_bytes(32, byteorder='big')


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


# TODO: Obtain real re-encryption metadata. Maybe constructing a WorkOrder and obtaining a response.
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
                                 sign_delegating_key=False,
                                 sign_receiving_key=False)
    capsule.set_correctness_keys(delegating_privkey.get_pubkey(), pub_key_bob, signing_privkey.get_pubkey())
    cfrag = pre.reencrypt(kfrags[0], capsule, metadata=metadata)
    return capsule, cfrag


def compute_penalty_and_reward(stake: int, penalty_history: int) -> Tuple[int, int]:
    penalty = BASE_PENALTY + PENALTY_HISTORY_COEFFICIENT * penalty_history
    penalty = min(penalty, stake // PERCENTAGE_PENALTY_COEFFICIENT)
    reward = penalty // REWARD_COEFFICIENT
    return penalty, reward


@pytest.mark.slow
def test_evaluate_cfrag(testerchain, escrow, adjudicator_contract):
    creator, miner, wrong_miner, investigator, *everyone_else = testerchain.interface.w3.eth.accounts
    evaluation_log = adjudicator_contract.events.CFragEvaluated.createFilter(fromBlock='latest')

    worker_stake = 1000
    worker_penalty_history = 0
    investigator_balance = 0
    number_of_evaluations = 0

    # Prepare one miner
    tx = escrow.functions.setMinerInfo(miner, worker_stake).transact()
    testerchain.wait_for_receipt(tx)

    # Generate miner's Umbral key
    miner_umbral_private_key = UmbralPrivateKey.gen_key()
    miner_umbral_public_key_bytes = miner_umbral_private_key.get_pubkey().to_bytes(is_compressed=False)

    # Sign Umbral public key using eth-key
    hash_ctx = hashes.Hash(hashes.SHA256(), backend=backend)
    hash_ctx.update(miner_umbral_public_key_bytes)
    miner_umbral_public_key_hash = hash_ctx.finalize()
    provider = testerchain.interface.provider
    address = to_canonical_address(miner)
    sig_key = provider.ethereum_tester.backend._key_lookup[address]
    signed_miner_umbral_public_key = bytes(sig_key.sign_msg_hash(miner_umbral_public_key_hash))

    # Prepare hash of the data
    metadata = os.urandom(33)
    capsule, cfrag = fragments(metadata)

    assert cfrag.verify_correctness(capsule)

    capsule_bytes = capsule.to_bytes()
    cfrag_bytes = cfrag.to_bytes()

    # Bob prepares supporting Evidence
    evidence = IndisputableEvidence(capsule, cfrag, ursula=None)

    evidence_data = evidence.precompute_values()
    assert len(evidence_data) == 20 * 32 + 32 + 20 + 1

    # This check is a workaround in order to test the signature validation is correct.
    # In reality, this check should be part of the isCapsuleFragCorrect logic,
    # but we're facing with "Stack too deep" errors at the moment.
    # address = adjudicator_contract.functions.aliceAddress(cfrag_bytes, evidence_data).call()
    # assert address == to_checksum_address(evidence_data[-21:-1].hex())

    proof_challenge_scalar = int(evidence.get_proof_challenge_scalar())
    # computeProofChallengeScalar = adjudicator_contract.functions.computeProofChallengeScalar
    # assert proof_challenge_scalar == computeProofChallengeScalar(capsule_bytes, cfrag_bytes).call()

    hash_ctx = hashes.Hash(hashes.SHA256(), backend=backend)
    hash_ctx.update(capsule_bytes + cfrag_bytes)
    data_hash = hash_ctx.finalize()
    # This capsule and cFrag are not yet evaluated
    assert not adjudicator_contract.functions.evaluatedCFrags(data_hash).call()

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
            evidence_data)

    assert worker_stake == escrow.functions.minerInfo(miner).call()[0]

    tx = adjudicator_contract.functions.evaluateCFrag(*args).transact({'from': investigator})
    testerchain.wait_for_receipt(tx)
    number_of_evaluations += 1
    # Hash of the data is saved and miner was not slashed
    assert adjudicator_contract.functions.evaluatedCFrags(data_hash).call()
    assert worker_stake == escrow.functions.minerInfo(miner).call()[0]
    assert investigator_balance == escrow.functions.rewardInfo(investigator).call()

    events = evaluation_log.get_all_entries()
    assert number_of_evaluations == len(events)
    event_args = events[-1]['args']
    assert data_hash == event_args['evaluationHash']
    assert miner == event_args['miner']
    assert investigator == event_args['investigator']
    assert event_args['correctness']

    # Test: Don't evaluate miner with data that already was checked
    with pytest.raises((TransactionFailed, ValueError)):
        tx = adjudicator_contract.functions.evaluateCFrag(*args).transact()
        testerchain.wait_for_receipt(tx)

    # Test: Ursula produces incorrect proof:
    metadata = os.urandom(34)
    capsule, cfrag = fragments(metadata)
    capsule_bytes = capsule.to_bytes()
    # Corrupt proof
    cfrag.proof.bn_sig = CurveBN.gen_rand(capsule.params.curve)
    cfrag_bytes = cfrag.to_bytes()
    assert not cfrag.verify_correctness(capsule)

    hash_ctx = hashes.Hash(hashes.SHA256(), backend=backend)
    hash_ctx.update(capsule_bytes + cfrag_bytes)
    data_hash = hash_ctx.finalize()
    capsule_signature_by_requester = sign_data(capsule_bytes, requester_umbral_private_key)
    capsule_signature_by_requester_and_miner = sign_data(capsule_signature_by_requester, miner_umbral_private_key)
    cfrag_signature_by_miner = sign_data(cfrag_bytes, miner_umbral_private_key)
    evidence = IndisputableEvidence(capsule, cfrag, ursula=None)
    evidence_data = evidence.precompute_values()
    args = (capsule_bytes,
            capsule_signature_by_requester,
            capsule_signature_by_requester_and_miner,
            cfrag_bytes,
            cfrag_signature_by_miner,
            requester_umbral_public_key_bytes,
            miner_umbral_public_key_bytes,
            signed_miner_umbral_public_key,
            evidence_data)

    assert not adjudicator_contract.functions.evaluatedCFrags(data_hash).call()
    tx = adjudicator_contract.functions.evaluateCFrag(*args).transact({'from': investigator})
    testerchain.wait_for_receipt(tx)
    number_of_evaluations += 1

    # Hash of the data is saved and miner was slashed
    assert adjudicator_contract.functions.evaluatedCFrags(data_hash).call()

    penalty, reward = compute_penalty_and_reward(worker_stake, worker_penalty_history)
    worker_stake -= penalty
    investigator_balance += reward
    worker_penalty_history += 1

    assert worker_stake == escrow.functions.minerInfo(miner).call()[0]
    assert investigator_balance == escrow.functions.rewardInfo(investigator).call()

    events = evaluation_log.get_all_entries()
    assert number_of_evaluations == len(events)
    event_args = events[-1]['args']
    assert data_hash == event_args['evaluationHash']
    assert miner == event_args['miner']
    assert investigator == event_args['investigator']
    assert not event_args['correctness']

    ###############################
    # Test: Bob produces wrong precomputed data
    ###############################

    metadata = os.urandom(34)
    capsule, cfrag = fragments(metadata)
    capsule_bytes = capsule.to_bytes()
    cfrag_bytes = cfrag.to_bytes()
    assert cfrag.verify_correctness(capsule)

    hash_ctx = hashes.Hash(hashes.SHA256(), backend=backend)
    hash_ctx.update(capsule_bytes + cfrag_bytes)
    data_hash = hash_ctx.finalize()
    capsule_signature_by_requester = sign_data(capsule_bytes, requester_umbral_private_key)
    capsule_signature_by_requester_and_miner = sign_data(capsule_signature_by_requester, miner_umbral_private_key)
    cfrag_signature_by_miner = sign_data(cfrag_bytes, miner_umbral_private_key)
    evidence = IndisputableEvidence(capsule, cfrag, ursula=None)
    evidence_data = evidence.precompute_values()

    # Bob produces a random point and gets the bytes of coords x and y
    random_point_bytes = Point.gen_rand().to_bytes(is_compressed=False)[1:]
    # He uses this garbage instead of correct precomputation of z*E
    evidence_data = bytearray(evidence_data)
    evidence_data[32:32+64] = random_point_bytes
    evidence_data = bytes(evidence_data)

    args = (capsule_bytes,
            capsule_signature_by_requester,
            capsule_signature_by_requester_and_miner,
            cfrag_bytes,
            cfrag_signature_by_miner,
            requester_umbral_public_key_bytes,
            miner_umbral_public_key_bytes,
            signed_miner_umbral_public_key,
            evidence_data)

    assert not adjudicator_contract.functions.evaluatedCFrags(data_hash).call()

    # Evaluation must fail since Bob precomputed wrong values
    with pytest.raises((TransactionFailed, ValueError)):
        tx = adjudicator_contract.functions.evaluateCFrag(*args).transact({'from': investigator})
        testerchain.wait_for_receipt(tx)

    ###############################
    # Test: Signatures and Metadata mismatch
    ###############################

    # TODO

    ###############################
    # Test: Second violation. Penalty is increased
    ###############################

    # Prepare hash of the data
    metadata = os.urandom(34)
    capsule, cfrag = fragments(metadata)
    capsule_bytes = capsule.to_bytes()
    # Corrupt proof
    cfrag.proof.bn_sig = CurveBN.gen_rand(capsule.params.curve)
    cfrag_bytes = cfrag.to_bytes()
    hash_ctx = hashes.Hash(hashes.SHA256(), backend=backend)
    hash_ctx.update(capsule_bytes + cfrag_bytes)
    data_hash = hash_ctx.finalize()
    capsule_signature_by_requester = sign_data(capsule_bytes, requester_umbral_private_key)
    capsule_signature_by_requester_and_miner = sign_data(capsule_signature_by_requester, miner_umbral_private_key)
    cfrag_signature_by_miner = sign_data(cfrag_bytes, miner_umbral_private_key)
    evidence = IndisputableEvidence(capsule, cfrag, ursula=None)
    evidence_data = evidence.precompute_values()
    args = [capsule_bytes,
            capsule_signature_by_requester,
            capsule_signature_by_requester_and_miner,
            cfrag_bytes,
            cfrag_signature_by_miner,
            requester_umbral_public_key_bytes,
            miner_umbral_public_key_bytes,
            signed_miner_umbral_public_key,
            evidence_data]
    assert not adjudicator_contract.functions.evaluatedCFrags(data_hash).call()

    worker_stake = escrow.functions.minerInfo(miner).call()[0]
    investigator_balance = escrow.functions.rewardInfo(investigator).call()
    assert not adjudicator_contract.functions.evaluatedCFrags(data_hash).call()
    tx = adjudicator_contract.functions.evaluateCFrag(*args).transact({'from': investigator})
    testerchain.wait_for_receipt(tx)
    number_of_evaluations += 1

    assert adjudicator_contract.functions.evaluatedCFrags(data_hash).call()

    previous_penalty = penalty
    penalty, reward = compute_penalty_and_reward(worker_stake, worker_penalty_history)
    # Penalty was increased because it's the second violation
    assert penalty == previous_penalty + PENALTY_HISTORY_COEFFICIENT
    worker_stake -= penalty
    investigator_balance += reward
    worker_penalty_history += 1

    assert worker_stake == escrow.functions.minerInfo(miner).call()[0]
    assert investigator_balance == escrow.functions.rewardInfo(investigator).call()

    events = evaluation_log.get_all_entries()
    assert number_of_evaluations == len(events)
    event_args = events[-1]['args']
    assert data_hash == event_args['evaluationHash']
    assert miner == event_args['miner']
    assert investigator == event_args['investigator']
    assert not event_args['correctness']

    ###############################
    # Test: Third violation. Penalty reaches the maximum allowed
    ###############################

    # Prepare corrupted data again
    capsule, cfrag = fragments(metadata)
    capsule_bytes = capsule.to_bytes()
    # Corrupt proof
    cfrag.proof.bn_sig = CurveBN.gen_rand(capsule.params.curve)
    cfrag_bytes = cfrag.to_bytes()
    hash_ctx = hashes.Hash(hashes.SHA256(), backend=backend)
    hash_ctx.update(capsule_bytes + cfrag_bytes)
    data_hash = hash_ctx.finalize()
    capsule_signature_by_requester = sign_data(capsule_bytes, requester_umbral_private_key)
    capsule_signature_by_requester_and_miner = sign_data(capsule_signature_by_requester, miner_umbral_private_key)
    cfrag_signature_by_miner = sign_data(cfrag_bytes, miner_umbral_private_key)
    evidence = IndisputableEvidence(capsule, cfrag, ursula=None)
    evidence_data = evidence.precompute_values()
    args = [capsule_bytes,
            capsule_signature_by_requester,
            capsule_signature_by_requester_and_miner,
            cfrag_bytes,
            cfrag_signature_by_miner,
            requester_umbral_public_key_bytes,
            miner_umbral_public_key_bytes,
            signed_miner_umbral_public_key,
            evidence_data]

    worker_stake = escrow.functions.minerInfo(miner).call()[0]
    investigator_balance = escrow.functions.rewardInfo(investigator).call()
    assert not adjudicator_contract.functions.evaluatedCFrags(data_hash).call()
    tx = adjudicator_contract.functions.evaluateCFrag(*args).transact({'from': investigator})
    testerchain.wait_for_receipt(tx)
    number_of_evaluations += 1

    assert adjudicator_contract.functions.evaluatedCFrags(data_hash).call()

    penalty, reward = compute_penalty_and_reward(worker_stake, worker_penalty_history)
    # Penalty has reached maximum available percentage of value
    assert penalty == worker_stake // PERCENTAGE_PENALTY_COEFFICIENT
    worker_stake -= penalty
    investigator_balance += reward
    worker_penalty_history += 1

    assert worker_stake == escrow.functions.minerInfo(miner).call()[0]
    assert investigator_balance == escrow.functions.rewardInfo(investigator).call()

    events = evaluation_log.get_all_entries()
    assert number_of_evaluations == len(events)
    event_args = events[-1]['args']
    assert data_hash == event_args['evaluationHash']
    assert miner == event_args['miner']
    assert investigator == event_args['investigator']
    assert not event_args['correctness']

    #################
    # Test: Invalid evaluations
    ##############

    # Can't evaluate miner using broken signatures
    wrong_args = args[:]
    wrong_args[1] = capsule_signature_by_requester[1:]
    with pytest.raises((TransactionFailed, ValueError)):
        tx = adjudicator_contract.functions.evaluateCFrag(*wrong_args).transact()
        testerchain.wait_for_receipt(tx)
    wrong_args = args[:]
    wrong_args[2] = capsule_signature_by_requester_and_miner[1:]
    with pytest.raises((TransactionFailed, ValueError)):
        tx = adjudicator_contract.functions.evaluateCFrag(*wrong_args).transact()
        testerchain.wait_for_receipt(tx)
    wrong_args = args[:]
    wrong_args[4] = cfrag_signature_by_miner[1:]
    with pytest.raises((TransactionFailed, ValueError)):
        tx = adjudicator_contract.functions.evaluateCFrag(*wrong_args).transact()
        testerchain.wait_for_receipt(tx)
    wrong_args = args[:]
    wrong_args[7] = signed_miner_umbral_public_key[1:]
    with pytest.raises((TransactionFailed, ValueError)):
        tx = adjudicator_contract.functions.evaluateCFrag(*wrong_args).transact()
        testerchain.wait_for_receipt(tx)

    # Can't evaluate miner using wrong keys
    wrong_args = args[:]
    wrong_args[5] = UmbralPrivateKey.gen_key().get_pubkey().to_bytes(is_compressed=False)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = adjudicator_contract.functions.evaluateCFrag(*wrong_args).transact()
        testerchain.wait_for_receipt(tx)
    wrong_args = args[:]
    wrong_args[6] = UmbralPrivateKey.gen_key().get_pubkey().to_bytes(is_compressed=False)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = adjudicator_contract.functions.evaluateCFrag(*wrong_args).transact()
        testerchain.wait_for_receipt(tx)

    # Can't use signature for another data
    wrong_args = args[:]
    wrong_args[0] = bytes(args[0][0] + 1) + args[0][1:]
    with pytest.raises((TransactionFailed, ValueError)):
        tx = adjudicator_contract.functions.evaluateCFrag(*wrong_args).transact()
        testerchain.wait_for_receipt(tx)
    wrong_args = args[:]
    wrong_args[3] = bytes(args[3][0] + 1) + args[3][1:]
    with pytest.raises((TransactionFailed, ValueError)):
        tx = adjudicator_contract.functions.evaluateCFrag(*wrong_args).transact()
        testerchain.wait_for_receipt(tx)

    # Can't evaluate nonexistent miner
    address = to_canonical_address(wrong_miner)
    sig_key = provider.ethereum_tester.backend._key_lookup[address]
    signed_wrong_miner_umbral_public_key = bytes(sig_key.sign_msg_hash(miner_umbral_public_key_hash))
    wrong_args = args[:]
    wrong_args[7] = signed_wrong_miner_umbral_public_key
    with pytest.raises((TransactionFailed, ValueError)):
        tx = adjudicator_contract.functions.evaluateCFrag(*wrong_args).transact()
        testerchain.wait_for_receipt(tx)

@pytest.mark.slow
def test_upgrading(testerchain):
    creator = testerchain.interface.w3.eth.accounts[0]

    secret_hash = testerchain.interface.w3.keccak(secret)
    secret2_hash = testerchain.interface.w3.keccak(secret2)

    # Deploy contracts
    escrow1, _ = testerchain.interface.deploy_contract('MinersEscrowForMiningAdjudicatorMock')
    escrow2, _ = testerchain.interface.deploy_contract('MinersEscrowForMiningAdjudicatorMock')
    address1 = escrow1.address
    address2 = escrow2.address
    contract_library_v1, _ = testerchain.interface.deploy_contract(
        'MiningAdjudicator', address1, ALGORITHM_KECCAK256, 1, 2, 3, 4)
    dispatcher, _ = testerchain.interface.deploy_contract('Dispatcher', contract_library_v1.address, secret_hash)

    # Deploy second version of the contract
    contract_library_v2, _ = testerchain.interface.deploy_contract(
        'MiningAdjudicatorV2Mock', address2, ALGORITHM_SHA256, 5, 6, 7, 8)
    contract = testerchain.interface.w3.eth.contract(
        abi=contract_library_v2.abi,
        address=dispatcher.address,
        ContractFactoryClass=Contract)

    # Upgrade to the second version
    assert address1 == contract.functions.escrow().call()
    assert ALGORITHM_KECCAK256 == contract.functions.hashAlgorithm().call()
    assert 1 == contract.functions.basePenalty().call()
    assert 2 == contract.functions.penaltyHistoryCoefficient().call()
    assert 3 == contract.functions.percentagePenaltyCoefficient().call()
    assert 4 == contract.functions.rewardCoefficient().call()
    tx = dispatcher.functions.upgrade(contract_library_v2.address, secret, secret2_hash).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    # Check constructor and storage values
    assert contract_library_v2.address == dispatcher.functions.target().call()
    assert address2 == contract.functions.escrow().call()
    assert ALGORITHM_SHA256 == contract.functions.hashAlgorithm().call()
    assert 5 == contract.functions.basePenalty().call()
    assert 6 == contract.functions.penaltyHistoryCoefficient().call()
    assert 7 == contract.functions.percentagePenaltyCoefficient().call()
    assert 8 == contract.functions.rewardCoefficient().call()
    # Check new ABI
    tx = contract.functions.setValueToCheck(3).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert 3 == contract.functions.valueToCheck().call()

    # Can't upgrade to the previous version or to the bad version
    contract_library_bad, _ = testerchain.interface.deploy_contract('MiningAdjudicatorBad')
    with pytest.raises((TransactionFailed, ValueError)):
        tx = dispatcher.functions.upgrade(contract_library_v1.address, secret2, secret_hash) \
            .transact({'from': creator})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = dispatcher.functions.upgrade(contract_library_bad.address, secret2, secret_hash) \
            .transact({'from': creator})
        testerchain.wait_for_receipt(tx)

    # But can rollback
    tx = dispatcher.functions.rollback(secret2, secret_hash).transact({'from': creator})
    testerchain.wait_for_receipt(tx)
    assert contract_library_v1.address == dispatcher.functions.target().call()
    assert address1 == contract.functions.escrow().call()
    assert ALGORITHM_KECCAK256 == contract.functions.hashAlgorithm().call()
    assert 1 == contract.functions.basePenalty().call()
    assert 2 == contract.functions.penaltyHistoryCoefficient().call()
    assert 3 == contract.functions.percentagePenaltyCoefficient().call()
    assert 4 == contract.functions.rewardCoefficient().call()
    # After rollback new ABI is unavailable
    with pytest.raises((TransactionFailed, ValueError)):
        tx = contract.functions.setValueToCheck(2).transact({'from': creator})
        testerchain.wait_for_receipt(tx)

    # Try to upgrade to the bad version
    with pytest.raises((TransactionFailed, ValueError)):
        tx = dispatcher.functions.upgrade(contract_library_bad.address, secret, secret2_hash) \
            .transact({'from': creator})
        testerchain.wait_for_receipt(tx)
