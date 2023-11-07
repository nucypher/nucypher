import pytest

from nucypher.blockchain.eth.agents import StakingProvidersReservoir
from nucypher.policy.reservoir import MergedReservoir, PrefetchStrategy


def test_empty_reservoir():
    merged_reservoir = MergedReservoir(
        values=[], reservoir=StakingProvidersReservoir({})
    )
    assert len(merged_reservoir) == 0
    next_address = merged_reservoir()
    assert next_address is None, "no values"


def test_reservoir_values(get_random_checksum_address):
    reservoir_size = 5
    stakers_reservoir = {
        get_random_checksum_address(): 1 for _ in range(reservoir_size)
    }

    merged_reservoir = MergedReservoir(
        values=[], reservoir=StakingProvidersReservoir(stakers_reservoir)
    )
    assert len(merged_reservoir) == len(stakers_reservoir)

    drawn_addresses = []

    for _ in range(reservoir_size):
        staker_address = merged_reservoir()
        assert staker_address in stakers_reservoir

        assert staker_address not in drawn_addresses, "no repeats"
        drawn_addresses.append(staker_address)
        assert len(merged_reservoir) == (reservoir_size - len(drawn_addresses))

    assert len(merged_reservoir) == 0
    next_address = merged_reservoir()
    assert next_address is None, "no more values"


def test_reservoir_values_initial_values_specified(get_random_checksum_address):
    initial_list_size = 4
    initial_list = [get_random_checksum_address() for i in range(initial_list_size)]

    reservoir_size = 3
    remaining_stakers_reservoir = {
        get_random_checksum_address(): 1 for _ in range(reservoir_size)
    }

    merged_reservoir = MergedReservoir(
        values=initial_list,
        reservoir=StakingProvidersReservoir(remaining_stakers_reservoir),
    )
    assert len(merged_reservoir) == (initial_list_size + reservoir_size)

    drawn_addresses = []

    # initial list drawn from first
    for _ in range(initial_list_size):
        staker_address = merged_reservoir()
        assert staker_address in initial_list
        assert staker_address not in drawn_addresses, "no repeats for initial list"
        drawn_addresses.append(staker_address)
        assert len(merged_reservoir) == (
            initial_list_size + reservoir_size - len(drawn_addresses)
        )

    assert len(merged_reservoir) == reservoir_size

    # list is been exhausted, now draw from reservoir
    for _ in range(reservoir_size):
        staker_address = merged_reservoir()
        assert staker_address in remaining_stakers_reservoir
        assert staker_address not in drawn_addresses, "no repeats for reservoir"
        drawn_addresses.append(staker_address)
        assert len(merged_reservoir) == (
            initial_list_size + reservoir_size - len(drawn_addresses)
        )

    assert len(merged_reservoir) == 0

    next_address = merged_reservoir()
    assert next_address is None, "no more values"


def test_prefetch_strategy_insufficient_reservoir_size(get_random_checksum_address):
    reservoir_size = 5
    stakers_reservoir = {
        get_random_checksum_address(): 1 for _ in range(reservoir_size)
    }
    merged_reservoir = MergedReservoir(
        values=[], reservoir=StakingProvidersReservoir(stakers_reservoir)
    )

    with pytest.raises(ValueError, match="Insufficient staking providers"):
        PrefetchStrategy(reservoir=merged_reservoir, need_successes=reservoir_size + 1)


def test_prefetch_strategy_immediate_success(get_random_checksum_address):
    reservoir_size = 10
    needed_successes = 5
    stakers_reservoir = {
        get_random_checksum_address(): 1 for _ in range(reservoir_size)
    }
    merged_reservoir = MergedReservoir(
        values=[], reservoir=StakingProvidersReservoir(stakers_reservoir)
    )

    prefetch_strategy = PrefetchStrategy(
        reservoir=merged_reservoir, need_successes=needed_successes
    )

    batch = prefetch_strategy(successes=0)
    assert len(batch) == needed_successes

    batch = prefetch_strategy(successes=needed_successes)
    assert batch is None, "required successes already achieved"


@pytest.mark.parametrize("reservoir_size", [11, 18, 25, 30, 31, 42])
def test_prefetch_strategy_no_success(reservoir_size, get_random_checksum_address):
    reservoir_size = 19
    needed_successes = 5
    stakers_reservoir = {
        get_random_checksum_address(): 1 for _ in range(reservoir_size)
    }
    merged_reservoir = MergedReservoir(
        values=[], reservoir=StakingProvidersReservoir(stakers_reservoir)
    )

    prefetch_strategy = PrefetchStrategy(
        reservoir=merged_reservoir, need_successes=needed_successes
    )

    num_rounds_until_end = int(reservoir_size / needed_successes)
    for i in range(num_rounds_until_end):
        batch = prefetch_strategy(successes=0)
        assert len(batch) == needed_successes

    if reservoir_size % needed_successes != 0:
        # one last round
        batch = prefetch_strategy(successes=0)
        assert len(batch) == (reservoir_size % needed_successes)

    batch = prefetch_strategy(successes=0)
    assert batch is None, "no more available values to batch return"


def test_prefetch_strategy_just_need_that_last_success(get_random_checksum_address):
    reservoir_size = 20
    needed_successes = 5
    stakers_reservoir = {
        get_random_checksum_address(): 1 for _ in range(reservoir_size)
    }
    merged_reservoir = MergedReservoir(
        values=[], reservoir=StakingProvidersReservoir(stakers_reservoir)
    )

    prefetch_strategy = PrefetchStrategy(
        reservoir=merged_reservoir, need_successes=needed_successes
    )

    # pretend that we've had 1 missing success until this moment
    for _ in range(reservoir_size - 1):
        batch = prefetch_strategy(successes=needed_successes - 1)
        assert len(batch) == 1

    batch = prefetch_strategy(successes=needed_successes - 1)
    assert len(batch) == 1, "got it right at the end"

    batch = prefetch_strategy(successes=needed_successes - 1)
    assert batch is None, "no more values"


def test_prefetch_strategy_too_many_successes(get_random_checksum_address):
    reservoir_size = 20
    needed_successes = 5
    stakers_reservoir = {
        get_random_checksum_address(): 1 for _ in range(reservoir_size)
    }
    merged_reservoir = MergedReservoir(
        values=[], reservoir=StakingProvidersReservoir(stakers_reservoir)
    )

    prefetch_strategy = PrefetchStrategy(
        reservoir=merged_reservoir, need_successes=needed_successes
    )

    batch = prefetch_strategy(successes=needed_successes + 1)
    assert batch is None, "all done, more than required successes achieved"
