import pytest
import pytest_twisted
from eth_account.messages import defunct_hash_message

from nucypher.blockchain.eth.models import SigningCoordinator
from nucypher.policy.conditions.auth.evm import EIP1271Auth
from nucypher.policy.conditions.lingo import ConditionLingo


@pytest.fixture(scope="module")
def cohort_id():
    return 0


@pytest.fixture(scope="module")
def dkg_size():
    return 4


@pytest.fixture(scope="module")
def duration():
    return 48 * 60 * 60


@pytest.fixture(scope="module")
def interval(testerchain):
    return testerchain.tx_machine._task.interval


@pytest.fixture(scope="module", autouse=True)
def transaction_tracker(testerchain, signing_coordinator_agent):
    testerchain.tx_machine.w3 = signing_coordinator_agent.blockchain.w3
    testerchain.tx_machine.start()


@pytest.fixture(scope="module")
def cohort(testerchain, clock, signing_coordinator_agent, ursulas, dkg_size):
    nodes = list(sorted(ursulas[:dkg_size], key=lambda x: int(x.checksum_address, 16)))
    assert len(nodes) == dkg_size
    for node in nodes:
        node.signing_ritual_tracker.task._task.clock = clock
        node.signing_ritual_tracker.start()
    return nodes


# TODO figure out why I can't do this in conftest.py
@pytest.fixture(scope="module")
def ritual_initiator(initiator, signing_coordinator, deployer_account):
    signing_coordinator.grantRole(
        signing_coordinator.INITIATOR_ROLE(),
        initiator.transacting_power.account,
        sender=deployer_account,
    )
    return initiator


def test_signing_cohort_initiation(
    signing_coordinator_agent,
    accounts,
    ritual_initiator,
    cohort,
    testerchain,
    cohort_id,
    duration,
):
    print("==================== INITIALIZING ====================")
    cohort_staking_provider_addresses = list(u.checksum_address for u in cohort)

    receipt = signing_coordinator_agent.initiate_signing_cohort(
        authority=ritual_initiator.transacting_power.account,
        providers=cohort_staking_provider_addresses,
        threshold=len(cohort_staking_provider_addresses) - 1,
        duration=duration,
        transacting_power=ritual_initiator.transacting_power,
    )

    testerchain.time_travel(seconds=1)
    testerchain.wait_for_receipt(receipt["transactionHash"])

    # check that the ritual was created on-chain
    assert signing_coordinator_agent.number_of_cohorts() == cohort_id + 1
    assert (
        signing_coordinator_agent.get_signing_cohort_status(cohort_id)
        == SigningCoordinator.RitualStatus.AWAITING_SIGNATURES
    )


@pytest_twisted.inlineCallbacks
def test_signing_cohort_finality(
    signing_coordinator_agent,
    cohort_id,
    cohort,
    clock,
    interval,
    testerchain,
    ritual_initiator,
    time_condition,
):
    print("==================== AWAITING COHORT FINALITY ====================")
    while (
        not signing_coordinator_agent.get_signing_cohort_status(cohort_id)
        == SigningCoordinator.RitualStatus.AWAITING_CONDITIONS
    ):
        yield clock.advance(interval)
        yield testerchain.time_travel(seconds=1)

    testerchain.tx_machine.stop()
    assert not testerchain.tx_machine.running

    signing_coordinator_agent.set_signing_cohort_conditions(
        cohort_id,
        time_condition.to_json().encode("utf-8"),
        ritual_initiator.transacting_power,
    )
    assert signing_coordinator_agent.is_cohort_active(cohort_id)
    yield


def test_signature_publication(signing_coordinator_agent, cohort, cohort_id, dkg_size):
    print("==================== VERIFYING DKG FINALITY ====================")
    for ursula in cohort:
        assert (
            len(
                signing_coordinator_agent.get_signer(
                    cohort_id=cohort_id,
                    provider=ursula.checksum_address,
                ).signature
            )
            > 0
        ), "no signature found for ursula"

    assert len(signing_coordinator_agent.get_signing_cohort(cohort_id).conditions) > 0


def test_get_signers(
    nucypher_dependency,
    signing_coordinator_agent,
    cohort,
    cohort_id,
    dkg_size,
    ritual_initiator,
):
    signing_cohort = signing_coordinator_agent.get_signing_cohort(cohort_id)
    for i, signer in enumerate(signing_cohort.signers):
        assert signer.provider == cohort[i].checksum_address
        assert signer.signature

    assert len(signing_cohort.signers) == dkg_size

    # check deployed multisig
    expected_multisig_address = signing_cohort.multisig

    cohort_multisig = nucypher_dependency.ThresholdSigningMultisig.at(
        expected_multisig_address
    )
    operator_addresses = [u.operator_address for u in cohort]

    assert cohort_multisig.getSigners() == operator_addresses
    assert cohort_multisig.threshold() == len(cohort) - 1
    assert cohort_multisig.owner() == ritual_initiator.transacting_power.account


@pytest_twisted.inlineCallbacks
def test_signing_request_fulfilment(
    mocker,
    bob,
    accounts,
    signing_coordinator_agent,
    initiator,
    cohort_id,
    cohort,
    time_condition,
    nucypher_dependency
):
    print("==================== SIGNING REQUEST ====================")
    bob.start_learning_loop(now=True)
    data_to_sign = b"test_data"
    signing_cohort = signing_coordinator_agent.get_signing_cohort(cohort_id)
    signatures = yield bob.request_threshold_signatures(
        data_to_sign=data_to_sign,
        cohort_id=cohort_id,
        conditions=ConditionLingo(time_condition).to_dict(),
        ursulas=cohort,
        threshold=signing_cohort.threshold,
    )
    assert len(signatures) >= signing_cohort.threshold
    multisig = nucypher_dependency.ThresholdSigningMultisig.at(
        signing_cohort.multisig
    )
    result = multisig.isValidSignature(
        defunct_hash_message(data_to_sign),
        b''.join(signatures),
    )
    magic_value = EIP1271Auth.MAGIC_VALUE_BYTES
    assert result == magic_value, f"Invalid signature: {result} != {magic_value}"
    print("===================== SIGNING SUCCESSFUL =====================")
    yield
