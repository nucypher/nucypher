import pytest
import pytest_twisted

from nucypher.blockchain.eth.models import SigningCoordinator


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


def test_signing_cohort_initiation(
    signing_coordinator_agent,
    accounts,
    initiator,
    cohort,
    testerchain,
    cohort_id,
    duration,
):
    print("==================== INITIALIZING ====================")
    cohort_staking_provider_addresses = list(u.checksum_address for u in cohort)

    receipt = signing_coordinator_agent.initiate_signing_cohort(
        authority=initiator.transacting_power.account,
        providers=cohort_staking_provider_addresses,
        threshold=len(cohort_staking_provider_addresses) - 1,
        duration=duration,
        transacting_power=initiator.transacting_power,
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
    signing_coordinator_agent, cohort_id, cohort, clock, interval, testerchain
):
    print("==================== AWAITING COHORT FINALITY ====================")
    while not signing_coordinator_agent.is_cohort_active(cohort_id):
        yield clock.advance(interval)
        yield testerchain.time_travel(seconds=1)

    testerchain.tx_machine.stop()
    assert not testerchain.tx_machine.running

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


def test_get_signers(signing_coordinator_agent, cohort, cohort_id, dkg_size):
    signing_cohort = signing_coordinator_agent.get_signing_cohort(cohort_id)
    for i, signer in enumerate(signing_cohort.signers):
        assert signer.provider == cohort[i].checksum_address
        assert signer.signature

    assert len(signing_cohort.signers) == dkg_size
