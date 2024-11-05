import collections
import time
from collections import defaultdict
from threading import Lock
from typing import List

from eth_typing import ChecksumAddress


class NodeLatencyStatsCollector:
    """
    Thread-safe utility that tracks latency statistics related to P2P connections with other nodes.
    """

    MAX_MOVING_AVERAGE_WINDOW = 5
    MAX_LATENCY = float(2**16)  # just need a large number for sorting

    class NodeLatencyContextManager:
        def __init__(
            self,
            stats_collector: "NodeLatencyStatsCollector",
            staker_address: ChecksumAddress,
        ):
            self._stats_collector = stats_collector
            self.staker_address = staker_address

        def __enter__(self):
            self.start_time = time.perf_counter()
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            if exc_type:
                # exception occurred - reset stats since connectivity was compromised
                self._stats_collector.reset_stats(self.staker_address)
            else:
                # no exception
                end_time = time.perf_counter()
                execution_time = end_time - self.start_time
                self._stats_collector._update_stats(self.staker_address, execution_time)

    def __init__(self, max_moving_average_window: int = MAX_MOVING_AVERAGE_WINDOW):
        self._node_stats = defaultdict(
            lambda: collections.deque([], maxlen=max_moving_average_window)
        )
        self._lock = Lock()

    def _update_stats(self, staking_address: ChecksumAddress, latest_time_taken: float):
        with self._lock:
            self._node_stats[staking_address].append(latest_time_taken)

    def reset_stats(self, staking_address: ChecksumAddress):
        with self._lock:
            self._node_stats[staking_address].clear()

    def get_latency_tracker(
        self, staker_address: ChecksumAddress
    ) -> NodeLatencyContextManager:
        return self.NodeLatencyContextManager(
            stats_collector=self, staker_address=staker_address
        )

    def get_average_latency_time(self, staking_address: ChecksumAddress) -> float:
        with self._lock:
            readings = list(self._node_stats[staking_address])
            num_readings = len(readings)
            # just need a large number > 0
            return (
                self.MAX_LATENCY if num_readings == 0 else sum(readings) / num_readings
            )

    def order_addresses_by_latency(
        self, staking_addresses: List[ChecksumAddress]
    ) -> List[ChecksumAddress]:
        result = sorted(
            staking_addresses,
            key=lambda staking_address: self.get_average_latency_time(staking_address),
        )
        return result
