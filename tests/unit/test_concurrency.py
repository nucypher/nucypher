import math

import pytest

from nucypher.network.concurrency import NetworkRequestClient
from nucypher.utilities.concurrency import (
    BatchValueFactory,
    VariableBatchSizeValueFactory,
)

NUM_VALUES = 20


@pytest.fixture(scope="module")
def values():
    values = []
    for i in range(0, NUM_VALUES):
        values.append(i)

    return values


def test_batch_value_factory_invalid_values(values):
    with pytest.raises(ValueError):
        BatchValueFactory(values=[], required_successes=0)

    with pytest.raises(ValueError):
        BatchValueFactory(values=[], required_successes=1)

    with pytest.raises(ValueError):
        BatchValueFactory(values=[1, 2, 3, 4], required_successes=5)

    with pytest.raises(ValueError):
        BatchValueFactory(values=[1, 2, 3, 4], required_successes=2, batch_size=0)


def test_batch_value_factory_all_successes_no_specified_batching(values):
    target_successes = NUM_VALUES
    value_factory = BatchValueFactory(
        values=values, required_successes=target_successes
    )

    # number of successes returned since no batching provided
    value_list = value_factory(successes=0)
    assert len(value_list) == target_successes, "list returned is based on successes"
    assert len(values) == NUM_VALUES, "values remained unchanged"

    # get list again
    value_list = value_factory(successes=NUM_VALUES)  # successes achieved
    assert not value_list, "successes achieved and no more values available"

    # get list again
    value_list = value_factory(successes=0)  # successes not achieved
    assert not value_list, "no successes achieved but no more values available"


def test_batch_value_factory_no_specified_batching_no_more_values_after_target_successes(
    values,
):
    target_successes = 1
    value_factory = BatchValueFactory(
        values=values, required_successes=target_successes
    )

    for i in range(0, NUM_VALUES // 3):
        value_list = value_factory(successes=0)
        assert (
            len(value_list) == target_successes
        ), "list returned is based on successes"
        assert len(values) == NUM_VALUES, "values remained unchanged"

    for i in range(NUM_VALUES // 3, NUM_VALUES):
        value_list = value_factory(successes=target_successes)
        assert (
            not value_list
        ), "there are more values but no more is needed since target successes attained"


def test_batch_value_factory_no_batching_no_success_multiple_calls(values):
    target_successes = 4
    value_factory = BatchValueFactory(
        values=values, required_successes=target_successes
    )

    for i in range(0, NUM_VALUES // target_successes):
        value_list = value_factory(successes=0)
        assert (
            len(value_list) == target_successes
        ), "list returned is based on successes"
        assert len(values) == NUM_VALUES, "values remained unchanged"

    # list all done but get list again
    value_list = value_factory(successes=target_successes)  # successes achieved
    assert not value_list, "successes achieved"

    # list all done but get list again
    value_list = value_factory(
        successes=1
    )  # not enough successes but list is now empty
    assert not value_list, "successes not achieved, but no more values available"


def test_batch_value_factory_no_batching_no_success_multiple_calls_non_divisible_successes(
    values,
):
    target_successes = 6
    value_factory = BatchValueFactory(
        values=values, required_successes=target_successes
    )

    # should be able to get 4 lists
    for i in range(0, NUM_VALUES // target_successes):
        value_list = value_factory(successes=0)
        assert (
            len(value_list) == target_successes
        ), "list returned is based on successes"
        assert len(values) == NUM_VALUES, "values remained unchanged"

    # last request
    value_list = value_factory(successes=0)
    assert len(value_list) == NUM_VALUES % target_successes, "remaining list returned"

    # get list again
    value_list = value_factory(successes=target_successes)  # successes achieved
    assert not value_list, "successes achieved"

    # get list again
    value_list = value_factory(
        successes=target_successes - 1
    )  # not enough successes but list is now empty
    assert not value_list, "successes not achieved, but no more values available"


def test_batch_value_factory_batching_individual(values):
    target_successes = NUM_VALUES
    batch_size = 1
    value_factory = BatchValueFactory(
        values=values, required_successes=target_successes, batch_size=batch_size
    )

    # number of successes returned since no batching provided
    for i in range(0, NUM_VALUES // batch_size):
        value_list = value_factory(successes=0)
        assert len(value_list) == batch_size, "list returned is based on batch size"
        assert len(values) == NUM_VALUES, "values remained unchanged"

    # get list again
    value_list = value_factory(successes=NUM_VALUES)  # successes achieved
    assert not value_list, "successes achieved and no more values available"

    # get list again
    value_list = value_factory(successes=0)  # successes not achieved
    assert not value_list, "no successes achieved but no more values available"


def test_batch_value_factory_batching_divisible(values):
    target_successes = NUM_VALUES
    batch_size = 5
    value_factory = BatchValueFactory(
        values=values, required_successes=target_successes, batch_size=batch_size
    )

    # number of successes returned since no batching provided (3x here)
    for i in range(0, NUM_VALUES // batch_size):
        value_list = value_factory(successes=target_successes - 1)
        assert len(value_list) == batch_size, "list returned is based on batch size"
        assert len(values) == NUM_VALUES, "values remained unchanged"

    # get list again
    value_list = value_factory(successes=NUM_VALUES)  # successes achieved
    assert not value_list, "successes achieved and no more values available"

    # get list again
    value_list = value_factory(successes=0)  # successes not achieved
    assert not value_list, "no successes achieved but no more values available"


def test_batch_value_factory_batching_non_divisible(values):
    target_successes = NUM_VALUES
    batch_size = 7
    value_factory = BatchValueFactory(
        values=values, required_successes=target_successes, batch_size=batch_size
    )

    # number of successes returned since no batching provided
    for i in range(0, NUM_VALUES // batch_size):
        value_list = value_factory(successes=0)
        assert len(value_list) == batch_size, "list returned is based on batch size"
        assert len(values) == NUM_VALUES, "values remained unchanged"

    # one more
    value_list = value_factory(successes=0)
    assert len(value_list) == NUM_VALUES % batch_size, "remainder of list returned"
    assert len(values) == NUM_VALUES, "values remained unchanged"

    # get list again
    value_list = value_factory(successes=target_successes)  # successes achieved
    assert not value_list, "successes achieved and no more values available"

    # get list again
    value_list = value_factory(successes=0)  # successes not achieved
    assert not value_list, "no successes achieved but no more values available"


class MyVariableBatchSizeFactory(VariableBatchSizeValueFactory):
    def __init__(self, values, required_successes, batch_size_func):
        super().__init__(values=values, required_successes=required_successes)
        self.batch_size_fn = batch_size_func

    def get_custom_batch_size(self, successes):
        return self.batch_size_fn(successes)


def test_variable_batch_size_factory_constant_batching():
    # A constant batch size function behaves like BatchValueFactory with that batch size
    vals = list(range(10))
    factory = MyVariableBatchSizeFactory(
        values=vals, required_successes=10, batch_size_func=lambda s: 3
    )

    assert factory(successes=0) == [0, 1, 2]
    assert factory(successes=0) == [3, 4, 5]
    assert factory(successes=0) == [6, 7, 8]
    assert factory(successes=0) == [9]
    assert factory(successes=0) is None


def test_variable_batch_size_factory_zero_batch_raises():
    # If the provided function returns a non-positive batch size, call raises ValueError
    vals = [1, 2, 3]
    factory = MyVariableBatchSizeFactory(
        values=vals, required_successes=3, batch_size_func=lambda s: 0
    )
    with pytest.raises(ValueError):
        factory(successes=0)


def test_variable_batch_size_factory_respects_success_threshold():
    # If successes already meet required_successes, factory returns None immediately
    vals = list(range(5))
    factory = MyVariableBatchSizeFactory(
        values=vals, required_successes=3, batch_size_func=lambda s: 2
    )
    assert factory(successes=3) is None


def test_variable_batch_size_factory_decreasing_batch_size():
    # Batch size may change depending on successes; ensure remaining items are returned
    vals = list(range(6))
    factory = MyVariableBatchSizeFactory(
        values=vals, required_successes=6, batch_size_func=lambda s: 4 if s < 2 else 1
    )

    assert factory(successes=0) == [0, 1, 2, 3]
    # Next call asks for batch size 4 again (since successes param still < 2), but only 2 remain
    assert factory(successes=1) == [4, 5]
    assert factory(successes=0) is None


@pytest.mark.parametrize("extra_buffer_factor", [-0.1, -0.01, None, 1.1, 1.5])
def test_request_factory_invalid_extra_buffer(
    get_random_checksum_address, extra_buffer_factor
):
    ursulas = [get_random_checksum_address() for _ in range(5)]
    threshold = 3

    with pytest.raises(
        ValueError, match="Threshold batch buffer factor must be between 0 and 1"
    ):
        NetworkRequestClient.RequestFactory(
            ursulas_to_contact=ursulas,
            threshold=threshold,
            threshold_batch_buffer_factor=extra_buffer_factor,
        )


def test_request_factory_required_successes_with_buffer_calc(
    get_random_checksum_address,
):
    ursulas = [get_random_checksum_address() for _ in range(10)]
    threshold = 4
    extra_buffer = 0.5
    req = NetworkRequestClient.RequestFactory(
        ursulas_to_contact=ursulas,
        threshold=threshold,
        threshold_batch_buffer_factor=extra_buffer,
    )

    assert req._required_successes_plus_buffer == int(threshold * (1 + extra_buffer))


def test_request_factory_get_custom_batch_size_simple(get_random_checksum_address):
    n_ursulas = 9  # odd number
    ursulas = [get_random_checksum_address() for _ in range(n_ursulas)]
    threshold = 1
    extra_buffer = 0.0  # no buffer
    req = NetworkRequestClient.RequestFactory(
        ursulas_to_contact=ursulas,
        threshold=threshold,
        threshold_batch_buffer_factor=extra_buffer,
    )

    for i in range(n_ursulas):
        assert req(successes=0) == ursulas[i * threshold : (i + 1) * threshold]


def test_request_factory_get_custom_batch_size_simple_remainder_at_end(
    get_random_checksum_address,
):
    n_ursulas = 9  # odd number
    ursulas = [get_random_checksum_address() for _ in range(n_ursulas)]
    threshold = 2
    extra_buffer = 0.0  # no buffer

    req = NetworkRequestClient.RequestFactory(
        ursulas_to_contact=ursulas,
        threshold=threshold,
        threshold_batch_buffer_factor=extra_buffer,
    )

    num_iterations = n_ursulas // threshold
    for i in range(num_iterations):
        assert req(successes=0) == ursulas[i * threshold : (i + 1) * threshold]

    # extra iteration where only 1 value remains; use 1 success to trigger the last value being
    # returned otherwise there wouldn't be sufficient values to meet threshold and error would be raised
    assert req(successes=1) == ursulas[-1:]


def test_request_factory_get_custom_batch_size_normal(get_random_checksum_address):
    n_ursulas = 10  # more than needed
    ursulas = [get_random_checksum_address() for _ in range(n_ursulas)]
    threshold = 4
    extra_buffer = 0.5
    req = NetworkRequestClient.RequestFactory(
        ursulas_to_contact=ursulas,
        threshold=threshold,
        threshold_batch_buffer_factor=extra_buffer,
    )

    threshold_with_buffer = math.ceil(threshold * (1 + extra_buffer))

    # first iteration returns threshold_with_buffer values, second call returns remaining values
    assert req(successes=0) == ursulas[0:threshold_with_buffer]
    assert req(successes=0) == ursulas[threshold_with_buffer:]


def test_request_factory_get_custom_batch_size_remaining_less_than_needed(
    get_random_checksum_address,
):
    n_ursulas = 7
    ursulas = [get_random_checksum_address() for _ in range(n_ursulas)]
    threshold = 6
    extra_buffer = 0.5
    req = NetworkRequestClient.RequestFactory(
        ursulas_to_contact=ursulas,
        threshold=threshold,
        threshold_batch_buffer_factor=extra_buffer,
    )

    threshold_with_buffer = math.ceil(threshold * (1 + extra_buffer))

    assert (
        threshold_with_buffer > n_ursulas
    ), "threshold with buffer should be greater than total values"
    assert (
        req(successes=0) == ursulas
    ), "should return all values since threshold with buffer is greater than total values"


def test_request_factory_raises_on_successes_ge_threshold(get_random_checksum_address):
    n_ursulas = 5
    ursulas = [get_random_checksum_address() for _ in range(n_ursulas)]

    threshold = 3
    req = NetworkRequestClient.RequestFactory(
        ursulas_to_contact=ursulas, threshold=threshold
    )
    with pytest.raises(
        ValueError,
        match="Current successes cannot be greater than or equal to the threshold",
    ):
        req.get_custom_batch_size(successes=threshold)
