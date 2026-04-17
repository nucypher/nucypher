import os
import random
import time
from unittest.mock import ANY, patch

import pytest
import pytest_twisted
from hexbytes import HexBytes
from prometheus_client import REGISTRY

from nucypher.blockchain.eth.agents import ContractAgency, SubscriptionManagerAgent
from nucypher.blockchain.eth.constants import NULL_ADDRESS
from nucypher.blockchain.eth.models import Coordinator
from nucypher.blockchain.eth.signers.software import InMemorySigner
from nucypher.characters.lawful import Enrico, Ursula
from nucypher.network.concurrency import ThresholdDecryptionClient
from nucypher.policy.conditions.evm import ContractCondition, RPCCondition
from nucypher.policy.conditions.lingo import (
    ConditionLingo,
    ConditionVariable,
    NotCompoundCondition,
    OrCompoundCondition,
    ReturnValueTest,
    SequentialCondition,
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
        operand=NotCompoundCondition(operand=rpc_condition)
    )

    sequential_condition = SequentialCondition(
        condition_variables=[
            ConditionVariable("rpc", rpc_condition),
            ConditionVariable("contract", contract_condition),
        ]
    )

    conditions = [
        time_condition,
        rpc_condition,
        contract_condition,
        or_condition,
        and_condition,
        not_not_condition,
        sequential_condition,
    ]

    condition_to_use = random.choice(conditions)
    return ConditionLingo(condition_to_use).to_dict()


@pytest.fixture(scope="module", autouse=True)
def transaction_tracker(testerchain, coordinator_agent):
    testerchain.tx_machine.w3 = coordinator_agent.blockchain.w3
    testerchain.tx_machine.start()


@pytest.fixture(scope="module")
def cohort(testerchain, clock, coordinator_agent, ursulas, dkg_size):
    nodes = ursulas[:dkg_size]
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


@pytest.fixture(scope="module")
def incoming_validator(ursulas, dkg_size, clock):
    incoming_validator = ursulas[dkg_size]
    incoming_validator.ritual_tracker.task._task.clock = clock
    incoming_validator.ritual_tracker.start()
    return incoming_validator


@pytest.fixture(scope="module")
def departing_validator(cohort):
    # randomize departing validator from the cohort
    return cohort[random.randint(0, len(cohort) - 1)]


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
    # initiation requires sorted order (others don't)
    cohort_staking_provider_addresses = list(
        u.checksum_address
        for u in sorted(cohort, key=lambda x: int(x.checksum_address, 16))
    )

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


def test_get_participants(coordinator_agent, cohort, ritual_id, dkg_size):
    pagination_sizes = range(0, dkg_size)  # 0 means get all in one call
    ordered_cohort = sorted(cohort, key=lambda x: int(x.checksum_address, 16))
    for page_size in pagination_sizes:
        with patch.object(coordinator_agent, "_get_page_size", return_value=page_size):
            ritual = coordinator_agent.get_ritual(ritual_id, transcripts=True)
            for i, participant in enumerate(ritual.participants):
                assert participant.provider == ordered_cohort[i].checksum_address
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


@pytest_twisted.inlineCallbacks
def test_authorized_decryption(
    mocker,
    bob,
    global_allow_list,
    accounts,
    coordinator_agent,
    threshold_message_kit,
    signer,
    initiator,
    ritual_id,
    cohort,
    plaintext,
):
    print("==================== DKG DECRYPTION (AUTHORIZED) ====================")
    # authorize Enrico to encrypt for ritual
    global_allow_list.authorize(
        ritual_id,
        [signer.accounts[0]],
        sender=accounts[initiator.transacting_power.account],
    )

    # fake some latency stats
    latency_stats = {}
    for ursula in cohort:
        # reset all stats
        bob.node_latency_collector.reset_stats(ursula.checksum_address)
        # add a single data point for each ursula: some time between 0.1 and 4
        mock_latency = random.uniform(0.1, 4)
        bob.node_latency_collector._update_stats(ursula.checksum_address, mock_latency)
        latency_stats[ursula.checksum_address] = mock_latency

    expected_ursula_request_ordering = sorted(
        list(latency_stats.keys()),
        key=lambda ursula_checksum: latency_stats[ursula_checksum],
    )
    value_factory_spy = mocker.spy(ThresholdDecryptionClient.RequestFactory, "__init__")

    # ritual_id, ciphertext, conditions are obtained from the side channel
    bob.start_learning_loop(now=True)
    cleartext = yield bob.threshold_decrypt(
        threshold_message_kit=threshold_message_kit,
    )
    assert bytes(cleartext) == plaintext.encode()

    # check that proper ordering of ursulas used for worker pool factory for requests
    value_factory_spy.assert_called_once_with(
        ANY,
        ursulas_to_contact=expected_ursula_request_ordering,
        threshold=ANY,
    )

    # check prometheus metric for decryption requests
    # since all running on the same machine - the value is not per-ursula but rather all
    num_successes = REGISTRY.get_sample_value(
        "threshold_decryption_num_successes_total"
    )

    ritual = coordinator_agent.get_ritual(ritual_id)
    # at least a threshold of ursulas were successful (concurrency)
    assert int(num_successes) >= ritual.threshold
    print("===================== DECRYPTION SUCCESSFUL =====================")
    yield


@pytest_twisted.inlineCallbacks
def test_decryption_failure_node_timeout(
    mocker, threshold_message_kit, ritual_id, cohort, bob, coordinator_agent, plaintext
):
    print(
        "==================== DKG DECRYPTION FAILURE NODE TIMEOUT (EXPECTED) ===================="
    )

    # mock timeout for all ursulas in cohort
    timeout = 1

    def timed_out_request_signature(*args, **kwargs):
        time.sleep(timeout + 2)  # ensures node never responds in time
        raise ValueError("Fake exception should be after worker pool timeout")

    mocker.patch(
        "nucypher.network.middleware.RestMiddleware.get_encrypted_decryption_share",
        side_effect=timed_out_request_signature,
    )

    # perform threshold decryption
    bob.start_learning_loop(now=True)
    with pytest.raises(
        Ursula.NotEnoughUrsulas, match="Threshold of Ursulas unable to decrypt"
    ) as exc_info:
        _ = yield bob.threshold_decrypt(
            threshold_message_kit=threshold_message_kit,
            decryption_timeout=timeout,
        )

    message = str(exc_info.value)
    for ursula in cohort:
        assert (
            f"Node {ursula.checksum_address} did not respond before timeout ({timeout}s)"
            in message
        )

    print(
        "===================== DECRYPTION FAILURE NODE TIMEOUT (EXPECTED) SUCCESSFUL  ====================="
    )
    yield


@pytest_twisted.inlineCallbacks
def test_decrypt_without_any_cached_values(
    threshold_message_kit, ritual_id, cohort, bob, coordinator_agent, plaintext
):
    print("==================== DKG DECRYPTION NO CACHE ====================")
    original_validators = cohort[0].dkg_storage.get_validators(ritual_id)
    for ursula in cohort:
        ursula.dkg_storage.clear(ritual_id)
        assert ursula.dkg_storage.get_validators(ritual_id) is None
        assert ursula.dkg_storage.get_active_ritual(ritual_id) is None

    # perform threshold decryption
    bob.start_learning_loop(now=True)
    cleartext = yield bob.threshold_decrypt(
        threshold_message_kit=threshold_message_kit,
    )
    assert bytes(cleartext) == plaintext.encode()

    ritual = coordinator_agent.get_ritual(ritual_id)
    num_used_ursulas = 0
    for ursula_index, ursula in enumerate(cohort):
        stored_validators = ursula.dkg_storage.get_validators(ritual_id)
        if not stored_validators:
            # this ursula was not used for threshold decryption; skip
            continue

        num_used_ursulas += 1
        for v_index, v in enumerate(stored_validators):
            assert v.address == original_validators[v_index].address
            assert v.public_key == original_validators[v_index].public_key

        stored_ritual = ursula.dkg_storage.get_active_ritual(ritual_id)
        assert stored_ritual == ritual

    assert num_used_ursulas >= ritual.threshold
    print("===================== DECRYPTION NO CACHE SUCCESSFUL =====================")
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


def check_nodes_ritual_metadata(nodes_to_check, ritual_id, should_exist=True):
    for ursula in nodes_to_check:
        ritual = ursula.dkg_storage.get_active_ritual(ritual_id)
        validators = ursula.dkg_storage.get_validators(ritual_id)
        if should_exist:
            assert ritual is not None, f"Ritual {ritual_id} object should be in cache"
            assert (
                validators is not None
            ), f"Validators for ritual {ritual_id} should be in cache"
        else:
            assert ritual is None, f"Ritual {ritual_id} object should not be in cache"
            assert (
                validators is None
            ), f"Validators for ritual {ritual_id} should not be in cache"


def test_handover_request(
    coordinator_agent,
    testerchain,
    ritual_id,
    cohort,
    supervisor_transacting_power,
    departing_validator,
    incoming_validator,
):
    testerchain.tx_machine.start()

    print("==================== INITIALIZING HANDOVER ====================")
    # check that ritual metadata is present in cache
    check_nodes_ritual_metadata(cohort, ritual_id, should_exist=True)

    receipt = coordinator_agent.request_handover(
        ritual_id=ritual_id,
        departing_validator=departing_validator.checksum_address,
        incoming_validator=incoming_validator.checksum_address,
        transacting_power=supervisor_transacting_power,
    )

    testerchain.time_travel(seconds=1)
    testerchain.wait_for_receipt(receipt["transactionHash"])

    handover_status = coordinator_agent.get_handover_status(
        ritual_id=ritual_id, departing_validator=departing_validator.checksum_address
    )
    assert handover_status == Coordinator.HandoverStatus.HANDOVER_AWAITING_TRANSCRIPT


@pytest_twisted.inlineCallbacks
def test_handover_finality(
    coordinator_agent,
    ritual_id,
    cohort,
    clock,
    interval,
    testerchain,
    departing_validator,
    incoming_validator,
    supervisor_transacting_power,
):
    print("==================== AWAITING HANDOVER FINALITY ====================")

    handover_status = coordinator_agent.get_handover_status(
        ritual_id=ritual_id, departing_validator=departing_validator.checksum_address
    )
    assert handover_status != Coordinator.HandoverStatus.NON_INITIATED

    while handover_status not in (
        Coordinator.HandoverStatus.NON_INITIATED,
        Coordinator.HandoverStatus.HANDOVER_AWAITING_FINALIZATION,
    ):
        handover_status = coordinator_agent.get_handover_status(
            ritual_id=ritual_id,
            departing_validator=departing_validator.checksum_address,
        )
        assert handover_status != Coordinator.HandoverStatus.HANDOVER_TIMEOUT
        yield clock.advance(interval)
        yield testerchain.time_travel(seconds=1)

    # check that ritual metadata is not present in cache anymore because in the midst of handover
    check_nodes_ritual_metadata(
        [*cohort, incoming_validator], ritual_id, should_exist=False
    )

    _receipt = coordinator_agent.finalize_handover(
        ritual_id=ritual_id,
        departing_validator=departing_validator.checksum_address,
        transacting_power=supervisor_transacting_power,
    )
    handover_status = coordinator_agent.get_handover_status(
        ritual_id=ritual_id, departing_validator=departing_validator.checksum_address
    )
    assert handover_status == Coordinator.HandoverStatus.NON_INITIATED

    testerchain.tx_machine.stop()
    assert not testerchain.tx_machine.running
    last_scanned_block = REGISTRY.get_sample_value(
        "ritual_events_last_scanned_block_number"
    )
    assert last_scanned_block > 0
    yield


@pytest_twisted.inlineCallbacks
def test_decryption_after_handover(
    mocker,
    bob,
    accounts,
    coordinator_agent,
    threshold_message_kit,
    ritual_id,
    cohort,
    plaintext,
    departing_validator,
    incoming_validator,
):
    print("==================== DKG DECRYPTION POST-HANDOVER ====================")

    departing_validator_spy = mocker.spy(
        departing_validator, "handle_threshold_decryption_request"
    )
    incoming_validator_spy = mocker.spy(
        incoming_validator, "handle_threshold_decryption_request"
    )
    # ensure that the incoming validator handled the request;
    # the ritual is 3/4 so we need 1 ursula in the cohort to fail to decrypt
    # to ensure that the incoming validator is actually used
    node_to_fail = None
    for u in cohort:
        if u.checksum_address != departing_validator.checksum_address:
            node_to_fail = u
            break
    assert node_to_fail is not None
    mocker.patch.object(
        node_to_fail,
        "handle_threshold_decryption_request",
        side_effect=ValueError("forcibly failed"),
    )

    # ritual_id, ciphertext, conditions are obtained from the side channel
    bob.start_learning_loop(now=True)
    cleartext = yield bob.threshold_decrypt(
        threshold_message_kit=threshold_message_kit,
    )
    assert bytes(cleartext) == plaintext.encode()

    # ensure that the departing validator did not handle the request
    assert departing_validator_spy.call_count == 0
    # ensure that the incoming validator handled the request
    assert incoming_validator_spy.call_count == 1

    num_successes = REGISTRY.get_sample_value(
        "threshold_decryption_num_successes_total"
    )

    ritual = coordinator_agent.get_ritual(ritual_id)
    # at least a threshold of ursulas were successful (concurrency)
    assert int(num_successes) >= ritual.threshold

    # now that handover is completed (clears cache), and there was a
    # successful decryption (populates cache) check that ritual metadata is present again
    nodes_to_check_for_participation_in_decryption = list(cohort)
    nodes_to_check_for_participation_in_decryption.remove(
        departing_validator
    )  # no longer in cohort
    nodes_to_check_for_participation_in_decryption.append(
        incoming_validator
    )  # now part of cohort
    nodes_to_check_for_participation_in_decryption.remove(
        node_to_fail
    )  # in the cohort but will fail to decrypt so cache not populated
    check_nodes_ritual_metadata(
        nodes_to_check_for_participation_in_decryption, ritual_id, should_exist=True
    )

    # this check reinforces that the departing validator did not participate in the decryption
    check_nodes_ritual_metadata([departing_validator], ritual_id, should_exist=False)

    print("===================== DECRYPTION SUCCESSFUL =====================")
    yield
