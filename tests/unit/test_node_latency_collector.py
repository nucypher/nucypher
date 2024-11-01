import random
import time
from concurrent.futures import ThreadPoolExecutor, wait
from unittest.mock import patch

import pytest
from eth_typing import ChecksumAddress

from nucypher.utilities.latency import NodeLatencyStatsCollector


@pytest.fixture(scope="module")
def execution_data(get_random_checksum_address):
    executions = {}

    node_1 = get_random_checksum_address()
    node_1_exec_times = [11.23, 24.8, 31.5, 40.21]
    executions[node_1] = node_1_exec_times

    node_2 = get_random_checksum_address()
    node_2_exec_times = [5.03, 6.78, 7.42, 8.043]
    executions[node_2] = node_2_exec_times

    node_3 = get_random_checksum_address()
    node_3_exec_times = [0.44, 4.512, 3.3]
    executions[node_3] = node_3_exec_times

    node_4 = get_random_checksum_address()
    node_4_exec_times = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]
    executions[node_4] = node_4_exec_times

    sorted_order = sorted(
        list(executions.keys()),
        key=lambda x: sum(executions.get(x)) / len(executions.get(x)),
    )
    assert sorted_order == [
        node_4,
        node_3,
        node_2,
        node_1,
    ]  # test of the test - "that's sooo meta"

    return executions, sorted_order


def floats_sufficiently_equal(a: float, b: float):
    if abs(a - b) < 1e-9:
        return True

    return False


def test_collector_initialization_no_data_collected(get_random_checksum_address):
    node_latency_collector = NodeLatencyStatsCollector()

    staker_addresses = [get_random_checksum_address() for _ in range(4)]

    # no data collected so average equals maximum latency
    for staker_address in staker_addresses:
        assert (
            node_latency_collector.get_average_latency_time(staker_address)
            == NodeLatencyStatsCollector.MAX_LATENCY
        )

    # no data collected so no change in order
    assert (
        node_latency_collector.order_addresses_by_latency(staker_addresses)
        == staker_addresses
    )


def test_collector_stats_obtained(execution_data):
    executions, expected_node_sorted_order = execution_data
    node_latency_collector = NodeLatencyStatsCollector()

    # update stats for all nodes
    for node, execution_times in executions.items():
        for i, exec_time in enumerate(execution_times):
            node_latency_collector._update_stats(node, exec_time)

            # check ongoing average
            subset_of_times = execution_times[: (i + 1)]
            # floating point arithmetic makes an exact check tricky
            assert floats_sufficiently_equal(
                node_latency_collector.get_average_latency_time(node),
                sum(subset_of_times) / len(subset_of_times),
            )

        # check final average
        # floating point arithmetic makes an exact check tricky
        assert floats_sufficiently_equal(
            node_latency_collector.get_average_latency_time(node),
            sum(execution_times) / len(execution_times),
        )

    node_addresses = list(executions.keys())
    for _ in range(10):
        # try various random permutations of order
        random.shuffle(node_addresses)
        assert (
            node_latency_collector.order_addresses_by_latency(node_addresses)
            == expected_node_sorted_order
        )


def test_collector_stats_reset(execution_data):
    executions, original_expected_node_sorted_order = execution_data
    node_latency_collector = NodeLatencyStatsCollector()

    # update stats for all nodes
    for node, execution_times in executions.items():
        for exec_time in execution_times:
            node_latency_collector._update_stats(node, exec_time)

        assert floats_sufficiently_equal(
            node_latency_collector.get_average_latency_time(node),
            sum(execution_times) / len(execution_times),
        )

    # proper order
    assert (
        node_latency_collector.order_addresses_by_latency(list(executions.keys()))
        == original_expected_node_sorted_order
    )

    # reset stats for fastest node, in which case it should now move to the end of the ordered list
    node_latency_collector.reset_stats(original_expected_node_sorted_order[0])
    assert (
        node_latency_collector.get_average_latency_time(
            original_expected_node_sorted_order[0]
        )
        == NodeLatencyStatsCollector.MAX_LATENCY
    )

    updated_order = original_expected_node_sorted_order[1:] + [
        original_expected_node_sorted_order[0]
    ]
    assert updated_order != original_expected_node_sorted_order
    assert (
        node_latency_collector.order_addresses_by_latency(list(executions.keys()))
        == updated_order
    )

    # reset another node's stats
    node_latency_collector.reset_stats(updated_order[1])
    assert (
        node_latency_collector.get_average_latency_time(updated_order[1])
        == NodeLatencyStatsCollector.MAX_LATENCY
    )
    # the order the addresses are passed in dictates the order of nodes without stats
    expected_updated_updated_order = (
        [updated_order[0]] + updated_order[2:-1] + [updated_order[1], updated_order[3]]
    )
    assert (
        node_latency_collector.order_addresses_by_latency(updated_order)
        == expected_updated_updated_order
    )

    # reset all stats
    for node in executions.keys():
        node_latency_collector.reset_stats(node)
        assert (
            node_latency_collector.get_average_latency_time(node)
            == NodeLatencyStatsCollector.MAX_LATENCY
        )
    all_reset_order = list(executions.keys())
    assert (
        node_latency_collector.order_addresses_by_latency(all_reset_order)
        == all_reset_order
    )


def test_collector_simple_concurrency(execution_data):
    executions, expected_node_sorted_order = execution_data
    node_latency_collector = NodeLatencyStatsCollector()

    def populate_executions(node_address: ChecksumAddress):
        execution_times = executions[node_address]
        for exec_time in execution_times:
            # add some delay for better concurrency
            time.sleep(0.1)
            node_latency_collector._update_stats(node_address, exec_time)

    # use thread pool
    n_threads = len(executions)
    with ThreadPoolExecutor(n_threads) as executor:
        # download each url and save as a local file
        futures = []
        for node_address in executions.keys():
            f = executor.submit(populate_executions, node_address)
            futures.append(f)

        wait(futures, timeout=3)  # these shouldn't take long; only wait max 3s

    assert (
        node_latency_collector.order_addresses_by_latency(list(executions.keys()))
        == expected_node_sorted_order
    )


def test_collector_tracker_no_exception(execution_data):
    executions, expected_node_sorted_order = execution_data
    node_latency_collector = NodeLatencyStatsCollector()
    for node, execution_times in executions.items():
        for exec_time in execution_times:
            base_perf_counter = time.perf_counter()
            end_time = base_perf_counter + exec_time
            with patch("time.perf_counter", side_effect=[base_perf_counter, end_time]):
                with node_latency_collector.get_latency_tracker(node):
                    # fake execution; do nothing
                    time.sleep(0)

        # floating point arithmetic makes an exact check tricky
        assert floats_sufficiently_equal(
            node_latency_collector.get_average_latency_time(node),
            sum(execution_times) / len(execution_times),
        )

    node_addresses = list(executions.keys())
    for _ in range(10):
        # try various random permutations of order
        random.shuffle(node_addresses)
        assert (
            node_latency_collector.order_addresses_by_latency(node_addresses)
            == expected_node_sorted_order
        )


def test_collector_tracker_exception(execution_data):
    executions, _ = execution_data
    node_latency_collector = NodeLatencyStatsCollector()

    node_not_to_raise = random.sample(list(executions.keys()), 1)[0]
    for node, execution_times in executions.items():
        for exec_time in execution_times:
            base_perf_counter = time.perf_counter()
            end_time = base_perf_counter + exec_time
            with patch("time.perf_counter", side_effect=[base_perf_counter, end_time]):
                exception_propagated = False
                try:
                    with node_latency_collector.get_latency_tracker(node):
                        # raise exception during whatever node execution
                        if node != node_not_to_raise:
                            raise ConnectionRefusedError("random execution exception")
                except ConnectionRefusedError:
                    exception_propagated = True

                assert exception_propagated == (node != node_not_to_raise)

        if node != node_not_to_raise:
            # no stats stored so average equals MAX_LATENCY
            assert (
                node_latency_collector.get_average_latency_time(node)
                == NodeLatencyStatsCollector.MAX_LATENCY
            )
        else:
            # floating point arithmetic makes an exact check tricky
            assert floats_sufficiently_equal(
                node_latency_collector.get_average_latency_time(node_not_to_raise),
                sum(execution_times) / len(execution_times),
            )

    node_addresses = list(executions.keys())
    exp_sorted_addresses = [node_not_to_raise] + [
        a for a in node_addresses if a != node_not_to_raise
    ]
    sorted_addresses = node_latency_collector.order_addresses_by_latency(node_addresses)
    assert sorted_addresses[0] == node_not_to_raise
    assert sorted_addresses == exp_sorted_addresses
