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

    def __init__(self, max_pool_size: int = 10, retries: int = 0):
        self._thread_local_storage = threading.local()
        self.max_pool_size = max_pool_size
        self.retries = retries

    def get_session(self) -> Session:
        session = getattr(self._thread_local_storage, "session", None)
        if session is None:
            session = self._make_session()
            self._thread_local_storage.session = session

        return session

    def _make_session(self):
        s = requests.Session()
        adapter = HTTPAdapter(
            pool_connections=self.max_pool_size,
            pool_maxsize=self.max_pool_size,
            max_retries=self.retries,
            pool_block=False,  # TODO: should this be True instead?
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
     - is_available() checks if the endpoint is currently available (not in cool down).
    """

    @dataclass(frozen=True)
    class EndpointStats:
        current_latency_ms: float
        consecutive_failures: int
        cool_down_until: float
        num_in_flight_usage: int
        last_used: float

    def __init__(self, endpoint: str, max_backoff_s=10.0):
        self.endpoint = endpoint
        self.max_backoff_s = max_backoff_s

        self.current_latency_ms = 0.0
        self.consecutive_failures = 0
        self.cool_down_until = 0.0
        self.num_in_flight_usage = 0
        self.last_used = 0.0

        self._lock = threading.Lock()

    @contextmanager
    def get_web3(
        self, session: Session, request_timeout: Union[float, Tuple[float, float]]
    ):
        with self._lock:
            self.num_in_flight_usage += 1
        try:
            w3 = Web3(
                Web3.HTTPProvider(
                    self.endpoint,
                    session=session,
                    request_kwargs={"timeout": request_timeout},
                )
            )
            w3.middleware_onion.inject(geth_poa_middleware, layer=0, name="poa")
            yield w3
        finally:
            with self._lock:
                self.num_in_flight_usage -= 1

    def is_available(self) -> bool:
        now = time.monotonic()
        with self._lock:
            return self.cool_down_until <= now

    def report_success(self, latency_ms: float) -> None:
        with self._lock:
            self.last_used = time.time()
            self.current_latency_ms = latency_ms
            self.consecutive_failures = 0
            self.cool_down_until = 0.0

    def report_failure(self, exc: Exception) -> None:
        with self._lock:
            self.last_used = time.time()
            # TODO - handle rate limit failures more specifically
            self.consecutive_failures += 1
            if self.consecutive_failures >= 2:
                backoff = min(self.max_backoff_s, 2 ** (self.consecutive_failures - 1))
                self.cool_down_until = time.monotonic() + backoff

    def get_stats_snapshot(self) -> EndpointStats:
        with self._lock:
            return self.EndpointStats(
                current_latency_ms=self.current_latency_ms,
                consecutive_failures=self.consecutive_failures,
                cool_down_until=self.cool_down_until,
                num_in_flight_usage=self.num_in_flight_usage,
                last_used=self.last_used,
            )


class RpcEndpointManager:
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
    ):
        self.session_manager = session_manager
        self.preferred_endpoints: List[RPCEndpoint] = []
        if preferred_endpoints:
            for url in preferred_endpoints:
                self.preferred_endpoints.append(
                    # TODO make configurable?
                    RPCEndpoint(endpoint=url, max_backoff_s=5.0)
                )

        self.endpoints: List[RPCEndpoint] = []
        for url in endpoints:
            self.endpoints.append(
                # TODO make configurable?
                RPCEndpoint(endpoint=url, max_backoff_s=60.0)
            )

        self.saturated_retries = saturated_retries
        self.saturated_retry_delay_s = saturated_retry_delay_s

    @staticmethod
    def _available_and_sorted(
        endpoints: List[RPCEndpoint],
        endpoint_sort_strategy: Optional[EndpointSortStrategy] = None,
    ) -> List[RPCEndpoint]:
        available = [e for e in endpoints if e.is_available()]

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
            preferred_endpoints = self._available_and_sorted(
                self.preferred_endpoints, endpoint_sort_strategy
            )
            candidates.extend(preferred_endpoints)

            # add non-preferred endpoints
            other_endpoints = self._available_and_sorted(
                self.endpoints, endpoint_sort_strategy
            )
            candidates.extend(other_endpoints)

            if candidates:
                return candidates

            if round_idx < self.saturated_retries:
                time.sleep(self.saturated_retry_delay_s)  # brief sleep before retrying

        # If we get here, everything was saturated for all rounds
        raise self.NoEndpointsAvailable("All endpoints saturated")

    def call(
        self,
        fn: Callable[[Web3], T],
        request_timeout: Union[float, Tuple[float, float]],
        endpoint_sort_strategy: Optional[EndpointSortStrategy] = None,
    ) -> T:
        endpoints = self._get_candidates(endpoint_sort_strategy)
        last_exc = None
        for endpoint in endpoints:
            session = self.session_manager.get_session()
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

            return result

        if last_exc is not None:
            raise last_exc

        # should never happen
        raise RuntimeError("No endpoints tried (unexpected)")
