import os
import pytest
from eth_account import Account
from eth_utils import keccak

from tests.mock.coordinator import MockCoordinatorV1


@pytest.fixture(scope='module')
def node_addresses():
    accounts = list()
    for _ in range(MockCoordinatorV1.DKG_SIZE):
        account = Account.create()
        accounts.append(account.address)
    return accounts


@pytest.fixture(scope='module')
def coordinator():
    return MockCoordinatorV1(
        transcripts_window=42,
        confirmations_window=42
    )


def test_mock_coordinator_creation(coordinator):
    assert coordinator.confirmations_window == 42
    assert coordinator.transcripts_window == 42
    assert len(coordinator.rituals) == 0
    assert coordinator.DKG_SIZE == 8


def test_mock_coordinator_round_0(node_addresses, coordinator):

    assert len(coordinator.rituals) == 0
    coordinator.initiate_ritual(nodes=node_addresses)
    assert len(coordinator.rituals) == 1

    assert coordinator.number_of_rituals() == 1

    ritual = coordinator.rituals[0]
    assert len(ritual.performances) == MockCoordinatorV1.DKG_SIZE
    for p in ritual.performances:
        assert p.confirmed_by == []
        assert p.transcript == bytes()

    assert len(coordinator.SIGNALS) == 1
    timestamp, signal = list(coordinator.SIGNALS.items())[0]
    signal_type, signal_data = signal
    assert signal_type == MockCoordinatorV1.Signal.START_RITUAL
    assert signal_data['ritual_id'] == 0
    assert set(signal_data['nodes']) == set(node_addresses)

    for index, node in enumerate(node_addresses):
        coordinator.checkin(ritual_id=0, node_index=index)

    assert len(coordinator.SIGNALS) == 2
    timestamp, signal = list(coordinator.SIGNALS.items())[1]
    signal_type, signal_data = signal
    assert signal_type == MockCoordinatorV1.Signal.START_TRANSCRIPT_ROUND
    assert signal_data['ritual_id'] == 0
    assert set(signal_data['nodes']) == set(node_addresses)


def test_mock_coordinator_round_1(node_addresses, coordinator):
    ritual = coordinator.rituals[0]
    assert ritual.status == MockCoordinatorV1.RitualStatus.WAITING_FOR_TRANSCRIPTS

    for p in ritual.performances:
        assert p.confirmed_by == []
        assert p.transcript == bytes()
        assert p.checkin_timestamp != 0

    for index, node in enumerate(node_addresses):
        transcript = os.urandom(16)
        coordinator.post_transcript(
            ritual_id=0,
            node_address=node,
            node_index=index,
            transcript=transcript
        )

        performance = ritual.performances[index]
        assert performance.confirmed_by == []
        assert performance.transcript == keccak(transcript)

        if index > len(node_addresses) - 1:
            assert len(coordinator.SIGNALS) == 2

    assert len(coordinator.SIGNALS) == 3
    timestamp, signal = list(coordinator.SIGNALS.items())[2]
    signal_type, signal_data = signal
    assert signal_type == MockCoordinatorV1.Signal.START_CONFIRMATION_ROUND
    assert signal_data['ritual_id'] == ritual.id
    assert set(signal_data['nodes']) == set(node_addresses)


def test_mock_coordinator_round_2(node_addresses, coordinator):
    ritual = coordinator.rituals[0]

    for p in ritual.performances:
        assert p.confirmed_by == []
        assert p.transcript != bytes()

    for index, node in enumerate(node_addresses):
        coordinator.post_confirmation(
            ritual_id=0,
            node_address=node_addresses[index],
            node_index=index,
            confirmed_node_indexes=list(range(MockCoordinatorV1.DKG_SIZE))
        )
        if index > len(node_addresses) - 1:
            assert len(coordinator.SIGNALS) == 3

    for p in ritual.performances:
        assert p.confirmed_by != []
        assert len(p.confirmed_by) == len(ritual.performances)
        assert p.transcript != bytes()

    assert ritual.status == MockCoordinatorV1.RitualStatus.COMPLETED
