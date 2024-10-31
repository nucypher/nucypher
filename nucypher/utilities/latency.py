import time
from collections import defaultdict
from threading import Lock
from typing import List

from eth_typing import ChecksumAddress


class NodeLatencyStatsCollector:
    """
    Track latency statistics related to communication with other nodes.
    """

    TOTAL_TIME = "total_time"
    COUNT = "count"
    MAX_LATENCY = 2**32 - 1  # just need a large number

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
        self._node_stats = defaultdict(lambda: {self.TOTAL_TIME: 0.0, self.COUNT: 0})
        self._lock = Lock()

    def update_stats(self, staking_address: ChecksumAddress, latest_time_taken: float):
        with self._lock:
            self._node_stats[staking_address][self.TOTAL_TIME] += latest_time_taken
            self._node_stats[staking_address][self.COUNT] += 1

    def reset_stats(self, staking_address: ChecksumAddress):
        with self._lock:
            self._node_stats[staking_address][self.TOTAL_TIME] = 0
            self._node_stats[staking_address][self.COUNT] = 0

    def get_latency_tracker(
        self, staker_address: ChecksumAddress
    ) -> NodeLatencyContextManager:
        return self.NodeLatencyContextManager(
            stats_collector=self, staker_address=staker_address
        )

    def get_average_latency_time(self, staking_address: ChecksumAddress) -> float:
        with self._lock:
            count = self._node_stats[staking_address][self.COUNT]
            # just need a large number > 0
            return (
                self.MAX_LATENCY
                if count == 0
                else self._node_stats[staking_address][self.TOTAL_TIME] / count
            )

    def order_addresses_by_latency(
        self, staking_addresses: List[ChecksumAddress]
    ) -> List[ChecksumAddress]:
        result = sorted(
            staking_addresses,
            key=lambda staking_address: self.get_average_latency_time(staking_address),
        )
        return result
