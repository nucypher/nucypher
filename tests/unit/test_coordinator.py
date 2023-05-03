import os
from collections import OrderedDict
from unittest.mock import Mock

import pytest
from eth_account import Account
from eth_utils import keccak
from ferveo_py import Keypair as FerveoKeypair

from tests.integration.blockchain.test_ritualist import FAKE_TRANSCRIPT
from tests.mock.coordinator import MockCoordinatorAgent
from tests.mock.interfaces import MockBlockchain

DKG_SIZE = 4


@pytest.fixture(scope='module')
def nodes_transacting_powers():
    accounts = OrderedDict()
    for _ in range(DKG_SIZE):
        account = Account.create()
        mock_transacting_power = Mock()
        mock_transacting_power.account = account.address
        accounts[account.address] = mock_transacting_power
    return accounts


@pytest.fixture(scope='module')
def coordinator():
    return MockCoordinatorAgent(blockchain=MockBlockchain())


def test_mock_coordinator_creation(coordinator):
    assert len(coordinator.rituals) == 0


def test_mock_coordinator_initiation(mocker, nodes_transacting_powers, coordinator, random_address):
    assert len(coordinator.rituals) == 0
    mock_transacting_power = mocker.Mock()
    mock_transacting_power.account = random_address
    coordinator.initiate_ritual(
        providers=list(nodes_transacting_powers.keys()),
        transacting_power=mock_transacting_power,
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
    assert signal_data["initiator"] == mock_transacting_power.account
    assert set(signal_data["participants"]) == nodes_transacting_powers.keys()


def test_mock_coordinator_round_1(nodes_transacting_powers, coordinator):
    ritual = coordinator.rituals[0]
    assert (
        coordinator.get_ritual_status(0)
        == MockCoordinatorAgent.RitualStatus.AWAITING_TRANSCRIPTS
    )

    for p in ritual.participants:
        assert p.transcript == bytes()

    for index, node_address in enumerate(nodes_transacting_powers):
        transcript = FAKE_TRANSCRIPT

        coordinator.post_transcript(
            ritual_id=0,
            transcript=transcript,
            transacting_power=nodes_transacting_powers[node_address]
        )

        performance = ritual.participants[index]
        assert performance.transcript == transcript

        if index == len(nodes_transacting_powers) - 1:
            assert len(coordinator.EVENTS) == 2

    timestamp, signal = list(coordinator.EVENTS.items())[1]
    signal_type, signal_data = signal
    assert signal_type == MockCoordinatorAgent.Events.START_AGGREGATION_ROUND
    assert signal_data["ritual_id"] == 0


def test_mock_coordinator_round_2(nodes_transacting_powers, coordinator):
    ritual = coordinator.rituals[0]
    assert (
        coordinator.get_ritual_status(0)
        == MockCoordinatorAgent.RitualStatus.AWAITING_AGGREGATIONS
    )

    for p in ritual.participants:
        assert p.transcript == FAKE_TRANSCRIPT

    aggregated_transcript = os.urandom(len(FAKE_TRANSCRIPT))
    public_key = FerveoKeypair.random().public_key()

    for index, node_address in enumerate(nodes_transacting_powers):
        coordinator.post_aggregation(
            ritual_id=0,
            aggregated_transcript=aggregated_transcript,
            public_key=public_key,
            transacting_power=nodes_transacting_powers[node_address]
        )
        if index == len(nodes_transacting_powers) - 1:
            assert len(coordinator.EVENTS) == 2

    assert ritual.aggregated_transcript == aggregated_transcript
    assert ritual.public_key == public_key
    for p in ritual.participants:
        # unchanged
        assert p.transcript == FAKE_TRANSCRIPT
        assert p.transcript != aggregated_transcript

    assert len(coordinator.EVENTS) == 2  # no additional event emitted here?
    assert (
        coordinator.get_ritual_status(0) == MockCoordinatorAgent.RitualStatus.FINALIZED
    )
