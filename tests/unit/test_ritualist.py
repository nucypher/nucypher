from unittest.mock import patch

import pytest
from atxm.exceptions import Fault, InsufficientFunds

from nucypher.blockchain.eth.agents import CoordinatorAgent
from nucypher.blockchain.eth.models import PHASE1, PHASE2, Coordinator
from nucypher.crypto.powers import RitualisticPower
from nucypher.types import PhaseId
from tests.constants import MOCK_ETH_PROVIDER_URI
from tests.mock.coordinator import MockCoordinatorAgent
from tests.mock.interfaces import MockBlockchain


@pytest.fixture(scope="module")
def agent(mock_contract_agency, ursulas) -> MockCoordinatorAgent:
    coordinator_agent: CoordinatorAgent = mock_contract_agency.get_agent(
        CoordinatorAgent, registry=None, blockchain_endpoint=MOCK_ETH_PROVIDER_URI
    )

    def mock_get_provider_public_key(provider, ritual_id):
        for ursula in ursulas:
            if ursula.checksum_address == provider:
                return ursula.public_keys(RitualisticPower)

    coordinator_agent.post_transcript = lambda *a, **kw: MockBlockchain.mock_async_tx()
    coordinator_agent.post_aggregation = lambda *a, **kw: MockBlockchain.mock_async_tx()
    coordinator_agent.get_provider_public_key = mock_get_provider_public_key
    return coordinator_agent


@pytest.fixture(scope="module")
def ursula(ursulas):
    return ursulas[1]


@pytest.fixture(scope="module")
def cohort(ursulas):
    return [u.staking_provider_address for u in ursulas[:4]]


@pytest.fixture(scope="module")
def transacting_power(alice):
    return alice.transacting_power


def test_initiate_ritual(
    agent: CoordinatorAgent, cohort, transacting_power, get_random_checksum_address
):
    # any value will do
    global_allow_list = get_random_checksum_address()
    fee_model = get_random_checksum_address()

    duration = 100
    receipt = agent.initiate_ritual(
        fee_model=fee_model,
        authority=transacting_power.account,
        access_controller=global_allow_list,
        providers=cohort,
        duration=duration,
        transacting_power=transacting_power,
    )

    participants = [
        Coordinator.Participant(
            provider=c,
        )
        for i, c in enumerate(cohort)
    ]

    init_timestamp = 123456
    end_timestamp = init_timestamp + duration
    number_of_rituals = agent.number_of_rituals()
    ritual_id = number_of_rituals - 1
    ritual = Coordinator.Ritual(
        id=ritual_id,
        initiator=transacting_power.account,
        authority=transacting_power.account,
        access_controller=global_allow_list,
        dkg_size=4,
        threshold=MockCoordinatorAgent.get_threshold_for_ritual_size(dkg_size=4),
        init_timestamp=123456,
        end_timestamp=end_timestamp,
        participants=participants,
        fee_model=fee_model,
    )
    agent.get_ritual = lambda *args, **kwargs: ritual

    assert receipt["transactionHash"]
    return ritual_id


def test_perform_round_1(
    ursula,
    random_address,
    cohort,
    agent,
    random_transcript,
    get_random_checksum_address,
):
    participants = dict()
    for i, checksum_address in enumerate(cohort):
        participants[checksum_address] = Coordinator.Participant(
            provider=checksum_address,
        )

    init_timestamp = 123456
    end_timestamp = init_timestamp + 100
    ritual = Coordinator.Ritual(
        id=0,
        initiator=random_address,
        authority=random_address,
        access_controller=get_random_checksum_address(),
        dkg_size=4,
        threshold=MockCoordinatorAgent.get_threshold_for_ritual_size(dkg_size=4),
        init_timestamp=init_timestamp,
        end_timestamp=end_timestamp,
        total_transcripts=4,
        participants=list(participants.values()),
        fee_model=get_random_checksum_address(),
    )
    agent.get_ritual = lambda *args, **kwargs: ritual
    agent.get_participant = lambda ritual_id, provider, transcript: participants[
        provider
    ]

    # ensure no operation performed for non-application-state
    non_application_states = [
        Coordinator.RitualStatus.NON_INITIATED,
        Coordinator.RitualStatus.DKG_AWAITING_AGGREGATIONS,
        Coordinator.RitualStatus.ACTIVE,
        Coordinator.RitualStatus.EXPIRED,
        Coordinator.RitualStatus.DKG_TIMEOUT,
        Coordinator.RitualStatus.DKG_INVALID,
    ]
    for state in non_application_states:
        agent.get_ritual_status = lambda *args, **kwargs: state
        result = ursula.perform_round_1(
            ritual_id=0, authority=random_address, participants=cohort, timestamp=0
        )
        assert result is None  # no execution performed

    # set correct state
    agent.get_ritual_status = (
        lambda *args, **kwargs: Coordinator.RitualStatus.DKG_AWAITING_TRANSCRIPTS
    )

    # cryptographic issue does not raise exception
    with patch(
        "nucypher.crypto.ferveo.dkg.generate_transcript",
        side_effect=Exception("transcript cryptography failed"),
    ):
        async_tx = ursula.perform_round_1(
            ritual_id=0, authority=random_address, participants=cohort, timestamp=0
        )
        # exception not raised, but None returned
        assert async_tx is None

    phase_id = PhaseId(ritual_id=0, phase=PHASE1)
    assert (
        ursula.dkg_storage.get_ritual_phase_async_tx(phase_id=phase_id) is None
    ), "no tx data as yet"

    async_tx = ursula.perform_round_1(
        ritual_id=0, authority=random_address, participants=cohort, timestamp=0
    )

    # ensure tx is tracked
    assert async_tx
    assert ursula.dkg_storage.get_ritual_phase_async_tx(phase_id=phase_id) is async_tx

    # try again
    async_tx2 = ursula.perform_round_1(
        ritual_id=0, authority=random_address, participants=cohort, timestamp=0
    )

    assert async_tx2 is async_tx
    assert ursula.dkg_storage.get_ritual_phase_async_tx(phase_id=phase_id) is async_tx2

    # participant already posted transcript
    participant = agent.get_participant(
        ritual_id=0, provider=ursula.checksum_address, transcript=False
    )
    participant.transcript = bytes(random_transcript)
    # try submitting again
    result = ursula.perform_round_1(
        ritual_id=0, authority=random_address, participants=cohort, timestamp=0
    )
    assert result is None

    # participant no longer already posted aggregated transcript
    participant.transcript = bytes()
    async_tx3 = ursula.perform_round_1(
        ritual_id=0, authority=random_address, participants=cohort, timestamp=0
    )

    assert async_tx3 is async_tx
    assert ursula.dkg_storage.get_ritual_phase_async_tx(phase_id=phase_id) is async_tx3


def test_perform_round_2(
    ursula,
    cohort,
    transacting_power,
    agent,
    mocker,
    random_transcript,
    get_random_checksum_address,
):
    participants = dict()
    for i, checksum_address in enumerate(cohort):
        participant = Coordinator.Participant(
            transcript=bytes(random_transcript),
            provider=checksum_address,
        )

        participants[checksum_address] = participant

    init_timestamp = 123456
    end_timestamp = init_timestamp + 100

    ritual = Coordinator.Ritual(
        id=0,
        initiator=transacting_power.account,
        authority=transacting_power.account,
        access_controller=get_random_checksum_address(),
        dkg_size=len(cohort),
        threshold=MockCoordinatorAgent.get_threshold_for_ritual_size(
            dkg_size=len(cohort)
        ),
        init_timestamp=init_timestamp,
        end_timestamp=end_timestamp,
        total_transcripts=len(cohort),
        participants=list(participants.values()),
        fee_model=get_random_checksum_address(),
    )

    agent.get_ritual = lambda *args, **kwargs: ritual
    agent.get_participant = lambda ritual_id, provider, transcript: participants[
        provider
    ]

    # ensure no operation performed for non-application-state
    non_application_states = [
        Coordinator.RitualStatus.NON_INITIATED,
        Coordinator.RitualStatus.DKG_AWAITING_TRANSCRIPTS,
        Coordinator.RitualStatus.ACTIVE,
        Coordinator.RitualStatus.EXPIRED,
        Coordinator.RitualStatus.DKG_TIMEOUT,
        Coordinator.RitualStatus.DKG_INVALID,
    ]
    for state in non_application_states:
        agent.get_ritual_status = lambda *args, **kwargs: state
        ursula.perform_round_2(ritual_id=0, timestamp=0)

    phase_1_id = PhaseId(ritual_id=0, phase=PHASE1)
    assert ursula.dkg_storage.get_ritual_phase_async_tx(phase_1_id) is not None

    # set correct state
    agent.get_ritual_status = (
        lambda *args, **kwargs: Coordinator.RitualStatus.DKG_AWAITING_AGGREGATIONS
    )

    # cryptographic issue does not raise exception
    with patch(
        "nucypher.crypto.ferveo.dkg.verify_aggregate",
        side_effect=Exception("aggregate cryptography failed"),
    ):
        async_tx = ursula.perform_round_2(ritual_id=0, timestamp=0)
        # exception not raised, but None returned
        assert async_tx is None

    phase_2_id = PhaseId(ritual_id=0, phase=PHASE2)
    assert (
        ursula.dkg_storage.get_ritual_phase_async_tx(phase_id=phase_2_id) is None
    ), "no tx data as yet"

    mocker.patch("nucypher.crypto.ferveo.dkg.verify_aggregate")
    async_tx = ursula.perform_round_2(ritual_id=0, timestamp=0)

    # check async tx tracking
    assert ursula.dkg_storage.get_ritual_phase_async_tx(phase_2_id) is async_tx
    assert (
        ursula.dkg_storage.get_ritual_phase_async_tx(phase_1_id) is not async_tx
    ), "phase 1 separate from phase 2"

    # trying again yields same tx
    async_tx2 = ursula.perform_round_2(ritual_id=0, timestamp=0)
    assert async_tx2 is async_tx
    assert ursula.dkg_storage.get_ritual_phase_async_tx(phase_2_id) is async_tx2

    # No action required
    participant = agent.get_participant(
        ritual_id=0, provider=ursula.checksum_address, transcript=False
    )
    participant.aggregated = True
    result = ursula.perform_round_2(ritual_id=0, timestamp=0)
    assert result is None

    # Action required but async tx already fired
    participant.aggregated = False
    async_tx4 = ursula.perform_round_2(ritual_id=0, timestamp=0)
    assert async_tx4 is async_tx
    assert ursula.dkg_storage.get_ritual_phase_async_tx(phase_2_id) is async_tx4


def test_async_tx_hooks_phase_1(ursula, mocker):
    ritual_id = 0
    transcript = mocker.Mock()
    phase_id = PhaseId(ritual_id=ritual_id, phase=PHASE1)

    mock_publish_transcript = mocker.Mock()
    mocker.patch.object(ursula, "publish_transcript", mock_publish_transcript)

    mock_publish_aggregated_transcript = mocker.Mock()
    mocker.patch.object(
        ursula, "publish_aggregated_transcript", mock_publish_aggregated_transcript
    )

    async_tx_hooks = ursula._setup_async_hooks(phase_id, ritual_id, transcript)
    mock_tx = mocker.Mock()
    mock_tx.id = 1
    mock_tx.params = MockBlockchain.FAKE_TX_PARAMS

    resubmit_call_count = 0

    # broadcast - just logging
    mock_tx.txhash = MockBlockchain.FAKE_TX_HASH
    async_tx_hooks.on_broadcast(mock_tx)
    assert mock_publish_transcript.call_count == 0
    assert (
        mock_publish_aggregated_transcript.call_count == 0
    ), "phase 2 publish never called"

    # insufficient funds - just logging
    async_tx_hooks.on_insufficient_funds(mock_tx, InsufficientFunds())
    assert mock_publish_transcript.call_count == resubmit_call_count, "no change"
    assert (
        mock_publish_aggregated_transcript.call_count == 0
    ), "phase 2 publish never called"

    #
    # With resubmitted tx
    #
    mocker.patch.object(ursula, "_is_phase_1_action_required", return_value=True)

    # broadcast failure
    async_tx_hooks.on_broadcast_failure(mock_tx, Exception("test"))
    resubmit_call_count += 1
    assert mock_publish_transcript.call_count == resubmit_call_count, "tx resubmitted"
    mock_publish_transcript.assert_called_with(ritual_id, transcript)
    assert (
        mock_publish_aggregated_transcript.call_count == 0
    ), "phase 2 publish never called"

    # fault
    mock_tx.fault = Fault.ERROR
    mock_tx.error = "fault error"
    async_tx_hooks.on_fault(mock_tx)
    resubmit_call_count += 1
    assert mock_publish_transcript.call_count == resubmit_call_count, "tx resubmitted"
    mock_publish_transcript.assert_called_with(ritual_id, transcript)
    assert (
        mock_publish_aggregated_transcript.call_count == 0
    ), "phase 2 publish never called"

    clear_ritual_spy = mocker.spy(ursula.dkg_storage, "clear_ritual_phase_async_tx")

    # finalized - unsuccessful
    mock_tx.successful = False
    async_tx_hooks.on_finalized(mock_tx)
    resubmit_call_count += 1
    assert mock_publish_transcript.call_count == resubmit_call_count, "tx resubmitted"
    mock_publish_transcript.assert_called_with(ritual_id, transcript)
    assert clear_ritual_spy.call_count == 0, "not called because unsuccessful"
    assert (
        mock_publish_aggregated_transcript.call_count == 0
    ), "phase 2 publish never called"

    # finalized - successful
    mock_tx.successful = True
    async_tx_hooks.on_finalized(mock_tx)
    assert (
        mock_publish_transcript.call_count == resubmit_call_count
    ), "no change because successful"
    clear_ritual_spy.assert_called_once_with(
        phase_id, mock_tx
    ), "cleared tx because successful"
    assert (
        mock_publish_aggregated_transcript.call_count == 0
    ), "phase 2 publish never called"

    #
    # Without resubmitted tx
    #
    mocker.patch.object(ursula, "_is_phase_1_action_required", return_value=False)
    current_call_count = mock_publish_transcript.call_count

    async_tx_hooks.on_broadcast_failure(mock_tx, Exception("test"))
    assert (
        mock_publish_transcript.call_count == current_call_count
    ), "no action needed, so not called"

    async_tx_hooks.on_fault(mock_tx)
    assert (
        mock_publish_transcript.call_count == current_call_count
    ), "no action needed, so not called"

    mock_tx.successful = True
    async_tx_hooks.on_finalized(mock_tx)
    assert (
        mock_publish_transcript.call_count == current_call_count
    ), "no action needed, so not called"

    mock_tx.successful = False
    async_tx_hooks.on_finalized(mock_tx)
    assert (
        mock_publish_transcript.call_count == current_call_count
    ), "no action needed, so not called"


def test_async_tx_hooks_phase_2(ursula, mocker, aggregated_transcript, dkg_public_key):
    ritual_id = 0
    aggregated_transcript = aggregated_transcript
    public_key = dkg_public_key
    phase_id = PhaseId(ritual_id=ritual_id, phase=PHASE2)

    mock_publish_transcript = mocker.Mock()
    mocker.patch.object(ursula, "publish_transcript", mock_publish_transcript)

    mock_publish_aggregated_transcript = mocker.Mock()
    mocker.patch.object(
        ursula, "publish_aggregated_transcript", mock_publish_aggregated_transcript
    )

    async_tx_hooks = ursula._setup_async_hooks(
        phase_id, ritual_id, aggregated_transcript, public_key
    )
    mock_tx = mocker.Mock()
    mock_tx.id = 1
    mock_tx.params = MockBlockchain.FAKE_TX_PARAMS

    resubmit_call_count = 0

    # broadcast - just logging
    mock_tx.txhash = MockBlockchain.FAKE_TX_HASH
    async_tx_hooks.on_broadcast(mock_tx)
    assert mock_publish_transcript.call_count == 0
    assert (
        mock_publish_aggregated_transcript.call_count == 0
    ), "phase 2 publish never called"

    # insufficient funds - just logging
    async_tx_hooks.on_insufficient_funds(mock_tx, InsufficientFunds())
    assert (
        mock_publish_aggregated_transcript.call_count == resubmit_call_count
    ), "no change"
    assert mock_publish_transcript.call_count == 0, "phase 1 publish never called"

    #
    # With resubmitted tx
    #
    mocker.patch.object(ursula, "_is_phase_2_action_required", return_value=True)

    # broadcast failure
    async_tx_hooks.on_broadcast_failure(mock_tx, Exception("test"))
    resubmit_call_count += 1
    assert (
        mock_publish_aggregated_transcript.call_count == resubmit_call_count
    ), "tx resubmitted"
    mock_publish_aggregated_transcript.assert_called_with(
        ritual_id, aggregated_transcript, public_key
    )
    assert mock_publish_transcript.call_count == 0, "phase 1 publish never called"

    # fault
    mock_tx.fault = Fault.TIMEOUT
    mock_tx.error = "fault error"
    async_tx_hooks.on_fault(mock_tx)
    resubmit_call_count += 1
    assert (
        mock_publish_aggregated_transcript.call_count == resubmit_call_count
    ), "tx resubmitted"
    mock_publish_aggregated_transcript.assert_called_with(
        ritual_id, aggregated_transcript, public_key
    )
    assert mock_publish_transcript.call_count == 0, "phase 1 publish never called"

    clear_ritual_spy = mocker.spy(ursula.dkg_storage, "clear_ritual_phase_async_tx")

    # finalized - unsuccessful
    mock_tx.successful = False
    async_tx_hooks.on_finalized(mock_tx)
    resubmit_call_count += 1
    assert (
        mock_publish_aggregated_transcript.call_count == resubmit_call_count
    ), "tx resubmitted"
    mock_publish_aggregated_transcript.assert_called_with(
        ritual_id, aggregated_transcript, public_key
    )
    assert clear_ritual_spy.call_count == 0, "not called because unsuccessful"
    assert mock_publish_transcript.call_count == 0, "phase 1 publish never called"

    # finalized - successful
    mock_tx.successful = True
    async_tx_hooks.on_finalized(mock_tx)
    assert (
        mock_publish_aggregated_transcript.call_count == resubmit_call_count
    ), "no change because successful"
    clear_ritual_spy.assert_called_once_with(
        phase_id, mock_tx
    ), "cleared tx because successful"
    assert mock_publish_transcript.call_count == 0, "phase 1 publish never called"

    #
    # Without resubmitted tx
    #
    mocker.patch.object(ursula, "_is_phase_2_action_required", return_value=False)
    current_call_count = mock_publish_transcript.call_count

    async_tx_hooks.on_broadcast_failure(mock_tx, Exception("test"))
    assert (
        mock_publish_transcript.call_count == current_call_count
    ), "no action needed, so not called"

    async_tx_hooks.on_fault(mock_tx)
    assert (
        mock_publish_transcript.call_count == current_call_count
    ), "no action needed, so not called"

    mock_tx.successful = True
    async_tx_hooks.on_finalized(mock_tx)
    assert (
        mock_publish_transcript.call_count == current_call_count
    ), "no action needed, so not called"

    mock_tx.successful = False
    async_tx_hooks.on_finalized(mock_tx)
    assert (
        mock_publish_transcript.call_count == current_call_count
    ), "no action needed, so not called"
