import time
from collections import defaultdict
from threading import Lock
from typing import List

from eth_typing import ChecksumAddress


class NodeLatencyStatsCollector:
    """
    Thread-safe utility that tracks latency statistics related to P2P connections with other nodes.
    """

    CURRENT_AVERAGE = "current_avg"
    COUNT = "count"
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
                self._stats_collector.update_stats(self.staker_address, execution_time)

    def __init__(self):
        # staker_address -> { "total_time": <float>, "count": <integer> }
        self._node_stats = defaultdict(
            lambda: {self.CURRENT_AVERAGE: 0.0, self.COUNT: 0}
        )
        self._lock = Lock()

    def update_stats(self, staking_address: ChecksumAddress, latest_time_taken: float):
        with self._lock:
            old_avg = self._node_stats[staking_address][self.CURRENT_AVERAGE]
            old_count = self._node_stats[staking_address][self.COUNT]

            updated_count = old_count + 1
            updated_avg = ((old_avg * old_count) + latest_time_taken) / updated_count

            self._node_stats[staking_address][self.CURRENT_AVERAGE] = updated_avg
            self._node_stats[staking_address][self.COUNT] = updated_count

    def reset_stats(self, staking_address: ChecksumAddress):
        with self._lock:
            self._node_stats[staking_address][self.CURRENT_AVERAGE] = 0
            self._node_stats[staking_address][self.COUNT] = 0

    def get_latency_tracker(
        self, staker_address: ChecksumAddress
    ) -> NodeLatencyContextManager:
        return self.NodeLatencyContextManager(
            stats_collector=self, staker_address=staker_address
        )

    def get_average_latency_time(self, staking_address: ChecksumAddress) -> float:
        with self._lock:
            current_avg = self._node_stats[staking_address][self.CURRENT_AVERAGE]
            # just need a large number > 0
            return self.MAX_LATENCY if current_avg == 0 else current_avg

    def order_addresses_by_latency(
        self, staking_addresses: List[ChecksumAddress]
    ) -> List[ChecksumAddress]:
        result = sorted(
            staking_addresses,
            key=lambda staking_address: self.get_average_latency_time(staking_address),
        )
        return result
