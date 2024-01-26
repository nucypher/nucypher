import random
import time
from typing import Iterable, Tuple

import pytest

from nucypher.utilities.concurrency import BatchValueFactory, WorkerPool


class AllAtOnceFactory:
    """
    A simple value factory that returns all its values in a single batch.
    """

    def __init__(self, values):
        self.values = values
        self._produced = False

    def __call__(self, _successes):
        if self._produced:
            return None
        else:
            self._produced = True
            return self.values


@pytest.fixture(scope="function")
def join_worker_pool(request):
    """
    Makes sure the pool is properly joined at the end of the test,
    so that one doesn't have to wrap the whole test in a try-finally block.
    """
    pool_to_join = None

    def register(pool):
        nonlocal pool_to_join
        pool_to_join = pool

    yield register
    pool_to_join.join()


class OperatorRule:
    def __init__(
        self, fails: bool = False, timeout_min: float = 0, timeout_max: float = 0
    ):
        self.fails = fails
        self.timeout_min = timeout_min
        self.timeout_max = timeout_max


class OperatorOutcome:
    def __init__(self, fails: bool, timeout: float):
        self.fails = fails
        self.timeout = timeout

    def __call__(self, value):
        time.sleep(self.timeout)
        if self.fails:
            raise Exception(f"Operator for {value} failed")
        else:
            return value


def generate_workers(rules: Iterable[Tuple[OperatorRule, int]], seed=None):
    rng = random.Random(seed)
    outcomes = []
    for rule, quantity in rules:
        for _ in range(quantity):
            timeout = rng.uniform(rule.timeout_min, rule.timeout_max)
            outcomes.append(OperatorOutcome(rule.fails, timeout))

    rng.shuffle(outcomes)

    values = list(range(len(outcomes)))

    def worker(value):
        return outcomes[value](value)

    return {value: outcomes[value] for value in values}, worker


def test_wait_for_successes(join_worker_pool):
    """
    Checks that `block_until_target_successes()` returns in time and gives all the successes,
    if there were enough of them.
    """

    outcomes, worker = generate_workers(
        [
            (OperatorRule(timeout_min=0.5, timeout_max=1.5), 10),
            (OperatorRule(fails=True, timeout_min=1, timeout_max=3), 20),
        ],
        seed=123,
    )

    factory = AllAtOnceFactory(list(outcomes))
    pool = WorkerPool(
        worker, factory, target_successes=10, timeout=10, threadpool_size=30
    )
    join_worker_pool(pool)

    t_start = time.monotonic()
    pool.start()
    successes = pool.block_until_target_successes()
    t_end = time.monotonic()

    failures = pool.get_failures()
    assert all(outcomes[value].fails for value in failures)

    assert len(successes) == 10

    # We have more threads in the pool than the workers,
    # so all the successful ones should be able to finish right away.
    assert t_end - t_start < 2

    # Should be able to do it several times
    successes = pool.block_until_target_successes()
    assert len(successes) == 10


def test_wait_for_successes_out_of_values(join_worker_pool):
    """
    Checks that if there weren't enough successful workers, `block_until_target_successes()`
    raises an exception when the value factory is exhausted.
    """

    outcomes, worker = generate_workers(
        [
            (OperatorRule(timeout_min=0.5, timeout_max=1.5), 9),
            (OperatorRule(fails=True, timeout_min=0.5, timeout_max=1.5), 20),
        ],
        seed=123,
    )

    factory = AllAtOnceFactory(list(outcomes))
    pool = WorkerPool(
        worker, factory, target_successes=10, timeout=10, threadpool_size=15
    )
    join_worker_pool(pool)

    t_start = time.monotonic()
    pool.start()
    with pytest.raises(WorkerPool.OutOfValues) as exc_info:
        pool.block_until_target_successes()
    t_end = time.monotonic()

    # We have roughly 2 workers per thread, so it shouldn't take longer than 1.5s (max timeout) * 2
    assert t_end - t_start < 4

    message = str(exc_info.value)

    assert (
        "Execution stopped before completion - not enough available values" in message
    )

    # We had 20 workers set up to fail
    num_expected_failures = 20
    assert f"{num_expected_failures} failures recorded" in message

    # check tracebacks
    tracebacks = exc_info.value.get_tracebacks()
    assert len(tracebacks) == num_expected_failures
    for value, traceback in tracebacks.items():
        assert 'raise Exception(f"Operator for {value} failed")' in traceback
        assert f"Operator for {value} failed" in traceback


def test_wait_for_successes_timed_out(join_worker_pool):
    """
    Checks that if enough successful workers can't finish before the timeout, we get an exception.
    """

    outcomes, worker = generate_workers(
        [
            (OperatorRule(timeout_min=0, timeout_max=0.5), 9),
            (OperatorRule(timeout_min=1.5, timeout_max=2.5), 1),
            (OperatorRule(fails=True, timeout_min=1.5, timeout_max=2.5), 20),
        ],
        seed=123,
    )

    factory = AllAtOnceFactory(list(outcomes))
    timeout = 1
    pool = WorkerPool(
        worker, factory, target_successes=10, timeout=timeout, threadpool_size=30
    )
    join_worker_pool(pool)

    t_start = time.monotonic()
    pool.start()
    with pytest.raises(WorkerPool.TimedOut) as exc_info:
        pool.block_until_target_successes()
    t_end = time.monotonic()

    # Even though timeout is 1, there are long-running workers which we can't interrupt.
    assert t_end - t_start < 3

    message = str(exc_info.value)

    # None of the workers actually failed, they just timed out
    assert f"Execution timed out after {timeout}s" == message


def test_join(join_worker_pool):
    """
    Test joining the pool.
    """

    outcomes, worker = generate_workers(
        [
            (OperatorRule(timeout_min=0.5, timeout_max=1.5), 9),
            (OperatorRule(fails=True, timeout_min=0.5, timeout_max=1.5), 20),
        ],
        seed=123,
    )

    factory = AllAtOnceFactory(list(outcomes))
    pool = WorkerPool(
        worker, factory, target_successes=10, timeout=1, threadpool_size=30
    )
    join_worker_pool(pool)

    t_start = time.monotonic()
    pool.start()
    pool.join()
    t_end = time.monotonic()

    pool.join()  # should work the second time too

    # Even though timeout is 1, there are long-running workers which we can't interrupt.
    assert t_end - t_start < 3


class BatchTrackingBatchValueFactory(BatchValueFactory):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.batch_sizes = []

    def __call__(self, successes):
        result = super().__call__(successes)
        if result:
            self.batch_sizes.append(len(result))

        return result


def test_batched_value_generation(join_worker_pool):
    """
    Tests a value factory that gives out value batches in portions.
    """

    outcomes, worker = generate_workers(
        [
            (OperatorRule(timeout_min=0.5, timeout_max=1.5), 80),
            (OperatorRule(fails=True, timeout_min=0.5, timeout_max=1.5), 80),
        ],
        seed=123,
    )

    factory = BatchTrackingBatchValueFactory(
        values=list(outcomes), required_successes=10
    )
    pool = WorkerPool(
        worker,
        factory,
        target_successes=10,
        timeout=10,
        threadpool_size=10,
        stagger_timeout=0.5,
    )
    join_worker_pool(pool)

    t_start = time.monotonic()
    pool.start()
    successes = pool.block_until_target_successes()
    pool.cancel()
    pool.join()
    t_end = time.monotonic()

    assert len(successes) == 10

    # Check that batch sizes in the factory were getting progressively smaller
    # as the number of successes grew.
    assert all(
        factory.batch_sizes[i] >= factory.batch_sizes[i + 1]
        for i in range(len(factory.batch_sizes) - 1)
    )

    # Since we canceled the pool, no more workers will be started and we will finish faster
    assert t_end - t_start < 4

    successes_copy = pool.get_successes()
    pool.get_failures()

    assert all(value in successes_copy for value in successes)


def test_cancel_waiting_workers(join_worker_pool):
    """
    If we have a small pool and many workers, it is possible for workers to be enqueued
    one after another in one thread.
    We test that if we call `cancel()`, these enqueued workers are cancelled too.
    """

    outcomes, worker = generate_workers(
        [
            (OperatorRule(timeout_min=1, timeout_max=1), 100),
        ],
        seed=123,
    )

    factory = AllAtOnceFactory(list(outcomes))
    pool = WorkerPool(
        worker, factory, target_successes=10, timeout=10, threadpool_size=10
    )
    join_worker_pool(pool)

    t_start = time.monotonic()
    pool.start()
    pool.block_until_target_successes()
    pool.cancel()
    pool.join()
    t_end = time.monotonic()

    # We have 10 threads in the pool and 100 workers that are all enqueued at once at the start.
    # If we didn't check for the cancel condition, we would have to wait for 10 seconds.
    # We get 10 successes after 1s and cancel the workers,
    # but the next workers in each thread have already started, so we have to wait for another 1s.
    assert t_end - t_start < 2.5


class BuggyFactory:
    def __init__(self, values):
        self.values = values

    def __call__(self, successes):
        if self.values is not None:
            values = self.values
            self.values = None
            return values
        else:
            raise Exception("Buggy factory")


def test_buggy_factory_raises_on_block():
    """
    Tests that if there is an exception thrown in the value factory,
    it is caught in the first call to `block_until_target_successes()`.
    """

    outcomes, worker = generate_workers(
        [(OperatorRule(timeout_min=1, timeout_max=1), 100)], seed=123
    )

    factory = BuggyFactory(list(outcomes))

    # WorkerPool short circuits once it has sufficient successes. Therefore,
    # the stagger timeout needs to be less than worker timeout,
    # since BuggyFactory only fails if you do a subsequent batch
    # Once the subsequent batch is requested, the BuggyFactory returns an error
    # causing WorkerPool to fail
    pool = WorkerPool(
        worker,
        factory,
        target_successes=10,
        timeout=10,
        threadpool_size=10,
        stagger_timeout=0.75,
    )

    pool.start()
    time.sleep(2)  # wait for the stagger timeout to finish
    with pytest.raises(Exception, match="Buggy factory"):
        pool.block_until_target_successes()
    # Further calls to `block_until_target_successes()` or `join()` don't throw the error.
    with pytest.raises(Exception, match="Buggy factory"):
        pool.block_until_target_successes()
    pool.cancel()

    with pytest.raises(Exception, match="Buggy factory"):
        pool.join()


def test_buggy_factory_raises_on_join():
    """
    Tests that if there is an exception thrown in the value factory,
    it is caught in the first call to `join()`.
    """

    outcomes, worker = generate_workers(
        [(OperatorRule(timeout_min=1, timeout_max=1), 100)], seed=123
    )

    factory = BuggyFactory(list(outcomes))
    pool = WorkerPool(
        worker, factory, target_successes=10, timeout=10, threadpool_size=10
    )

    pool.start()
    pool.cancel()
    with pytest.raises(Exception, match="Buggy factory"):
        pool.join()
    with pytest.raises(Exception, match="Buggy factory"):
        pool.join()
