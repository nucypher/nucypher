import os
import random
from unittest.mock import patch

import pytest
import pytest_twisted
from hexbytes import HexBytes
from prometheus_client import REGISTRY

from nucypher.blockchain.eth.agents import ContractAgency, SubscriptionManagerAgent
from nucypher.blockchain.eth.constants import NULL_ADDRESS
from nucypher.blockchain.eth.models import Coordinator
from nucypher.blockchain.eth.signers.software import InMemorySigner
from nucypher.characters.lawful import Enrico, Ursula
from nucypher.policy.conditions.evm import ContractCondition, RPCCondition
from nucypher.policy.conditions.lingo import (
    ConditionLingo,
    NotCompoundCondition,
    OrCompoundCondition,
    ReturnValueTest,
)
from nucypher.policy.conditions.time import TimeCondition
from tests.constants import TEST_ETH_PROVIDER_URI, TESTERCHAIN_CHAIN_ID


@pytest.fixture(scope="module")
def ritual_id():
    return 0


@pytest.fixture(scope="module")
def dkg_size():
    return 4


@pytest.fixture(scope="module")
def duration():
    return 48 * 60 * 60


@pytest.fixture(scope="module")
def plaintext():
    return "peace at dawn"


@pytest.fixture(scope="module")
def interval(testerchain):
    return testerchain.tx_machine._task.interval


@pytest.fixture(scope="module")
def signer():
    return InMemorySigner()


@pytest.fixture(scope="module")
def condition(test_registry):
    time_condition = TimeCondition(
        chain=TESTERCHAIN_CHAIN_ID,
        return_value_test=ReturnValueTest(comparator=">", value=0),
    )
    rpc_condition = RPCCondition(
        chain=TESTERCHAIN_CHAIN_ID,
        method="eth_getBalance",
        return_value_test=ReturnValueTest(comparator="==", value=0),
        parameters=["0x0000000000000000000000000000000000000007"],  # random account
    )

    subscription_manager = ContractAgency.get_agent(
        SubscriptionManagerAgent,
        registry=test_registry,
        blockchain_endpoint=TEST_ETH_PROVIDER_URI,
    )
    contract_condition = ContractCondition(
        contract_address=subscription_manager.contract.address,
        function_abi=subscription_manager.contract.get_function_by_name(
            "getPolicy"
        ).abi,
        method="getPolicy",
        chain=TESTERCHAIN_CHAIN_ID,
        return_value_test=ReturnValueTest(
            comparator="==", value=[NULL_ADDRESS, 0, 0, 0, NULL_ADDRESS]
        ),
        parameters=[HexBytes(os.urandom(16)).hex()],
    )

    or_condition = OrCompoundCondition(
        operands=[time_condition, rpc_condition, contract_condition]
    )

    and_condition = OrCompoundCondition(
        operands=[time_condition, rpc_condition, contract_condition]
    )

    not_not_condition = NotCompoundCondition(
        operand=NotCompoundCondition(operand=and_condition)
    )

    conditions = [
        time_condition,
        rpc_condition,
        contract_condition,
        or_condition,
        and_condition,
        not_not_condition,
    ]

    condition_to_use = random.choice(conditions)
    return ConditionLingo(condition_to_use).to_dict()


@pytest.fixture(scope="module", autouse=True)
def transaction_tracker(testerchain, coordinator_agent):
    testerchain.tx_machine.w3 = coordinator_agent.blockchain.w3
    testerchain.tx_machine.start()


@pytest.fixture(scope="module")
def cohort(testerchain, clock, coordinator_agent, ursulas, dkg_size):
    nodes = list(sorted(ursulas[:dkg_size], key=lambda x: int(x.checksum_address, 16)))
    assert len(nodes) == dkg_size
    for node in nodes:
        node.ritual_tracker.task._task.clock = clock
        node.ritual_tracker.start()
    return nodes


@pytest.fixture(scope="module")
def threshold_message_kit(coordinator_agent, plaintext, condition, signer, ritual_id):
    encrypting_key = coordinator_agent.get_ritual_public_key(ritual_id=ritual_id)
    enrico = Enrico(encrypting_key=encrypting_key, signer=signer)
    return enrico.encrypt_for_dkg(plaintext=plaintext.encode(), conditions=condition)


def test_dkg_initiation(
    coordinator_agent,
    accounts,
    initiator,
    cohort,
    fee_model,
    global_allow_list,
    testerchain,
    ritual_token,
    ritual_id,
    duration,
):
    print("==================== INITIALIZING ====================")
    cohort_staking_provider_addresses = list(u.checksum_address for u in cohort)

    # Approve the ritual token for the coordinator agent to spend
    amount = fee_model.getRitualCost(len(cohort_staking_provider_addresses), duration)
    ritual_token.approve(
        fee_model.address,
        amount,
        sender=accounts[initiator.transacting_power.account],
    )

    receipt = coordinator_agent.initiate_ritual(
        fee_model=fee_model.address,
        providers=cohort_staking_provider_addresses,
        authority=initiator.transacting_power.account,
        duration=duration,
        access_controller=global_allow_list.address,
        transacting_power=initiator.transacting_power,
    )

    testerchain.time_travel(seconds=1)
    testerchain.wait_for_receipt(receipt["transactionHash"])

    # check that the ritual was created on-chain
    assert coordinator_agent.number_of_rituals() == ritual_id + 1
    assert (
        coordinator_agent.get_ritual_status(ritual_id)
        == Coordinator.RitualStatus.DKG_AWAITING_TRANSCRIPTS
    )


@pytest_twisted.inlineCallbacks
def test_dkg_finality(
    coordinator_agent, ritual_id, cohort, clock, interval, testerchain
):
    print("==================== AWAITING DKG FINALITY ====================")

    while (
        coordinator_agent.get_ritual_status(ritual_id)
        != Coordinator.RitualStatus.ACTIVE
    ):
        yield clock.advance(interval)
        yield testerchain.time_travel(seconds=1)

    testerchain.tx_machine.stop()
    assert not testerchain.tx_machine.running

    status = coordinator_agent.get_ritual_status(ritual_id)
    assert status == Coordinator.RitualStatus.ACTIVE
    last_scanned_block = REGISTRY.get_sample_value(
        "ritual_events_last_scanned_block_number"
    )
    assert last_scanned_block > 0
    yield


def test_transcript_publication(coordinator_agent, cohort, ritual_id, dkg_size):
    print("==================== VERIFYING DKG FINALITY ====================")
    for ursula in cohort:
        assert (
            len(
                coordinator_agent.get_participant(
                    ritual_id=ritual_id,
                    provider=ursula.checksum_address,
                    transcript=True,
                ).transcript
            )
            > 0
        ), "no transcript found for ursula"
        print(f"Ursula {ursula.checksum_address} has submitted a transcript")


def test_get_participants(coordinator_agent, cohort, ritual_id, dkg_size):
    pagination_sizes = range(0, dkg_size)  # 0 means get all in one call
    for page_size in pagination_sizes:
        with patch.object(coordinator_agent, "_get_page_size", return_value=page_size):
            ritual = coordinator_agent.get_ritual(ritual_id, transcripts=True)
            for i, participant in enumerate(ritual.participants):
                assert participant.provider == cohort[i].checksum_address
                assert participant.aggregated is True
                assert participant.transcript
                assert participant.decryption_request_static_key

                assert len(ritual.participants) == dkg_size


def test_encrypt(
    coordinator_agent, condition, ritual_id, plaintext, testerchain, signer
):
    print("==================== DKG ENCRYPTION ====================")
    encrypting_key = coordinator_agent.get_ritual_public_key(ritual_id=ritual_id)
    plaintext = plaintext.encode()
    enrico = Enrico(encrypting_key=encrypting_key, signer=signer)
    print(f"encrypting for DKG with key {bytes(encrypting_key).hex()}")
    tmk = enrico.encrypt_for_dkg(plaintext=plaintext, conditions=condition)
    assert tmk.ciphertext_header


@pytest_twisted.inlineCallbacks
def test_unauthorized_decryption(
    bob, cohort, threshold_message_kit, ritual_id, signer, global_allow_list
):
    print("======== DKG DECRYPTION (UNAUTHORIZED) ========")
    assert not global_allow_list.isAddressAuthorized(ritual_id, signer.accounts[0])

    bob.start_learning_loop(now=True)
    with pytest.raises(
        Ursula.NotEnoughUrsulas,
        match=f"Encrypted data not authorized for ritual {ritual_id}",
    ):
        yield bob.threshold_decrypt(
            threshold_message_kit=threshold_message_kit,
        )

    # check prometheus metric for decryption requests
    # since all running on the same machine - the value is not per-ursula but rather all
    num_failures = REGISTRY.get_sample_value("threshold_decryption_num_failures_total")
    assert len(cohort) == int(num_failures)  # each ursula in cohort had a failure
    yield


def check_decrypt_without_any_cached_values(
    threshold_message_kit, ritual_id, cohort, bob, coordinator_agent, plaintext
):
    print("==================== DKG DECRYPTION NO CACHE ====================")
    original_validators = cohort[0].dkg_storage.get_validators(ritual_id)

    for ursula in cohort:
        ursula.dkg_storage.clear(ritual_id)
        assert ursula.dkg_storage.get_validators(ritual_id) is None
        assert ursula.dkg_storage.get_active_ritual(ritual_id) is None

    bob.start_learning_loop(now=True)
    cleartext = bob.threshold_decrypt(
        threshold_message_kit=threshold_message_kit,
    )
    assert bytes(cleartext) == plaintext.encode()

    ritual = coordinator_agent.get_ritual(ritual_id)
    num_used_ursulas = 0
    for ursula_index, ursula in enumerate(cohort):
        stored_ritual = ursula.dkg_storage.get_active_ritual(ritual_id)
        if not stored_ritual:
            # this ursula was not used for threshold decryption; skip
            continue
        assert stored_ritual == ritual

        stored_validators = ursula.dkg_storage.get_validators(ritual_id)
        num_used_ursulas += 1
        for v_index, v in enumerate(stored_validators):
            assert v.address == original_validators[v_index].address
            assert v.public_key == original_validators[v_index].public_key

    assert num_used_ursulas >= ritual.threshold
    print("===================== DECRYPTION SUCCESSFUL =====================")


@pytest_twisted.inlineCallbacks
def test_authorized_decryption(
    bob,
    global_allow_list,
    accounts,
    coordinator_agent,
    threshold_message_kit,
    signer,
    initiator,
    ritual_id,
    plaintext,
):
    print("==================== DKG DECRYPTION (AUTHORIZED) ====================")
    # authorize Enrico to encrypt for ritual
    global_allow_list.authorize(
        ritual_id,
        [signer.accounts[0]],
        sender=accounts[initiator.transacting_power.account],
    )

    # ritual_id, ciphertext, conditions are obtained from the side channel
    bob.start_learning_loop(now=True)
    cleartext = yield bob.threshold_decrypt(
        threshold_message_kit=threshold_message_kit,
    )
    assert bytes(cleartext) == plaintext.encode()

    # check prometheus metric for decryption requests
    # since all running on the same machine - the value is not per-ursula but rather all
    num_successes = REGISTRY.get_sample_value(
        "threshold_decryption_num_successes_total"
    )

    ritual = coordinator_agent.get_ritual(ritual_id)
    # at least a threshold of ursulas were successful (concurrency)
    assert int(num_successes) >= ritual.threshold
    yield


def test_encryption_and_decryption_prometheus_metrics():
    print("==================== METRICS ====================")
    # check prometheus metric for decryption requests
    # since all running on the same machine - the value is not per-ursula but rather all
    num_decryption_failures = REGISTRY.get_sample_value(
        "threshold_decryption_num_failures_total"
    )
    num_decryption_successes = REGISTRY.get_sample_value(
        "threshold_decryption_num_successes_total"
    )
    num_decryption_requests = REGISTRY.get_sample_value(
        "decryption_request_processing_count"
    )
    assert num_decryption_requests == (
        num_decryption_successes + num_decryption_failures
    )
