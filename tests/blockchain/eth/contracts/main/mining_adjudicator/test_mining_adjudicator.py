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
from eth_utils import to_canonical_address
from typing import Tuple
from web3.contract import Contract

from umbral import pre
from umbral.curvebn import CurveBN
from umbral.keys import UmbralPrivateKey
from umbral.point import Point
from umbral.signing import Signer

from nucypher.crypto.utils import get_signature_recovery_value
from nucypher.policy.models import IndisputableEvidence


ALGORITHM_KECCAK256 = 0
ALGORITHM_SHA256 = 1
secret = (123456).to_bytes(32, byteorder='big')
secret2 = (654321).to_bytes(32, byteorder='big')


# TODO: Obtain real re-encryption metadata. Maybe constructing a WorkOrder and obtaining a response.
def mock_ursula_reencrypts(ursula_privkey, corrupt_cfrag: bool = False):
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

    ursula_pubkey = ursula_privkey.get_pubkey()
    ursula_pubkey_bytes = ursula_pubkey.to_bytes(is_compressed=False)[1:]
    specification = bytes(capsule) + ursula_pubkey_bytes + bytes(20) + bytes(32)

    ursulas_signer = Signer(ursula_privkey)
    bobs_signer = Signer(priv_key_bob)
    task_signature = bytes(bobs_signer(specification))

    metadata = bytes(ursulas_signer(task_signature))

    cfrag = pre.reencrypt(kfrags[0], capsule, metadata=metadata)

    if corrupt_cfrag:
        cfrag.proof.bn_sig = CurveBN.gen_rand(capsule.params.curve)

    cfrag_signature = bytes(ursulas_signer(bytes(cfrag)))

    bob_pubkey_bytes = pub_key_bob.to_bytes(is_compressed=False)[1:]

    cfrag_signature_v = get_signature_recovery_value(message=bytes(cfrag),
                                                     signature=cfrag_signature,
                                                     public_key=ursula_pubkey)
    task_signature_v = get_signature_recovery_value(message=task_signature,
                                                    signature=metadata,
                                                    public_key=ursula_pubkey)
    recovery_values = cfrag_signature_v + task_signature_v

    return capsule, cfrag, cfrag_signature, task_signature, recovery_values, bob_pubkey_bytes


def evaluation_hash(capsule, cfrag):
    hash_ctx = hashes.Hash(hashes.SHA256(), backend=backend)
    hash_ctx.update(bytes(capsule) + bytes(cfrag))
    data_hash = hash_ctx.finalize()
    return data_hash


@pytest.mark.slow
def test_evaluate_cfrag(testerchain, escrow, adjudicator_contract, slashing_economics):
    creator, miner, wrong_miner, investigator, *everyone_else = testerchain.interface.w3.eth.accounts
    evaluation_log = adjudicator_contract.events.CFragEvaluated.createFilter(fromBlock='latest')

    worker_stake = 1000
    worker_penalty_history = 0
    investigator_balance = 0
    number_of_evaluations = 0

    def compute_penalty_and_reward(stake: int, penalty_history: int) -> Tuple[int, int]:
        penalty_ = slashing_economics.base_penalty
        penalty_ += slashing_economics.penalty_history_coefficient * penalty_history
        penalty_ = min(penalty_, stake // slashing_economics.percentage_penalty_coefficient)
        reward_ = penalty_ // slashing_economics.reward_coefficient
        return penalty_, reward_

    # Prepare one miner
    tx = escrow.functions.setMinerInfo(miner, worker_stake).transact()
    testerchain.wait_for_receipt(tx)

    # Generate miner's Umbral key
    miner_umbral_private_key = UmbralPrivateKey.gen_key()
    miner_umbral_public_key_bytes = miner_umbral_private_key.get_pubkey().to_bytes(is_compressed=False)[1:]

    # Sign Umbral public key using eth-key
    hash_ctx = hashes.Hash(hashes.SHA256(), backend=backend)
    hash_ctx.update(miner_umbral_public_key_bytes)
    miner_umbral_public_key_hash = hash_ctx.finalize()
    provider = testerchain.interface.provider
    address = to_canonical_address(miner)
    sig_key = provider.ethereum_tester.backend._key_lookup[address]
    signed_miner_umbral_public_key = bytes(sig_key.sign_msg_hash(miner_umbral_public_key_hash))

    # Prepare evaluation data
    capsule, cfrag, *other_stuff = mock_ursula_reencrypts(miner_umbral_private_key)
    cfrag_signature, task_signature, recovery_values, bob_pubkey_bytes = other_stuff
    assert cfrag.verify_correctness(capsule)

    # Investigator prepares supporting Evidence
    evidence = IndisputableEvidence(capsule, cfrag, ursula=None)

    evidence_data = evidence.precompute_values()
    assert len(evidence_data) == 20 * 32 + 32 + 20 + 1

    data_hash = evaluation_hash(capsule, cfrag)
    # This capsule and cFrag are not yet evaluated
    assert not adjudicator_contract.functions.evaluatedCFrags(data_hash).call()

    # Challenge using good data
    args = (bytes(capsule),
            bytes(cfrag),
            cfrag_signature,
            task_signature,
            recovery_values,
            bob_pubkey_bytes,
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

    ###############################
    # Test: Don't evaluate miner with data that already was checked
    ###############################
    # TODO: be more specific on the expected exception
    with pytest.raises((TransactionFailed, ValueError)):
        tx = adjudicator_contract.functions.evaluateCFrag(*args).transact()
        testerchain.wait_for_receipt(tx)

    ###############################
    # Test: Ursula produces incorrect proof:
    ###############################
    capsule, cfrag, *other_stuff = mock_ursula_reencrypts(miner_umbral_private_key, corrupt_cfrag=True)
    cfrag_signature, task_signature, recovery_values, bob_pubkey_bytes = other_stuff
    assert not cfrag.verify_correctness(capsule)

    evidence = IndisputableEvidence(capsule, cfrag, ursula=None)
    evidence_data = evidence.precompute_values()
    args = (bytes(capsule),
            bytes(cfrag),
            cfrag_signature,
            task_signature,
            recovery_values,
            bob_pubkey_bytes,
            miner_umbral_public_key_bytes,
            signed_miner_umbral_public_key,
            evidence_data)

    data_hash = evaluation_hash(capsule, cfrag)
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

    capsule, cfrag, *other_stuff = mock_ursula_reencrypts(miner_umbral_private_key)
    cfrag_signature, task_signature, recovery_values, bob_pubkey_bytes = other_stuff
    assert cfrag.verify_correctness(capsule)

    evidence = IndisputableEvidence(capsule, cfrag, ursula=None)
    evidence_data = evidence.precompute_values()

    # Bob produces a random point and gets the bytes of coords x and y
    random_point_bytes = Point.gen_rand().to_bytes(is_compressed=False)[1:]
    # He uses this garbage instead of correct precomputation of z*E
    evidence_data = bytearray(evidence_data)
    evidence_data[32:32+64] = random_point_bytes
    evidence_data = bytes(evidence_data)

    args = (bytes(capsule),
            bytes(cfrag),
            cfrag_signature,
            task_signature,
            recovery_values,
            bob_pubkey_bytes,
            miner_umbral_public_key_bytes,
            signed_miner_umbral_public_key,
            evidence_data)

    data_hash = evaluation_hash(capsule, cfrag)
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

    capsule, cfrag, *other_stuff = mock_ursula_reencrypts(miner_umbral_private_key, corrupt_cfrag=True)
    cfrag_signature, task_signature, recovery_values, bob_pubkey_bytes = other_stuff

    evidence = IndisputableEvidence(capsule, cfrag, ursula=None)
    evidence_data = evidence.precompute_values()
    args = (bytes(capsule),
            bytes(cfrag),
            cfrag_signature,
            task_signature,
            recovery_values,
            bob_pubkey_bytes,
            miner_umbral_public_key_bytes,
            signed_miner_umbral_public_key,
            evidence_data)

    data_hash = evaluation_hash(capsule, cfrag)
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
    assert penalty == previous_penalty + slashing_economics.penalty_history_coefficient
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

    capsule, cfrag, *other_stuff = mock_ursula_reencrypts(miner_umbral_private_key, corrupt_cfrag=True)
    cfrag_signature, task_signature, recovery_values, bob_pubkey_bytes = other_stuff

    evidence = IndisputableEvidence(capsule, cfrag, ursula=None)
    evidence_data = evidence.precompute_values()
    args = (bytes(capsule),
            bytes(cfrag),
            cfrag_signature,
            task_signature,
            recovery_values,
            bob_pubkey_bytes,
            miner_umbral_public_key_bytes,
            signed_miner_umbral_public_key,
            evidence_data)

    data_hash = evaluation_hash(capsule, cfrag)
    assert not adjudicator_contract.functions.evaluatedCFrags(data_hash).call()

    worker_stake = escrow.functions.minerInfo(miner).call()[0]
    investigator_balance = escrow.functions.rewardInfo(investigator).call()

    tx = adjudicator_contract.functions.evaluateCFrag(*args).transact({'from': investigator})
    testerchain.wait_for_receipt(tx)
    number_of_evaluations += 1

    assert adjudicator_contract.functions.evaluatedCFrags(data_hash).call()

    penalty, reward = compute_penalty_and_reward(worker_stake, worker_penalty_history)
    # Penalty has reached maximum available percentage of value
    assert penalty == worker_stake // slashing_economics.percentage_penalty_coefficient
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
    wrong_args = list(args)
    wrong_args[2] = cfrag_signature[1:]
    with pytest.raises((TransactionFailed, ValueError)):
        tx = adjudicator_contract.functions.evaluateCFrag(*wrong_args).transact()
        testerchain.wait_for_receipt(tx)

    wrong_args = list(args)
    wrong_args[3] = task_signature[1:]
    with pytest.raises((TransactionFailed, ValueError)):
        tx = adjudicator_contract.functions.evaluateCFrag(*wrong_args).transact()
        testerchain.wait_for_receipt(tx)

    wrong_args = list(args)
    wrong_args[7] = signed_miner_umbral_public_key[1:]
    with pytest.raises((TransactionFailed, ValueError)):
        tx = adjudicator_contract.functions.evaluateCFrag(*wrong_args).transact()
        testerchain.wait_for_receipt(tx)

    # Can't evaluate miner using wrong keys
    wrong_args = list(args)
    wrong_args[5] = UmbralPrivateKey.gen_key().get_pubkey().to_bytes(is_compressed=False)[1:]
    with pytest.raises((TransactionFailed, ValueError)):
        tx = adjudicator_contract.functions.evaluateCFrag(*wrong_args).transact()
        testerchain.wait_for_receipt(tx)

    wrong_args = list(args)
    wrong_args[6] = UmbralPrivateKey.gen_key().get_pubkey().to_bytes(is_compressed=False)[1:]
    with pytest.raises((TransactionFailed, ValueError)):
        tx = adjudicator_contract.functions.evaluateCFrag(*wrong_args).transact()
        testerchain.wait_for_receipt(tx)

    # Can't use signature for another data
    wrong_args = list(args)
    wrong_args[1] = os.urandom(len(bytes(cfrag)))
    with pytest.raises((TransactionFailed, ValueError)):
        tx = adjudicator_contract.functions.evaluateCFrag(*wrong_args).transact()
        testerchain.wait_for_receipt(tx)

    # Can't evaluate nonexistent miner
    address = to_canonical_address(wrong_miner)
    sig_key = provider.ethereum_tester.backend._key_lookup[address]
    signed_wrong_miner_umbral_public_key = bytes(sig_key.sign_msg_hash(miner_umbral_public_key_hash))

    wrong_args = list(args)
    wrong_args[7] = signed_wrong_miner_umbral_public_key
    with pytest.raises((TransactionFailed, ValueError)):
        tx = adjudicator_contract.functions.evaluateCFrag(*wrong_args).transact()
        testerchain.wait_for_receipt(tx)

@pytest.mark.slow
def test_upgrading(testerchain):
    creator = testerchain.interface.w3.eth.accounts[0]

    secret_hash = testerchain.interface.w3.keccak(secret)
    secret2_hash = testerchain.interface.w3.keccak(secret2)

    # Only escrow contract is allowed in MiningAdjudicator constructor
    with pytest.raises((TransactionFailed, ValueError)):
        testerchain.interface.deploy_contract('MiningAdjudicator', creator, ALGORITHM_KECCAK256, 1, 2, 3, 4)

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

    # Can't call `finishUpgrade` and `verifyState` methods outside upgrade lifecycle
    with pytest.raises((TransactionFailed, ValueError)):
        tx = contract_library_v1.functions.finishUpgrade(contract.address).transact({'from': creator})
        testerchain.wait_for_receipt(tx)
    with pytest.raises((TransactionFailed, ValueError)):
        tx = contract_library_v1.functions.verifyState(contract.address).transact({'from': creator})
        testerchain.wait_for_receipt(tx)

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

    events = dispatcher.events.StateVerified.createFilter(fromBlock=0).get_all_entries()
    assert 4 == len(events)
    event_args = events[0]['args']
    assert contract_library_v1.address == event_args['testTarget']
    assert creator == event_args['sender']
    event_args = events[1]['args']
    assert contract_library_v2.address == event_args['testTarget']
    assert creator == event_args['sender']
    assert event_args == events[2]['args']
    event_args = events[3]['args']
    assert contract_library_v2.address == event_args['testTarget']
    assert creator == event_args['sender']

    events = dispatcher.events.UpgradeFinished.createFilter(fromBlock=0).get_all_entries()
    assert 3 == len(events)
    event_args = events[0]['args']
    assert contract_library_v1.address == event_args['target']
    assert creator == event_args['sender']
    event_args = events[1]['args']
    assert contract_library_v2.address == event_args['target']
    assert creator == event_args['sender']
    event_args = events[2]['args']
    assert contract_library_v1.address == event_args['target']
    assert creator == event_args['sender']
