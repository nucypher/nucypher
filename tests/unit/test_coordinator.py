from collections import OrderedDict
from unittest.mock import Mock

import pytest
from nucypher_core import SessionStaticSecret

from tests.mock.coordinator import MockCoordinatorAgent
from tests.mock.interfaces import MockBlockchain
from tests.utils.blockchain import TestAccount

DKG_SIZE = 4


@pytest.fixture(scope='module')
def nodes_wallets():
    accounts = OrderedDict()
    for _ in range(DKG_SIZE):
        account = TestAccount.random()
        mock_wallet = Mock()
        mock_wallet.address = account.address
        accounts[account.address] = mock_wallet
    return accounts


@pytest.fixture(scope='module')
def coordinator():
    return MockCoordinatorAgent(blockchain=MockBlockchain())


def test_mock_coordinator_creation(coordinator):
    assert len(coordinator.rituals) == 0


def test_mock_coordinator_initiation(
    mocker,
    nodes_wallets,
    coordinator,
    random_address,
    get_random_checksum_address,
):
    assert len(coordinator.rituals) == 0
    mock_wallet = mocker.Mock()
    mock_wallet.address = random_address
    coordinator.initiate_ritual(
        providers=list(nodes_wallets.keys()),
        authority=mock_wallet.address,
        duration=1,
        access_controller=get_random_checksum_address(),
        wallet=mock_wallet,
    )
    assert len(coordinator.rituals) == 1

    assert coordinator.number_of_rituals() == 1

    ritual = coordinator.rituals[0]
    assert len(ritual.participants) == DKG_SIZE
    for p in ritual.participants:
        assert p.transcript == bytes()

    assert len(coordinator.EVENTS) == 1

    timestamp, signal = list(coordinator.EVENTS.items())[0]
    signal_type, signal_data = signal
    assert signal_type == MockCoordinatorAgent.Events.START_RITUAL
    assert signal_data["ritual_id"] == 0
    assert signal_data["authority"] == mock_wallet.address
    assert set(signal_data["participants"]) == nodes_wallets.keys()


def test_mock_coordinator_round_1(
    nodes_wallets, coordinator, random_transcript
):
    ritual = coordinator.rituals[0]
    assert (
        coordinator.get_ritual_status(0)
        == MockCoordinatorAgent.RitualStatus.DKG_AWAITING_TRANSCRIPTS
    )

    for p in ritual.participants:
        assert p.transcript == bytes()

    for index, node_address in enumerate(nodes_wallets):
        transcript = random_transcript

        coordinator.post_transcript(
            ritual_id=0,
            transcript=transcript,
            wallet=nodes_wallets[node_address]
        )

        performance = ritual.participants[index]
        assert performance.transcript == bytes(transcript)

        if index == len(nodes_wallets) - 1:
            assert len(coordinator.EVENTS) == 2

    timestamp, signal = list(coordinator.EVENTS.items())[1]
    signal_type, signal_data = signal
    assert signal_type == MockCoordinatorAgent.Events.START_AGGREGATION_ROUND
    assert signal_data["ritual_id"] == 0


def test_mock_coordinator_round_2(
    nodes_wallets,
    coordinator,
    aggregated_transcript,
    dkg_public_key,
    random_transcript,
):
    ritual = coordinator.rituals[0]
    assert (
        coordinator.get_ritual_status(0)
        == MockCoordinatorAgent.RitualStatus.DKG_AWAITING_AGGREGATIONS
    )

    for p in ritual.participants:
        assert p.transcript == bytes(random_transcript)

    participant_public_keys = []
    for index, node_address in enumerate(nodes_wallets):
        participant_public_key = SessionStaticSecret.random().public_key()
        coordinator.post_aggregation(
            ritual_id=0,
            aggregated_transcript=aggregated_transcript,
            public_key=dkg_public_key,
            participant_public_key=participant_public_key,
            wallet=nodes_wallets[node_address]
        )
        participant_public_keys.append(participant_public_key)
        if index == len(nodes_wallets) - 1:
            assert len(coordinator.EVENTS) == 2

    assert ritual.aggregated_transcript == bytes(aggregated_transcript)

    assert bytes(ritual.public_key) == bytes(dkg_public_key)
    for index, p in enumerate(ritual.participants):
        # unchanged
        assert p.transcript == bytes(random_transcript)
        assert p.transcript != bytes(aggregated_transcript)
    assert p.decryption_request_static_key == bytes(participant_public_keys[index])

    assert len(coordinator.EVENTS) == 2  # no additional event emitted here?
    assert coordinator.get_ritual_status(0) == MockCoordinatorAgent.RitualStatus.ACTIVE
