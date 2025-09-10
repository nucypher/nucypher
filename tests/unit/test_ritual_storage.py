import pytest

from nucypher.blockchain.eth.models import (
    DKG_PHASE_1,
    DKG_PHASE_2,
    HANDOVER_AWAITING_BLINDED_SHARE,
    HANDOVER_AWAITING_TRANSCRIPT,
    SIGNING_AWAITING_SIGNATURES,
)
from nucypher.datastore.ritual import DKGStorage, SigningRitualStorage
from nucypher.types import PhaseId, PhaseNumber


@pytest.mark.parametrize("storage_class", [DKGStorage, SigningRitualStorage])
def test_store_for_non_existent_phase(storage_class, mocker):
    storage = storage_class()
    phase_id = PhaseId(ritual_id=1, phase=PhaseNumber(10000000))
    async_tx = mocker.Mock()
    with pytest.raises(ValueError):
        storage.store_ritual_phase_async_tx(phase_id, async_tx)


@pytest.mark.parametrize("storage_class", [DKGStorage, SigningRitualStorage])
def test_retrieve_for_non_existent_phase(storage_class):
    storage = storage_class()
    phase_id = PhaseId(ritual_id=1, phase=PhaseNumber(10000000))
    with pytest.raises(ValueError):
        storage.get_ritual_phase_async_tx(phase_id)


@pytest.mark.parametrize("storage_class", [DKGStorage, SigningRitualStorage])
def test_clear_for_non_existent_phase(storage_class, mocker):
    storage = storage_class()
    phase_id = PhaseId(ritual_id=1, phase=PhaseNumber(10000000))
    async_tx = mocker.Mock()
    with pytest.raises(ValueError):
        storage.clear_ritual_phase_async_tx(phase_id, async_tx)


@pytest.mark.parametrize(
    "storage_class, phase_numbers",
    [
        (
            DKGStorage,
            [
                DKG_PHASE_1,
                DKG_PHASE_2,
                HANDOVER_AWAITING_TRANSCRIPT,
                HANDOVER_AWAITING_BLINDED_SHARE,
            ],
        ),
        (SigningRitualStorage, [SIGNING_AWAITING_SIGNATURES]),
    ],
)
def test_store_and_get_async_tx(storage_class, phase_numbers, mocker):
    storage = storage_class()
    for phase_number in phase_numbers:
        phase_id = PhaseId(ritual_id=1, phase=PhaseNumber(phase_number))
        async_tx = mocker.Mock()
        storage.store_ritual_phase_async_tx(phase_id, async_tx)
        retrieved_tx = storage.get_ritual_phase_async_tx(phase_id)
        assert retrieved_tx == async_tx


@pytest.mark.parametrize(
    "storage_class, phase_numbers",
    [
        (
            DKGStorage,
            [
                DKG_PHASE_1,
                DKG_PHASE_2,
                HANDOVER_AWAITING_TRANSCRIPT,
                HANDOVER_AWAITING_BLINDED_SHARE,
            ],
        ),
        (SigningRitualStorage, [SIGNING_AWAITING_SIGNATURES]),
    ],
)
def test_store_and_clear_individual_async_tx(storage_class, phase_numbers, mocker):
    storage = storage_class()

    # add all phase entries
    for phase_number in phase_numbers:
        phase_id = PhaseId(ritual_id=1, phase=PhaseNumber(phase_number))
        async_tx = mocker.Mock()
        storage.store_ritual_phase_async_tx(phase_id, async_tx)
        retrieved_tx = storage.get_ritual_phase_async_tx(phase_id)
        assert retrieved_tx == async_tx

    i = len(phase_numbers) - 1
    while i >= 0:
        phase_number = phase_numbers[i]
        phase_id = PhaseId(ritual_id=1, phase=PhaseNumber(phase_number))
        async_tx = storage.get_ritual_phase_async_tx(phase_id)
        assert async_tx is not None

        # mismatched async tx does not clear
        mismatched_async_tx = mocker.Mock()
        cleared = storage.clear_ritual_phase_async_tx(phase_id, mismatched_async_tx)
        assert cleared is False

        # correct async tx clears
        cleared = storage.clear_ritual_phase_async_tx(phase_id, async_tx)
        assert cleared is True
        retrieved_tx = storage.get_ritual_phase_async_tx(phase_id)
        assert retrieved_tx is None

        # other phases (different phase number) unaffected by individual phase clearance
        for j in range(i):
            other_phase_number = phase_numbers[j]
            other_phase_id = PhaseId(ritual_id=1, phase=PhaseNumber(other_phase_number))
            other_async_tx = storage.get_ritual_phase_async_tx(other_phase_id)
            assert other_async_tx is not None

        i -= 1


@pytest.mark.parametrize(
    "storage_class, phase_numbers",
    [
        (
            DKGStorage,
            [
                DKG_PHASE_1,
                DKG_PHASE_2,
                HANDOVER_AWAITING_TRANSCRIPT,
                HANDOVER_AWAITING_BLINDED_SHARE,
            ],
        ),
        (SigningRitualStorage, [SIGNING_AWAITING_SIGNATURES]),
    ],
)
def test_store_and_clear_all_async_tx(storage_class, phase_numbers, mocker):
    storage = storage_class()
    ritual_id = 1
    for phase_number in phase_numbers:
        phase_id = PhaseId(ritual_id=ritual_id, phase=PhaseNumber(phase_number))
        async_tx = mocker.Mock()
        storage.store_ritual_phase_async_tx(phase_id, async_tx)
        retrieved_tx = storage.get_ritual_phase_async_tx(phase_id)
        assert retrieved_tx == async_tx

    # clear non-existent ritual_id
    storage.clear(ritual_id=2)

    # existing ritual id should still  be there
    for phase_number in phase_numbers:
        phase_id = PhaseId(ritual_id=ritual_id, phase=PhaseNumber(phase_number))
        retrieved_tx = storage.get_ritual_phase_async_tx(phase_id)
        assert retrieved_tx is not None

    storage.clear(ritual_id=ritual_id)
    for phase_number in phase_numbers:
        phase_id = PhaseId(ritual_id=ritual_id, phase=PhaseNumber(phase_number))
        retrieved_tx = storage.get_ritual_phase_async_tx(phase_id)
        assert retrieved_tx is None
