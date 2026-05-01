import random
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Callable, Iterable, List, Optional, Sequence, Tuple, Union

import requests
from requests import Session
from requests.adapters import HTTPAdapter
from web3 import Web3
from web3.middleware import geth_poa_middleware
from web3.types import Middleware


class ThreadLocalSessionManager:
    """
    One requests.Session per thread.
    Each thread gets its own connection pool(s) and keep-alives.
    """

    def __init__(self, max_pool_size: int = 20, retries: int = 0):
        if max_pool_size <= 0:
            raise ValueError("max_pool_size must be positive")
        if retries < 0:
            raise ValueError("retries must be non-negative")

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
     - Designed to be used within RPCEndpointManager for managing multiple endpoints.
     - Does not handle actual request sending, just tracks health and availability.
     - Cool down logic is simple: after 2 consecutive failures, it goes into cool down with exponential backoff up to max_backoff_s.
     - Availability is enforced via try_acquire(), which respects cool down and in-flight capacity limits.
    """

    @dataclass(frozen=True)
    class EndpointStats:
        """
        Snapshot of the endpoint's current health and usage stats for external inspection or sorting.
         - latest_latency_ms: most recent latency measurement in milliseconds.
         - ewma_latency_ms: exponentially weighted moving average of latency for trend tracking.
         - consecutive_request_failures: number of consecutive non-unreachable failures since last success.
         - consecutive_unreachable_failures: number of failures that indicate the endpoint is unreachable (e.g. connection errors).
         - num_in_flight_usage: current number of in-flight usages of this endpoint.
         - in_flight_capacity: current maximum allowed in-flight usages based on health.
         - last_used: real-world timestamp of the last time this endpoint was used (success or failure).
        """

        latest_latency_ms: float
        ewma_latency_ms: float
        consecutive_request_failures: int
        consecutive_unreachable_failures: int
        num_in_flight_usage: int
        in_flight_capacity: int
        last_used: float

        def __str__(self):
            return (
                f"EndpointStats(latency={self.latest_latency_ms:.2f}ms, "
                f"ewma_latency={self.ewma_latency_ms:.2f}ms, "
                f"consecutive_request_failures={self.consecutive_request_failures}, "
                f"consecutive_unreachable_failures={self.consecutive_unreachable_failures}, "
                f"in_flight_usage={self.num_in_flight_usage}, "
                f"in_flight_cap={self.in_flight_capacity}, "
                f"last_used={self.last_used})"
            )

    def __init__(
        self,
        endpoint_uri: str,
        max_backoff_s=10.0,
        min_in_flight_capacity: int = 10,
        max_in_flight_capacity: int = 50,
        ewma_alpha: float = 0.5,
        target_latency_ms: float = 2000.0,  # 2s
        scale_up_utilization_threshold: float = 0.5,
        max_unreachable_quarantine_s: float = 600.0,  # 10 minutes
        unreachable_quarantine_after: int = 2,  # number of consecutive unreachable failures before considering the endpoint essentially unreachable and applying a long backoff
        rng: Optional[random.Random] = None,
    ):
        if max_backoff_s <= 0:
            raise ValueError("max_backoff_s must be positive")
        if min_in_flight_capacity <= 0:
            raise ValueError("min_in_flight_capacity must be positive")
        if max_in_flight_capacity < min_in_flight_capacity:
            raise ValueError(
                "max_in_flight_capacity must be greater than or equal to min_in_flight_capacity"
            )
        if not (0 < ewma_alpha < 1.0):
            raise ValueError("ewma_alpha must be between 0 and 1")
        if target_latency_ms <= 0:
            raise ValueError("target_latency_ms must be positive")
        if not (0 < scale_up_utilization_threshold < 1.0):
            raise ValueError("scale_up_utilization_threshold must be between 0 and 1")

        self.endpoint_uri = endpoint_uri
        self.max_backoff_s = max_backoff_s

        self._latest_latency_ms = 0.0
        self._consecutive_request_failures = 0
        self._cool_down_until = 0.0
        self._last_used = 0.0

        self._num_in_flight_usage = 0
        self.min_in_flight_capacity = min_in_flight_capacity
        self._in_flight_capacity = min_in_flight_capacity
        self.max_in_flight_capacity = max_in_flight_capacity

        self.target_latency_ms = target_latency_ms

        # https://corporatefinanceinstitute.com/resources/career-map/sell-side/capital-markets/exponentially-weighted-moving-average-ewma/
        self.ewma_alpha = ewma_alpha
        self._ewma_latency_ms = 0.0

        self.scale_up_utilization_threshold = scale_up_utilization_threshold

        self.max_unreachable_quarantine_s = max_unreachable_quarantine_s
        self.unreachable_quarantine_after = unreachable_quarantine_after
        self._consecutive_unreachable_failures = 0

        self.rng = rng or random.Random()

        self._lock = threading.Lock()

    def is_cooled_down(self) -> bool:
        now = time.monotonic()
        with self._lock:
            return self._cool_down_until <= now

    def consider_increasing_in_flight_capacity(self) -> bool:
        """
        Consider increasing in-flight capacity due to already being at high utilization without
        failures: we are not in cool down, no consecutive failures, and we are at high utilization.

        This is a proactive adjustment to allow the endpoint to handle more load if current
        in flight capacity is deemed to be the bottleneck rather than health.

        NOTE: should only be called by RPCEndpointManager.

        :return True if the endpoint increased capacity, False otherwise
        """
        now = time.monotonic()
        with self._lock:
            # check that not in cool down
            if self._cool_down_until > now:
                # if we are in cool down state, it means we had recent failures and
                # should not increase capacity
                return False

            # check that there weren't consecutive failures recently
            if self._consecutive_request_failures > 0:
                # if we had recent failures, it means the endpoint is unstable and we should
                # not increase capacity even if we are not currently in cool down
                return False

            if self._consecutive_unreachable_failures > 0:
                # if we had recent unreachable failures, it means the endpoint can't be reached and
                # we should not increase capacity even if we are not currently in cool down
                return False

            # check that we are not already at max capacity
            if self._in_flight_capacity >= self.max_in_flight_capacity:
                return False

            # check in high-utilization state
            utilization_factor = self._num_in_flight_usage / self._in_flight_capacity
            if utilization_factor < self.scale_up_utilization_threshold:
                # utilization is low, no need to increase capacity
                return False

            # if we are here, it means we are not in cool down, and we are at high utilization,
            # so we can increase capacity
            self._in_flight_capacity = min(
                self.max_in_flight_capacity, self._in_flight_capacity + 2
            )
            return True

    @contextmanager
    def get_web3(
        self,
        session: Session,
        request_timeout: Union[float, Tuple[float, float]],
        override_middleware_stack: Optional[Sequence[Tuple[Middleware, str]]] = None,
    ):
        provider = self._make_provider(self.endpoint_uri, session, request_timeout)
        w3 = self._configure_w3(
            provider=provider, override_middleware_stack=override_middleware_stack
        )
        yield w3

    @staticmethod
    def _make_provider(
        endpoint_uri: str,
        session: Session,
        request_timeout: Union[float, Tuple[float, float]],
    ) -> Web3.HTTPProvider:
        # makes testing easier by having a static method create the provider so it can be mocked
        return Web3.HTTPProvider(
            endpoint_uri=endpoint_uri,
            session=session,
            request_kwargs={
                "timeout": request_timeout,
            },
        )

    @staticmethod
    def _configure_w3(
        provider: Web3.HTTPProvider,
        override_middleware_stack: Optional[Sequence[Tuple[Middleware, str]]] = None,
    ) -> Web3:
        # makes testing easier by having a static method create the web3 instance so it can be mocked
        # Instantiate a local web3 instance
        w3 = Web3(provider=provider, middlewares=override_middleware_stack)
        # inject web3 middleware to handle POA chain extra_data field.
        w3.middleware_onion.inject(geth_poa_middleware, layer=0, name="poa")
        return w3

    def try_acquire(self) -> bool:
        now = time.monotonic()
        with self._lock:
            if (
                self._cool_down_until <= now
                and self._num_in_flight_usage < self._in_flight_capacity
            ):
                self._num_in_flight_usage += 1
                return True

            return False

    def release(self) -> None:
        with self._lock:
            self._num_in_flight_usage -= 1
            if self._num_in_flight_usage < 0:
                raise RuntimeError("In-flight count should never be negative")

    def report_success(self, latency_ms: float) -> None:
        with self._lock:
            self._last_used = time.time()
            self._latest_latency_ms = latency_ms

            # reset failure counts on success
            self._consecutive_request_failures = 0
            self._consecutive_unreachable_failures = 0

            # reset cool down on success
            self._cool_down_until = 0.0

            self._ewma_latency_ms = (
                latency_ms
                if self._ewma_latency_ms == 0.0
                else (
                    # exponential weighted moving average update
                    self.ewma_alpha * latency_ms
                    + (1 - self.ewma_alpha) * self._ewma_latency_ms
                )
            )

            if self._in_flight_capacity < self.min_in_flight_capacity:
                # this can happen if endpoint was previously unreachable
                self._in_flight_capacity = self.min_in_flight_capacity
                return

            # proactive decrease on slow-but-successful responses
            if self._ewma_latency_ms > self.target_latency_ms * 1.5:
                # starting to get out of hand, start to reduce capacity
                self._in_flight_capacity = max(
                    self.min_in_flight_capacity, self._in_flight_capacity - 1
                )
            # additional capacity if performing well
            elif self._ewma_latency_ms <= self.target_latency_ms:
                utilization_factor = (
                    self._num_in_flight_usage / self._in_flight_capacity
                )
                if utilization_factor >= self.scale_up_utilization_threshold:
                    self._in_flight_capacity = min(
                        self.max_in_flight_capacity, self._in_flight_capacity + 1
                    )

    def report_failure(self, exc: Exception) -> None:
        with self._lock:
            self._last_used = time.time()
            now = time.monotonic()

            is_unreachable = isinstance(exc, requests.exceptions.ConnectionError)
            if is_unreachable:
                # endpoint is unreachable
                self._consecutive_unreachable_failures += 1
                self._consecutive_request_failures = 0  # reset non-unreachable failures

                # start going down in capacity more quickly on unreachable failures
                self._in_flight_capacity = max(1, self._in_flight_capacity // 2)

                if (
                    self._consecutive_unreachable_failures
                    >= self.unreachable_quarantine_after
                ):
                    # severely limit capacity to essentially quarantine the endpoint due to being unreachable
                    # until it proves it can be reachable again, at which point report_success
                    # will reset capacity and failures
                    self._in_flight_capacity = 1
                    unreachable_quarantine_jitter = min(
                        self.rng.uniform(0.8, 1.2) * self.max_unreachable_quarantine_s,
                        self.max_unreachable_quarantine_s,
                    )
                    self._cool_down_until = now + unreachable_quarantine_jitter

                return

            # non-unreachable failure
            self._consecutive_request_failures += 1
            self._consecutive_unreachable_failures = 0  # reset unreachable failures

            # decrease in flight capacity on failure, but never below minimum
            # either back to min or 1/2 of current capacity, whichever is higher
            self._in_flight_capacity = max(
                self.min_in_flight_capacity, self._in_flight_capacity // 2
            )

            if self._consecutive_request_failures >= 2:
                backoff = min(
                    self.max_backoff_s, 2 ** (self._consecutive_request_failures - 1)
                )
                # add some jitter to avoid common backoff patterns
                backoff_jitter = min(
                    self.rng.uniform(0.8, 1.2) * backoff, self.max_backoff_s
                )
                self._cool_down_until = now + backoff_jitter

    def get_stats_snapshot(self) -> EndpointStats:
        with self._lock:
            return self.EndpointStats(
                latest_latency_ms=self._latest_latency_ms,
                ewma_latency_ms=self._ewma_latency_ms,
                consecutive_request_failures=self._consecutive_request_failures,
                consecutive_unreachable_failures=self._consecutive_unreachable_failures,
                num_in_flight_usage=self._num_in_flight_usage,
                in_flight_capacity=self._in_flight_capacity,
                last_used=self._last_used,
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

        preferred_endpoints = preferred_endpoints or []
        endpoints = endpoints or []
        if set(preferred_endpoints) & set(endpoints):
            raise ValueError("Preferred endpoints cannot overlap with other endpoints")

        for url in preferred_endpoints:
            self.preferred_endpoints.append(
                # TODO make configurable?
                RPCEndpoint(
                    endpoint_uri=url,
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
                    endpoint_uri=url,
                    max_backoff_s=10.0,
                    min_in_flight_capacity=min_in_flight_capacity,
                    max_in_flight_capacity=max_in_flight_capacity,
                    target_latency_ms=target_latency_ms,
                )
            )

        if not self.preferred_endpoints and not self.endpoints:
            raise ValueError("At least one endpoint URI must be provided")

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
        # Attempt rounds: try each endpoint up to saturated_retries additional retries.
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
            # always shuffle before sorting to avoid persistent tie bias while keeping sorting
            # strategy intact; helps distribute early traffic when stats are similar
            random.shuffle(other_endpoints)
            other_endpoints = self._cooled_down_and_sorted(
                other_endpoints, endpoint_sort_strategy
            )
            candidates.extend(other_endpoints)

            if candidates:
                return candidates

            if round_idx < self.saturated_retries:
                time.sleep(self.saturated_retry_delay_s)  # brief sleep before retrying

        # If we get here, all endpoints are in cool down phase; and none available to use
        raise self.NoEndpointsAvailable(
            f"All endpoints at capacity or in cool down after {self.saturated_retries} retries"
        )

    def consider_increasing_capacity_on_saturation(self) -> None:
        """
        Consider proactively increasing in-flight capacity on all endpoints if endpoints are
        hitting capacity limits without failures.
        """
        for endpoint in self.preferred_endpoints + self.endpoints:
            endpoint.consider_increasing_in_flight_capacity()

    def call(
        self,
        fn: Callable[[Web3], Any],
        request_timeout: Union[float, Tuple[float, float]] = (
            3.05,
            5.0,
        ),  # https://requests.readthedocs.io/en/latest/user/advanced/#timeouts
        endpoint_sort_strategy: Optional[EndpointSortStrategy] = None,
        override_middleware_stack: Optional[Sequence[Tuple[Middleware, str]]] = None,
    ) -> Any:
        """
        Executes web3 calls with automatic endpoint selection, failover, and health tracking.
        :param fn: A function that takes a Web3 instance and performs the desired calls, returning a result.
        :param request_timeout: Timeout for the web3 provider requests, can be a single float or a (connect_timeout, read_timeout) tuple.
        :param endpoint_sort_strategy: Optional function to sort endpoints based on their stats for prioritization.
        :param override_middleware_stack: Optional sequence of (middleware, name) tuples to override Web3 default middlewares
        :return: The result of the provided function executed with a Web3 instance from a healthy endpoint.
        """
        endpoints = self._get_candidates(endpoint_sort_strategy=endpoint_sort_strategy)
        last_exc = None
        session = self.session_manager.get_session()
        for endpoint in endpoints:
            if not endpoint.try_acquire():
                # Something changed between when we got the candidates and now,
                #  so skip this endpoint and try the next one.
                continue

            try:
                with endpoint.get_web3(
                    session=session,
                    request_timeout=request_timeout,
                    override_middleware_stack=override_middleware_stack,
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
            finally:
                endpoint.release()

        if last_exc is not None:
            raise last_exc

        # if we are here it means we had candidates, but they were all at capacity or in
        # cool down by the time we tried to acquire them
        self.consider_increasing_capacity_on_saturation()
        raise self.NoEndpointsAvailable("All endpoints at capacity or in cool down")
