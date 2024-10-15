import pytest_twisted
from atxm.exceptions import Fault, InsufficientFunds
from twisted.internet import reactor
from twisted.internet.task import deferLater

from nucypher.blockchain.eth.models import PHASE1, PHASE2, Coordinator
from nucypher.types import PhaseId
from tests.mock.interfaces import MockBlockchain


@pytest_twisted.inlineCallbacks
def test_ursula_dkg_rounds_fault_tolerance(
    clock,
    ursulas,
    testerchain,
    ritual_token,
    fee_model,
    global_allow_list,
    coordinator_agent,
    accounts,
    initiator,
    mocker,
):
    #
    # DKG Setup
    #
    ursula_1, ursula_2 = ursulas[0], ursulas[1]
    cohort_addresses = sorted([ursula_1.checksum_address, ursula_2.checksum_address])
    initiate_dkg(
        accounts,
        initiator,
        testerchain,
        ritual_token,
        fee_model,
        global_allow_list,
        coordinator_agent,
        cohort_addresses,
    )
    ritual_id = 0

    # Round 1 (make issues occur)
    yield from perform_round_1_with_fault_tolerance(
        clock,
        mocker,
        testerchain,
        ritual_id,
        ursula_1,
        ursula_2,
        cohort_addresses,
        initiator,
    )

    # Round 2 (make issues occur)
    #  Use "ursula_2" to experience the problems; ursula_2 must be used to prevent
    #  having a `spy(spy(...))` for methods on ursula_1 since spies already utilized from round_1
    yield from perform_round_2_with_fault_tolerance(
        clock, mocker, coordinator_agent, ritual_id, testerchain, ursula_2, ursula_1
    )


def initiate_dkg(
    accounts,
    initiator,
    testerchain,
    ritual_token,
    fee_model,
    global_allow_list,
    coordinator_agent,
    cohort_addresses,
):
    duration = 24 * 60 * 60
    # Approve the ritual token for the coordinator agent to spend
    amount = fee_model.getRitualCost(len(cohort_addresses), duration)
    ritual_token.approve(
        fee_model.address,
        amount,
        sender=accounts[initiator.transacting_power.account],
    )
    receipt = coordinator_agent.initiate_ritual(
        fee_model=fee_model.address,
        providers=cohort_addresses,
        authority=initiator.transacting_power.account,
        duration=duration,
        access_controller=global_allow_list.address,
        transacting_power=initiator.transacting_power,
    )
    testerchain.time_travel(seconds=1)
    testerchain.wait_for_receipt(receipt["transactionHash"])


def perform_round_1_with_fault_tolerance(
    clock,
    mocker,
    testerchain,
    ritual_id,
    ursula_experiencing_problems,
    ursula_2,
    cohort_staking_provider_addresses,
    initiator,
):
    phase_id = PhaseId(ritual_id=ritual_id, phase=PHASE1)

    # pause machine so that txs don't actually get processed until the end
    testerchain.tx_machine.pause()
    assert len(testerchain.tx_machine.queued) == 0

    publish_transcript_spy = mocker.spy(
        ursula_experiencing_problems, "publish_transcript"
    )
    publish_aggregated_transcript_spy = mocker.spy(
        ursula_experiencing_problems, "publish_aggregated_transcript"
    )
    publish_transcript_call_count = 0
    assert (
        ursula_experiencing_problems.dkg_storage.get_ritual_phase_async_tx(phase_id)
        is None
    ), "nothing cached as yet"
    original_async_tx = ursula_experiencing_problems.perform_round_1(
        ritual_id=ritual_id,
        authority=initiator.transacting_power.account,
        participants=cohort_staking_provider_addresses,
        timestamp=testerchain.get_blocktime(),
    )
    publish_transcript_call_count += 1
    assert len(testerchain.tx_machine.queued) == 1
    assert (
        ursula_experiencing_problems.dkg_storage.get_ritual_phase_async_tx(phase_id)
        is original_async_tx
    )
    assert publish_transcript_spy.call_count == publish_transcript_call_count
    assert (
        publish_aggregated_transcript_spy.call_count == 0
    ), "phase 2 method never called"

    # calling again has no effect
    repeat_call_async_tx = ursula_experiencing_problems.perform_round_1(
        ritual_id=ritual_id,
        authority=initiator.transacting_power.account,
        participants=cohort_staking_provider_addresses,
        timestamp=testerchain.get_blocktime(),
    )
    assert repeat_call_async_tx is original_async_tx
    assert (
        publish_transcript_spy.call_count == publish_transcript_call_count
    ), "no change"
    assert (
        publish_aggregated_transcript_spy.call_count == 0
    ), "phase 2 method never called"

    # broadcast callback called - must mock existing tx since it wasn't actually broadcasted as yet
    mocked_pending_tx = mocker.Mock()
    mocked_pending_tx.params = original_async_tx.params
    mocked_pending_tx.id = original_async_tx.id
    mocked_pending_tx.txhash = MockBlockchain.FAKE_TX_HASH
    original_async_tx.on_broadcast(mocked_pending_tx)
    assert (
        publish_transcript_spy.call_count == publish_transcript_call_count
    ), "no change"
    assert (
        publish_aggregated_transcript_spy.call_count == 0
    ), "phase 2 method never called"
    assert len(testerchain.tx_machine.queued) == 1

    # insufficient funds callback called
    original_async_tx.on_insufficient_funds(original_async_tx, InsufficientFunds())
    assert (
        publish_transcript_spy.call_count == publish_transcript_call_count
    ), "no change"
    assert (
        publish_aggregated_transcript_spy.call_count == 0
    ), "phase 2 method never called"
    assert len(testerchain.tx_machine.queued) == 1

    # broadcast failure callback called
    # tx is explicitly removed and resubmitted by callback
    original_async_tx.on_broadcast_failure(original_async_tx, Exception())
    publish_transcript_call_count += 1  # on_fault should trigger resubmission
    assert (
        publish_transcript_spy.call_count == publish_transcript_call_count
    ), "updated call"
    assert (
        publish_aggregated_transcript_spy.call_count == 0
    ), "phase 2 method never called"
    resubmitted_after_broadcast_failure_async_tx = (
        ursula_experiencing_problems.dkg_storage.get_ritual_phase_async_tx(phase_id)
    )
    assert (
        resubmitted_after_broadcast_failure_async_tx is not original_async_tx
    ), "cache updated with resubmitted tx"
    assert len(testerchain.tx_machine.queued) == 1

    # on_fault callback called - this should cause a resubmission of tx because
    # tx was removed from atxm after faulting
    testerchain.tx_machine.remove_queued_transaction(
        resubmitted_after_broadcast_failure_async_tx
    )  # simulate removal from atxm
    assert len(testerchain.tx_machine.queued) == 0
    resubmitted_after_broadcast_failure_async_tx.fault = Fault.ERROR
    resubmitted_after_broadcast_failure_async_tx.error = None
    resubmitted_after_broadcast_failure_async_tx.on_fault(
        resubmitted_after_broadcast_failure_async_tx
    )
    publish_transcript_call_count += 1  # on_fault should trigger resubmission
    assert (
        publish_transcript_spy.call_count == publish_transcript_call_count
    ), "updated call"
    assert (
        publish_aggregated_transcript_spy.call_count == 0
    ), "phase 2 method never called"

    resubmitted_after_fault_async_tx = (
        ursula_experiencing_problems.dkg_storage.get_ritual_phase_async_tx(phase_id)
    )
    assert (
        resubmitted_after_fault_async_tx
        is not resubmitted_after_broadcast_failure_async_tx
    ), "cache updated with resubmitted tx"
    assert len(testerchain.tx_machine.queued) == 1

    # on_finalized (unsuccessful) callback called - this should cause a resubmission of tx because
    # tx was removed from atxm after faulting
    testerchain.tx_machine.remove_queued_transaction(
        resubmitted_after_fault_async_tx
    )  # simulate removal from atxm
    assert len(testerchain.tx_machine.queued) == 0
    resubmitted_after_fault_async_tx.successful = False
    resubmitted_after_fault_async_tx.on_finalized(resubmitted_after_fault_async_tx)
    publish_transcript_call_count += (
        1  # on_finalized (unsuccessful) should trigger resubmission
    )
    assert (
        publish_transcript_spy.call_count == publish_transcript_call_count
    ), "updated call"
    assert (
        publish_aggregated_transcript_spy.call_count == 0
    ), "phase 2 method never called"

    resubmitted_after_finalized_async_tx = (
        ursula_experiencing_problems.dkg_storage.get_ritual_phase_async_tx(phase_id)
    )
    assert (
        resubmitted_after_finalized_async_tx is not resubmitted_after_fault_async_tx
    ), "cache updated with resubmitted tx"
    assert len(testerchain.tx_machine.queued) == 1
    ursula_1_on_finalized_spy = mocker.spy(
        resubmitted_after_finalized_async_tx, "on_finalized"
    )
    assert ursula_1_on_finalized_spy.call_count == 0

    # have ursula_2 also submit their transcript
    ursula_2_async_tx = ursula_2.perform_round_1(
        ritual_id=ritual_id,
        authority=initiator.transacting_power.account,
        participants=cohort_staking_provider_addresses,
        timestamp=testerchain.get_blocktime(),
    )
    ursula_2_on_finalized_spy = mocker.spy(ursula_2_async_tx, "on_finalized")
    assert ursula_2_on_finalized_spy.call_count == 0

    testerchain.tx_machine.resume()  # resume processing
    interval = testerchain.tx_machine._task.interval

    # wait for txs to be processed
    while not all(
        tx in testerchain.tx_machine.finalized
        for tx in [resubmitted_after_finalized_async_tx, ursula_2_async_tx]
    ):
        yield clock.advance(interval)
        yield testerchain.time_travel(seconds=1)

    # wait for hooks to be called
    yield deferLater(reactor, 0.2, lambda: None)
    ursula_1_on_finalized_spy.assert_called_once_with(
        resubmitted_after_finalized_async_tx
    )
    ursula_2_on_finalized_spy.assert_called_once_with(ursula_2_async_tx)


def perform_round_2_with_fault_tolerance(
    clock,
    mocker,
    coordinator_agent,
    ritual_id,
    testerchain,
    ursula_experiencing_problems,
    ursula_2,
):
    # ensure we are actually in the 2nd round of the dkg process
    while (
        coordinator_agent.get_ritual_status(ritual_id=ritual_id)
        != Coordinator.RitualStatus.DKG_AWAITING_AGGREGATIONS
    ):
        yield testerchain.time_travel(seconds=1)

    phase_id = PhaseId(ritual_id=ritual_id, phase=PHASE2)

    # pause machine so that txs don't actually get processed until the end
    testerchain.tx_machine.pause()
    assert len(testerchain.tx_machine.queued) == 0

    publish_transcript_spy = mocker.spy(
        ursula_experiencing_problems, "publish_transcript"
    )
    publish_aggregated_transcript_spy = mocker.spy(
        ursula_experiencing_problems, "publish_aggregated_transcript"
    )
    publish_aggregated_transcript_call_count = 0
    assert (
        ursula_experiencing_problems.dkg_storage.get_ritual_phase_async_tx(phase_id)
        is None
    ), "nothing cached as yet"
    original_async_tx = ursula_experiencing_problems.perform_round_2(
        ritual_id=ritual_id, timestamp=testerchain.get_blocktime()
    )
    publish_aggregated_transcript_call_count += 1

    assert len(testerchain.tx_machine.queued) == 1
    assert (
        ursula_experiencing_problems.dkg_storage.get_ritual_phase_async_tx(phase_id)
        is original_async_tx
    )
    assert (
        publish_aggregated_transcript_spy.call_count
        == publish_aggregated_transcript_call_count
    )
    assert publish_transcript_spy.call_count == 0, "phase 1 method never called"

    # calling again has no effect
    repeat_call_async_tx = ursula_experiencing_problems.perform_round_2(
        ritual_id=ritual_id, timestamp=testerchain.get_blocktime()
    )
    assert repeat_call_async_tx is original_async_tx
    assert (
        publish_aggregated_transcript_spy.call_count
        == publish_aggregated_transcript_call_count
    ), "no change"
    assert publish_transcript_spy.call_count == 0, "phase 1 method never called"

    # broadcast callback called - must mock existing tx since it wasn't actually broadcasted as yet
    mocked_pending_tx = mocker.Mock()
    mocked_pending_tx.params = original_async_tx.params
    mocked_pending_tx.id = original_async_tx.id
    mocked_pending_tx.txhash = MockBlockchain.FAKE_TX_HASH
    original_async_tx.on_broadcast(mocked_pending_tx)
    assert (
        publish_aggregated_transcript_spy.call_count
        == publish_aggregated_transcript_call_count
    ), "no change"
    assert publish_transcript_spy.call_count == 0, "phase 1 method never called"
    assert len(testerchain.tx_machine.queued) == 1

    # insufficient funds callback called
    original_async_tx.on_insufficient_funds(original_async_tx, InsufficientFunds())
    assert (
        publish_aggregated_transcript_spy.call_count
        == publish_aggregated_transcript_call_count
    ), "no change"
    assert publish_transcript_spy.call_count == 0, "phase 1 method never called"
    assert len(testerchain.tx_machine.queued) == 1

    # broadcast failure callback called
    # tx is explicitly removed and resubmitted by callback
    original_async_tx.on_broadcast_failure(original_async_tx, Exception())
    publish_aggregated_transcript_call_count += (
        1  # on_fault should trigger resubmission
    )
    assert (
        publish_aggregated_transcript_spy.call_count
        == publish_aggregated_transcript_call_count
    ), "updated call"
    assert publish_transcript_spy.call_count == 0, "phase 1 method never called"
    resubmitted_after_broadcast_failure_async_tx = (
        ursula_experiencing_problems.dkg_storage.get_ritual_phase_async_tx(phase_id)
    )
    assert (
        resubmitted_after_broadcast_failure_async_tx is not original_async_tx
    ), "cache updated with resubmitted tx"
    assert len(testerchain.tx_machine.queued) == 1

    # on_fault callback called - this should cause a resubmission of tx because
    # tx was removed from atxm after faulting
    testerchain.tx_machine.remove_queued_transaction(
        resubmitted_after_broadcast_failure_async_tx
    )  # simulate removal from atxm
    assert len(testerchain.tx_machine.queued) == 0
    resubmitted_after_broadcast_failure_async_tx.fault = Fault.ERROR
    resubmitted_after_broadcast_failure_async_tx.error = None
    resubmitted_after_broadcast_failure_async_tx.on_fault(
        resubmitted_after_broadcast_failure_async_tx
    )
    publish_aggregated_transcript_call_count += (
        1  # on_fault should trigger resubmission
    )
    assert (
        publish_aggregated_transcript_spy.call_count
        == publish_aggregated_transcript_call_count
    ), "updated call"
    assert publish_transcript_spy.call_count == 0, "phase 1 method never called"

    resubmitted_after_fault_async_tx = (
        ursula_experiencing_problems.dkg_storage.get_ritual_phase_async_tx(phase_id)
    )
    assert (
        resubmitted_after_fault_async_tx
        is not resubmitted_after_broadcast_failure_async_tx
    ), "cache updated with resubmitted tx"
    assert len(testerchain.tx_machine.queued) == 1

    # on_finalized (unsuccessful) callback called - this should cause a resubmission of tx because
    # tx was removed from atxm after faulting
    testerchain.tx_machine.remove_queued_transaction(
        resubmitted_after_fault_async_tx
    )  # simulate removal from atxm
    assert len(testerchain.tx_machine.queued) == 0
    resubmitted_after_fault_async_tx.successful = False
    resubmitted_after_fault_async_tx.on_finalized(resubmitted_after_fault_async_tx)
    publish_aggregated_transcript_call_count += (
        1  # on_finalized (unsuccessful) should trigger resubmission
    )
    assert (
        publish_aggregated_transcript_spy.call_count
        == publish_aggregated_transcript_call_count
    ), "updated call"
    assert publish_transcript_spy.call_count == 0, "phase 1 method never called"

    resubmitted_after_finalized_async_tx = (
        ursula_experiencing_problems.dkg_storage.get_ritual_phase_async_tx(phase_id)
    )
    assert (
        resubmitted_after_finalized_async_tx is not resubmitted_after_fault_async_tx
    ), "cache updated with resubmitted tx"
    assert len(testerchain.tx_machine.queued) == 1
    ursula_1_on_finalized_spy = mocker.spy(
        resubmitted_after_finalized_async_tx, "on_finalized"
    )
    assert ursula_1_on_finalized_spy.call_count == 0

    # have ursula_2 also submit their transcript
    ursula_2_async_tx = ursula_2.perform_round_2(
        ritual_id=ritual_id, timestamp=testerchain.get_blocktime()
    )
    ursula_2_on_finalized_spy = mocker.spy(ursula_2_async_tx, "on_finalized")
    assert ursula_2_on_finalized_spy.call_count == 0

    testerchain.tx_machine.resume()  # resume processing
    interval = testerchain.tx_machine._task.interval

    # wait for txs to be processed
    while not all(
        tx in testerchain.tx_machine.finalized
        for tx in [resubmitted_after_finalized_async_tx, ursula_2_async_tx]
    ):
        yield clock.advance(interval)
        yield testerchain.time_travel(seconds=1)

    # wait for hooks to be called
    yield deferLater(reactor, 0.2, lambda: None)
    ursula_1_on_finalized_spy.assert_called_once_with(
        resubmitted_after_finalized_async_tx
    )
    ursula_2_on_finalized_spy.assert_called_once_with(ursula_2_async_tx)

    # ensure ritual is successfully completed
    assert (
        coordinator_agent.get_ritual_status(ritual_id=ritual_id)
        == Coordinator.RitualStatus.ACTIVE
    )
