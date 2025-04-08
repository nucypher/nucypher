import pytest
import pytest_twisted
from twisted.logger import globalLogPublisher

from nucypher.blockchain.eth.models import Coordinator
from nucypher.blockchain.eth.signers import InMemorySigner
from nucypher.crypto.keypairs import RitualisticKeypair
from nucypher.crypto.powers import RitualisticPower
from nucypher.utilities.warnings import render_ferveo_key_mismatch_warning


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
def cohort(testerchain, clock, coordinator_agent, ursulas, dkg_size):
    nodes = list(sorted(ursulas[:dkg_size], key=lambda x: int(x.checksum_address, 16)))
    assert len(nodes) == dkg_size
    for node in nodes:
        node.ritual_tracker.task._task.clock = clock
        node.ritual_tracker.start()
    return nodes


@pytest_twisted.inlineCallbacks
def test_dkg_failure_with_ferveo_key_mismatch(
    coordinator_agent,
    ritual_id,
    cohort,
    clock,
    interval,
    testerchain,
    initiator,
    fee_model,
    global_allow_list,
    duration,
    accounts,
    ritual_token,
):

    bad_ursula = cohort[0]
    old_public_key = bad_ursula.public_keys(RitualisticPower)
    new_keypair = RitualisticKeypair()
    new_public_key = new_keypair.pubkey

    bad_ursula._crypto_power._CryptoPower__power_ups[RitualisticPower].keypair = (
        new_keypair
    )

    assert bytes(old_public_key) != bytes(new_public_key)
    assert bytes(old_public_key) != bytes(bad_ursula.public_keys(RitualisticPower))
    assert bytes(new_public_key) == bytes(bad_ursula.public_keys(RitualisticPower))

    onchain_public_key = coordinator_agent.get_provider_public_key(
        ritual_id=ritual_id, provider=bad_ursula.checksum_address
    )

    assert bytes(onchain_public_key) == bytes(old_public_key)
    assert bytes(onchain_public_key) != bytes(new_public_key)
    assert bytes(onchain_public_key) != bytes(bad_ursula.public_keys(RitualisticPower))
    print(f"BAD URSULA: {bad_ursula.checksum_address}")

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

    log_messages = []

    def log_trapper(event):
        log_messages.append(event["log_format"])

    globalLogPublisher.addObserver(log_trapper)

    print(
        "==================== AWAITING DKG FAILURE (FERVEO MISMATCH) ===================="
    )
    while (
        coordinator_agent.get_ritual_status(ritual_id)
        != Coordinator.RitualStatus.DKG_TIMEOUT
    ):
        # remains in awaiting transcripts because of the one bad ursula not submitting transcript
        assert (
            coordinator_agent.get_ritual_status(ritual_id)
            == Coordinator.RitualStatus.DKG_AWAITING_TRANSCRIPTS
        )
        yield clock.advance(interval)
        yield testerchain.time_travel(
            seconds=coordinator_agent.get_timeout() // 6
        )  # min. 6 rounds before timeout

    assert (
        render_ferveo_key_mismatch_warning(
            bytes(new_public_key), bytes(onchain_public_key)
        )
        in log_messages
    )

    for ursula in cohort:
        participant = coordinator_agent.get_participant(
            ritual_id, ursula.checksum_address, True
        )
        if ursula.checksum_address == bad_ursula.checksum_address:
            assert (
                not participant.transcript
            ), "transcript not submitted due to mismatched ferveo key"
        else:
            assert participant.transcript, "transcript submitted"

    testerchain.tx_machine.stop()
    assert not testerchain.tx_machine.running
    globalLogPublisher.removeObserver(log_trapper)
