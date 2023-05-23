import pytest

from nucypher.utilities.concurrency import BatchValueFactory

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
