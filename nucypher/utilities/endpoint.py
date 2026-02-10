import random
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Callable, Iterable, List, Optional, Tuple, TypeVar, Union

import requests
from requests import Session
from requests.adapters import HTTPAdapter
from web3 import Web3
from web3.middleware import geth_poa_middleware

T = TypeVar("T")


class ThreadLocalSessionManager:
    """
    One requests.Session per thread.
    Each thread gets its own connection pool(s) and keep-alives.
    """

    def __init__(self, max_pool_size: int = 20, retries: int = 0):
        self._thread_local_storage = threading.local()
        self.max_pool_size = max_pool_size
        self.retries = retries

    def get_session(self) -> Session:
        session = getattr(self._thread_local_storage, "session", None)
        if session is None:
            session = self._make_session()
            self._thread_local_storage.session = session

        return session

    def _make_session(self) -> requests.Session:
        s = requests.Session()
        adapter = HTTPAdapter(
            pool_connections=self.max_pool_size,
            pool_maxsize=self.max_pool_size,
            max_retries=self.retries,
            pool_block=True,
        )
        s.mount("http://", adapter)
        s.mount("https://", adapter)
        return s


class RPCEndpoint:
    """
    Represents an RPC endpoint with health tracking and automatic cool down on failures.
     - Tracks current latency and consecutive failures.
     - Automatically cools down after a certain number of failures, with exponential backoff.
     - Thread-safe for concurrent access and updates.
     - Designed to be used within RpcEndpointManager for managing multiple endpoints.
     - Does not handle actual request sending, just tracks health and availability.
     - Cool down logic is simple: after 2 consecutive failures, it goes into cool down with exponential backoff up to max_backoff_s.
     - is_available() checks if the endpoint is currently available (not in cool down and not exceeding capacity).
    """

    @dataclass(frozen=True)
    class EndpointStats:
        """
        Snapshot of the endpoint's current health and usage stats for external inspection or sorting.
         - latest_latency_ms: most recent latency measurement in milliseconds.
         - ewma_latency_ms: exponentially weighted moving average of latency for trend tracking.
         - consecutive_failures: number of consecutive failures since last success.
         - num_in_flight_usage: current number of in-flight usages of this endpoint.
         - in_flight_capacity: current maximum allowed in-flight usages based on health.
         - last_used: real-world timestamp of the last time this endpoint was used (success or failure).
        """

        latest_latency_ms: float
        ewma_latency_ms: float
        consecutive_failures: int
        num_in_flight_usage: int
        in_flight_capacity: int
        last_used: float

    def __init__(
        self,
        endpoint: str,
        max_backoff_s=10.0,
        min_in_flight_capacity: int = 10,
        max_in_flight_capacity: int = 50,
        ewma_alpha: float = 0.5,
        target_latency_ms: float = 2000.0,  # 2s
        rng: Optional[random.Random] = None,
    ):
        self.endpoint = endpoint
        self.max_backoff_s = max_backoff_s

        self.latest_latency_ms = 0.0
        self.consecutive_failures = 0
        self.cool_down_until = 0.0
        self.last_used = 0.0

        self.num_in_flight_usage = 0
        self.min_in_flight_capacity = min_in_flight_capacity
        self.in_flight_capacity = min_in_flight_capacity
        self.max_in_flight_capacity = max_in_flight_capacity

        self.target_latency_ms = target_latency_ms

        # https://corporatefinanceinstitute.com/resources/career-map/sell-side/capital-markets/exponentially-weighted-moving-average-ewma/
        self.ewma_alpha = ewma_alpha
        self.ewma_latency_ms = 0.0

        self._rng = rng or random.Random()

        self._lock = threading.Lock()

    def is_cooled_down(self) -> bool:
        now = time.monotonic()
        with self._lock:
            return self.cool_down_until <= now

    @contextmanager
    def get_web3(
        self, session: Session, request_timeout: Union[float, Tuple[float, float]]
    ):
        w3 = Web3(
            Web3.HTTPProvider(
                self.endpoint,
                session=session,
                request_kwargs={"timeout": request_timeout},
            )
        )
        w3.middleware_onion.inject(geth_poa_middleware, layer=0, name="poa")
        yield w3

    def try_acquire(self) -> bool:
        now = time.monotonic()
        with self._lock:
            if (
                self.cool_down_until <= now
                and self.num_in_flight_usage < self.in_flight_capacity
            ):
                self.num_in_flight_usage += 1
                return True

            return False

    def release(self) -> None:
        with self._lock:
            self.num_in_flight_usage -= 1
            if self.num_in_flight_usage < 0:
                raise RuntimeError("In-flight count should never be negative")

    def report_success(self, latency_ms: float) -> None:
        with self._lock:
            self.last_used = time.time()
            self.latest_latency_ms = latency_ms
            self.consecutive_failures = 0
            self.cool_down_until = time.monotonic()  # reset cool down on success

            self.ewma_latency_ms = (
                latency_ms
                if self.ewma_latency_ms == 0.0
                else (
                    # exponential weighted moving average update
                    self.ewma_alpha * latency_ms
                    + (1 - self.ewma_alpha) * self.ewma_latency_ms
                )
            )

            # proactive decrease on slow-but-successful responses
            if self.ewma_latency_ms > self.target_latency_ms * 1.5:
                # starting to get out of hand, start to reduce capacity
                self.in_flight_capacity = max(
                    self.min_in_flight_capacity, self.in_flight_capacity - 1
                )
            # additional capacity if performing well
            elif self.ewma_latency_ms <= self.target_latency_ms:
                self.in_flight_capacity = min(
                    self.max_in_flight_capacity, self.in_flight_capacity + 1
                )

    def report_failure(self, exc: Exception) -> None:
        with self._lock:
            self.last_used = time.time()
            # TODO - handle rate limit failures more specifically
            self.consecutive_failures += 1

            # decrease in flight capacity on failure, but never below minimum
            # either back to min or 1/2 of current capacity, whichever is higher
            self.in_flight_capacity = max(
                self.min_in_flight_capacity, self.in_flight_capacity // 2
            )

            if self.consecutive_failures >= 2:
                backoff = min(self.max_backoff_s, 2 ** (self.consecutive_failures - 1))
                # add some jitter to avoid common backoff patterns
                backoff_jitter = min(
                    self._rng.uniform(0.8, 1.2) * backoff, self.max_backoff_s
                )
                self.cool_down_until = time.monotonic() + backoff_jitter

    def get_stats_snapshot(self) -> EndpointStats:
        with self._lock:
            return self.EndpointStats(
                latest_latency_ms=self.latest_latency_ms,
                consecutive_failures=self.consecutive_failures,
                num_in_flight_usage=self.num_in_flight_usage,
                in_flight_capacity=self.in_flight_capacity,
                last_used=self.last_used,
                ewma_latency_ms=self.ewma_latency_ms,
            )


class RPCEndpointManager:
    """
    Manages multiple RPC endpoints with automatic failover and basic health tracking.
     - Tracks latency and failures for each endpoint.
     - Automatically cools down endpoints that are failing.
     - Prioritizes preferred endpoints if provided.
     - Thread-safe for concurrent use.
    """

    EndpointSortStrategy = Callable[[RPCEndpoint.EndpointStats], Tuple]

    class NoEndpointsAvailable(Exception):
        """All endpoints are in cool down or at max in-flight requests."""

    def __init__(
        self,
        session_manager: ThreadLocalSessionManager,
        endpoints: Iterable[str],
        preferred_endpoints: Optional[Iterable[str]] = None,
        saturated_retries: int = 2,
        saturated_retry_delay_s: float = 1.0,
        min_in_flight_capacity: int = 10,
        max_in_flight_capacity: int = 50,
        target_latency_ms: float = 2000.0,  # 2s
    ):
        self.session_manager = session_manager
        self.preferred_endpoints: List[RPCEndpoint] = []
        if preferred_endpoints:
            for url in preferred_endpoints:
                self.preferred_endpoints.append(
                    # TODO make configurable?
                    RPCEndpoint(
                        endpoint=url,
                        max_backoff_s=3.0,
                        min_in_flight_capacity=min_in_flight_capacity,
                        max_in_flight_capacity=max_in_flight_capacity,
                        target_latency_ms=target_latency_ms,
                    )
                )

        self.endpoints: List[RPCEndpoint] = []
        for url in endpoints:
            self.endpoints.append(
                # TODO make configurable?
                RPCEndpoint(
                    endpoint=url,
                    max_backoff_s=10.0,
                    min_in_flight_capacity=min_in_flight_capacity,
                    max_in_flight_capacity=max_in_flight_capacity,
                    target_latency_ms=target_latency_ms,
                )
            )

        self.saturated_retries = saturated_retries
        self.saturated_retry_delay_s = saturated_retry_delay_s

    @staticmethod
    def _cooled_down_and_sorted(
        endpoints: List[RPCEndpoint],
        endpoint_sort_strategy: Optional[EndpointSortStrategy] = None,
    ) -> List[RPCEndpoint]:
        available = [e for e in endpoints if e.is_cooled_down()]
        if not endpoint_sort_strategy:
            return available

        snapshots = [(e, e.get_stats_snapshot()) for e in available]
        snapshots.sort(key=lambda pair: endpoint_sort_strategy(pair[1]))
        return [pair[0] for pair in snapshots]

    def _get_candidates(
        self, endpoint_sort_strategy: Optional[EndpointSortStrategy] = None
    ) -> List[RPCEndpoint]:
        # Attempt rounds: try each endpoint up to max_attempts.
        # If all saturated, optionally sleep briefly and retry a few times.
        rounds = 1 + self.saturated_retries
        for round_idx in range(rounds):
            candidates = []

            # add preferred endpoints first, then others
            preferred_endpoints = self._cooled_down_and_sorted(
                self.preferred_endpoints, endpoint_sort_strategy
            )
            candidates.extend(preferred_endpoints)

            # add non-preferred endpoints
            other_endpoints = list(self.endpoints)
            if not endpoint_sort_strategy:
                # shuffle if no sorting strategy to help distribute load across equally healthy endpoints
                random.shuffle(other_endpoints)
            other_endpoints = self._cooled_down_and_sorted(
                other_endpoints, endpoint_sort_strategy
            )
            candidates.extend(other_endpoints)

            if candidates:
                return candidates

            if round_idx < self.saturated_retries:
                time.sleep(self.saturated_retry_delay_s)  # brief sleep before retrying

        # If we get here, everything was saturated for all rounds
        raise self.NoEndpointsAvailable("All endpoints at capacity or in cool down")

    def call(
        self,
        fn: Callable[[Web3], T],
        request_timeout: Union[float, Tuple[float, float]],
        endpoint_sort_strategy: Optional[EndpointSortStrategy] = None,
    ) -> T:
        endpoints = self._get_candidates(endpoint_sort_strategy)
        last_exc = None
        session = self.session_manager.get_session()
        for endpoint in endpoints:
            if not endpoint.try_acquire():
                # Something changed between when we got the candidates and now,
                #  so skip this endpoint and try the next one.
                continue

            try:
                with endpoint.get_web3(
                    session=session, request_timeout=request_timeout
                ) as w3:
                    start = time.perf_counter()
                    result = fn(w3)
                    latency_ms = (time.perf_counter() - start) * 1000.0
            except Exception as e:
                last_exc = e
                endpoint.report_failure(e)
                continue
            else:
                endpoint.report_success(latency_ms)
            finally:
                endpoint.release()

            return result

        if last_exc is not None:
            raise last_exc

        # should never happen
        raise RuntimeError("No endpoints tried (unexpected)")
