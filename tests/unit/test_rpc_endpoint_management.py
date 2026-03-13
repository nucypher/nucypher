import random
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

import pytest
import requests
from requests.adapters import HTTPAdapter
from web3.middleware import (
    abi_middleware,
    async_buffered_gas_estimate_middleware,
    attrdict_middleware,
)

from nucypher.utilities.endpoint import (
    RPCEndpoint,
    RPCEndpointManager,
    ThreadLocalSessionManager,
)


class TestThreadLocalSessionManager:

    @staticmethod
    def check_adapter(
        adapter: HTTPAdapter, max_pool_size: int, retries: int, pool_block: bool
    ) -> None:
        assert adapter._pool_maxsize == max_pool_size
        assert adapter._pool_connections == max_pool_size
        assert adapter.max_retries.total == retries
        assert adapter._pool_block is pool_block

    def test_initialization_invalid_parameters(self):
        for value in [-5, -1, 0]:
            with pytest.raises(ValueError, match="max_pool_size must be positive"):
                ThreadLocalSessionManager(max_pool_size=value)

        for value in [-5, -1]:
            with pytest.raises(ValueError, match="retries must be non-negative"):
                ThreadLocalSessionManager(retries=value)

    def test_make_session_default_configuration(self):
        manager = ThreadLocalSessionManager()
        session = manager.get_session()

        # adapters for both schemes must exist
        assert "http://" in session.adapters
        assert "https://" in session.adapters

        http_adapter = session.adapters["http://"]
        self.check_adapter(
            adapter=http_adapter, max_pool_size=20, retries=0, pool_block=True
        )

        https_adapter = session.adapters["https://"]
        self.check_adapter(
            adapter=https_adapter, max_pool_size=20, retries=0, pool_block=True
        )

    def test_make_session_configuration(self):
        manager = ThreadLocalSessionManager(max_pool_size=7, retries=3)
        session = manager.get_session()

        # adapters for both schemes must exist
        assert "http://" in session.adapters
        assert "https://" in session.adapters

        http_adapter = session.adapters["http://"]
        self.check_adapter(
            adapter=http_adapter, max_pool_size=7, retries=3, pool_block=True
        )

        https_adapter = session.adapters["https://"]
        self.check_adapter(
            adapter=https_adapter, max_pool_size=7, retries=3, pool_block=True
        )

    def test_same_thread_return_same_session(self):
        manager = ThreadLocalSessionManager(max_pool_size=2)
        session_1 = manager.get_session()
        session_2 = manager.get_session()
        # same object returned for repeated calls in same thread
        assert session_1 is session_2

    def test_distinct_sessions_across_threads(self):
        manager = ThreadLocalSessionManager(max_pool_size=2)

        results = defaultdict(set)

        def get_session_id():
            thread_id = threading.get_ident()
            session = manager.get_session()
            # return object id
            results[thread_id].add(id(session))

        # smaller pool size than iterations ensures that all threads are utilized
        n_threads = 5
        with ThreadPoolExecutor(max_workers=n_threads * 5) as executor:
            for i in range(20):
                executor.submit(get_session_id)

        assert len(results) > 1, "at least 2 threads used"
        for thread_id, sessions in results.items():
            assert len(sessions) == 1, "one session per thread"


class TestRPCEndpoint:
    """
    Test the RPC endpoint.
    """

    URI = "https://example.com"

    def test_initialization_defaults(self):
        endpoint = RPCEndpoint(endpoint_uri=self.URI)
        assert endpoint.endpoint_uri == self.URI
        assert endpoint.max_backoff_s == 10.0
        assert endpoint.min_in_flight_capacity == 10
        assert endpoint.max_in_flight_capacity == 50
        assert endpoint.ewma_alpha == 0.5
        assert endpoint.target_latency_ms == 2000.0
        assert endpoint.scale_up_utilization_threshold == 0.5
        assert isinstance(endpoint.rng, random.Random)

    def test_initialization_invalid_parameters(self):
        for value in [0, -1, -5]:
            with pytest.raises(ValueError, match="max_backoff_s must be positive"):
                RPCEndpoint(endpoint_uri=self.URI, max_backoff_s=value)

        for value in [0, -1]:
            with pytest.raises(
                ValueError, match="min_in_flight_capacity must be positive"
            ):
                RPCEndpoint(endpoint_uri=self.URI, min_in_flight_capacity=value)

        with pytest.raises(
            ValueError,
            match="max_in_flight_capacity must be greater than or equal to min_in_flight_capacity",
        ):
            RPCEndpoint(
                endpoint_uri=self.URI,
                min_in_flight_capacity=20,
                max_in_flight_capacity=10,
            )

        for value in [-5, -0.5, -0.1, 0, 1, 1.1, 5]:
            with pytest.raises(ValueError, match="ewma_alpha must be between 0 and 1"):
                RPCEndpoint(endpoint_uri=self.URI, ewma_alpha=value)

        for value in [0, -1, -1000]:
            with pytest.raises(ValueError, match="target_latency_ms must be positive"):
                RPCEndpoint(endpoint_uri=self.URI, target_latency_ms=value)

        for value in [-5, -0.5, -0.1, 0, 1, 1.5, 5]:
            with pytest.raises(
                ValueError,
                match="scale_up_utilization_threshold must be between 0 and 1",
            ):
                RPCEndpoint(endpoint_uri=self.URI, scale_up_utilization_threshold=value)

    def test_custom_initialization(self):
        max_backoff_s = 15.0
        min_inflight_capacity = 100
        max_inflight_capacity = 500
        ewma_alpha = 0.1
        target_latency_ms = 3000.0
        scale_up_utilization_threshold = 0.4
        max_unreachable_quarantine_s = 900  # 15 minutes
        unreachable_quarantine_after = 1

        for with_rng in [True, False]:
            rng = random.Random() if with_rng else None
            endpoint = RPCEndpoint(
                endpoint_uri=self.URI,
                max_backoff_s=max_backoff_s,
                min_in_flight_capacity=min_inflight_capacity,
                max_in_flight_capacity=max_inflight_capacity,
                ewma_alpha=ewma_alpha,
                target_latency_ms=target_latency_ms,
                scale_up_utilization_threshold=scale_up_utilization_threshold,
                max_unreachable_quarantine_s=max_unreachable_quarantine_s,
                unreachable_quarantine_after=unreachable_quarantine_after,
                rng=rng,
            )
            assert endpoint.endpoint_uri == self.URI
            assert endpoint.max_backoff_s == max_backoff_s
            assert endpoint.min_in_flight_capacity == min_inflight_capacity
            assert endpoint.max_in_flight_capacity == max_inflight_capacity
            assert endpoint.ewma_alpha == ewma_alpha
            assert endpoint.target_latency_ms == target_latency_ms
            assert (
                endpoint.scale_up_utilization_threshold
                == scale_up_utilization_threshold
            )
            assert endpoint.max_unreachable_quarantine_s == max_unreachable_quarantine_s
            assert endpoint.unreachable_quarantine_after == unreachable_quarantine_after

            if with_rng:
                assert endpoint.rng == rng
            else:
                # without rng (should default to random.Random())
                assert isinstance(endpoint.rng, random.Random)

    def test_get_web3(self):
        endpoint = RPCEndpoint(endpoint_uri=self.URI)
        session = requests.Session()

        with endpoint.get_web3(session=session, request_timeout=4.0) as w3:
            assert w3.provider.endpoint_uri == self.URI
            assert w3.provider._request_kwargs["timeout"] == 4.0
            assert w3.middleware_onion.get("poa")  # poa middleware injected

        # subsequent calls should return different w3 instance
        with endpoint.get_web3(session=session, request_timeout=3.5) as w3_again:
            assert (
                w3_again is not w3
            ), "subsequent call should return different w3 instance"
            assert w3_again.provider.endpoint_uri == self.URI
            assert w3_again.provider._request_kwargs["timeout"] == 3.5
            assert w3_again.middleware_onion.get("poa")  # poa middleware injected

        # timeout can be a tuple
        with endpoint.get_web3(
            session=session, request_timeout=(2.1, 5.7)
        ) as w3_tuple_timeout:
            assert w3_tuple_timeout.provider.endpoint_uri == self.URI
            assert w3_tuple_timeout
            assert w3_tuple_timeout.middleware_onion.get(
                "poa"
            )  # poa middleware injected

        # override middleware
        my_middleware = [
            (attrdict_middleware, "attrdict"),
            (abi_middleware, "abi"),
            (async_buffered_gas_estimate_middleware, "buffered_gas_estimate"),
        ]
        with endpoint.get_web3(
            session=session,
            request_timeout=1.2,
            override_middleware_stack=my_middleware,
        ) as w3_custom_middleware:
            assert w3_custom_middleware.provider.endpoint_uri == self.URI
            assert w3_custom_middleware.provider._request_kwargs["timeout"] == 1.2
            assert (
                len(w3_custom_middleware.middleware_onion) == len(my_middleware) + 1
            ), "middleware stack should be overridden with provided middleware with poa middleware still injected"
            for mw_func, mw_name in my_middleware:
                assert w3_custom_middleware.middleware_onion.get(
                    mw_name
                ), f"{mw_name} should be in middleware stack"

    def test_try_acquire_release(self):
        endpoint = RPCEndpoint(
            endpoint_uri=self.URI, min_in_flight_capacity=10, max_in_flight_capacity=20
        )

        # simple acquire and release immediately
        for _ in range(20):
            assert endpoint.try_acquire()
            assert endpoint._num_in_flight_usage == 1
            assert endpoint.get_stats_snapshot().num_in_flight_usage == 1
            endpoint.release()
            assert endpoint._num_in_flight_usage == 0
            assert endpoint.get_stats_snapshot().num_in_flight_usage == 0

        # still min since we haven't reported success or failure to trigger capacity adjustment
        assert endpoint._in_flight_capacity == endpoint.min_in_flight_capacity
        # acquire up to current capacity
        for i in range(endpoint.min_in_flight_capacity):
            assert endpoint.try_acquire()
            stats = endpoint.get_stats_snapshot()
            assert stats.num_in_flight_usage == (i + 1)

        assert not endpoint.try_acquire(), "can't acquire beyond current capacity"

        # release half
        n_releases = endpoint.min_in_flight_capacity // 2
        for _ in range(n_releases):
            endpoint.release()

        assert endpoint._num_in_flight_usage == (
            endpoint.min_in_flight_capacity - n_releases
        )
        assert endpoint.get_stats_snapshot().num_in_flight_usage == (
            endpoint.min_in_flight_capacity - n_releases
        )

        # fake that endpoint is in cool down
        endpoint._cool_down_until = time.monotonic() + 10
        assert not endpoint.try_acquire(), "can't acquire when in cooldown"

    @pytest.mark.parametrize("scale_up_utilization", [0.3, 0.5, 0.7])
    def test_report_successes(self, scale_up_utilization):
        initial_min_capacity = 10
        max_capacity = 50
        endpoint = RPCEndpoint(
            endpoint_uri=self.URI,
            min_in_flight_capacity=initial_min_capacity,
            max_in_flight_capacity=max_capacity,
            scale_up_utilization_threshold=scale_up_utilization,
        )

        # report successes and failures to trigger capacity adjustment
        # go up to max
        current_capacity = initial_min_capacity
        num_in_flight_usages = 0
        while endpoint._in_flight_capacity < max_capacity:
            assert endpoint.try_acquire()  # acquire first to increment in-flight usage
            num_in_flight_usages += 1

            random_latency_ms = random.random() * endpoint.target_latency_ms

            utilization = endpoint._num_in_flight_usage / endpoint._in_flight_capacity
            endpoint.report_success(
                latency_ms=random_latency_ms
            )  # below target latency

            # check current usage
            assert endpoint._num_in_flight_usage == num_in_flight_usages
            assert (
                endpoint.get_stats_snapshot().num_in_flight_usage
                == num_in_flight_usages
            )

            # check failure counts
            assert endpoint._consecutive_request_failures == 0
            assert endpoint.get_stats_snapshot().consecutive_request_failures == 0
            assert endpoint._consecutive_unreachable_failures == 0
            assert endpoint.get_stats_snapshot().consecutive_unreachable_failures == 0

            # capacity increased since successful, below target latency, and utilization > 50%
            if utilization >= scale_up_utilization:
                current_capacity += 1
                expected_capacity = min(current_capacity, max_capacity)
                assert endpoint._in_flight_capacity == expected_capacity
                assert (
                    endpoint.get_stats_snapshot().in_flight_capacity
                    == expected_capacity
                )

        # release 5 to free up capacity for next test
        for i in range(5):
            endpoint.release()
            num_in_flight_usages -= 1
            assert endpoint._num_in_flight_usage == num_in_flight_usages
            assert (
                endpoint.get_stats_snapshot().num_in_flight_usage
                == num_in_flight_usages
            )

        # try to proactively increase past max capacity
        for i in range(5):
            assert endpoint.try_acquire()
            num_in_flight_usages += 1

            random_latency_ms = random.random() * endpoint.target_latency_ms
            endpoint.report_success(
                latency_ms=random_latency_ms
            )  # below target latency

            # check current usage
            assert endpoint._num_in_flight_usage == num_in_flight_usages
            assert (
                endpoint.get_stats_snapshot().num_in_flight_usage
                == num_in_flight_usages
            )

            # capacity should not increase past max
            assert endpoint._in_flight_capacity == max_capacity
            assert endpoint.get_stats_snapshot().in_flight_capacity == max_capacity

        # release 3 to free up capacity for next test
        for i in range(3):
            endpoint.release()
            num_in_flight_usages -= 1
            assert endpoint._num_in_flight_usage == num_in_flight_usages
            assert (
                endpoint.get_stats_snapshot().num_in_flight_usage
                == num_in_flight_usages
            )

        # report success but above target latency to trigger backoff
        for i in range(3):
            assert endpoint.try_acquire()
            num_in_flight_usages += 1
            try:
                # must be high to make ewma > 150% target latency to trigger backoff
                random_latency_ms = endpoint.target_latency_ms * 20
                endpoint.report_success(latency_ms=random_latency_ms)

                # check failure counts
                assert endpoint._consecutive_request_failures == 0
                assert endpoint.get_stats_snapshot().consecutive_request_failures == 0
                assert endpoint._consecutive_unreachable_failures == 0
                assert (
                    endpoint.get_stats_snapshot().consecutive_unreachable_failures == 0
                )

                # check current usage
                assert endpoint._num_in_flight_usage == num_in_flight_usages
                assert (
                    endpoint.get_stats_snapshot().num_in_flight_usage
                    == num_in_flight_usages
                )

                # capacity should incrementally decrease since made ewma > 150% target latency
                assert endpoint._ewma_latency_ms > (1.5 * endpoint.target_latency_ms)
                assert endpoint.get_stats_snapshot().ewma_latency_ms > (
                    1.5 * endpoint.target_latency_ms
                )

                expected_capacity = max_capacity - (i + 1)
                assert endpoint._in_flight_capacity == expected_capacity
                assert (
                    endpoint.get_stats_snapshot().in_flight_capacity
                    == expected_capacity
                )
            finally:
                endpoint.release()
                num_in_flight_usages -= 1

    def test_ewma_latency_calculation(self):
        endpoint = RPCEndpoint(endpoint_uri=self.URI, ewma_alpha=0.5)

        assert endpoint.try_acquire()
        try:
            # report a latency of 100ms
            endpoint.report_success(latency_ms=100)
            assert endpoint._ewma_latency_ms == 100
            assert endpoint.get_stats_snapshot().ewma_latency_ms == 100

            assert endpoint._latest_latency_ms == 100
            assert endpoint.get_stats_snapshot().latest_latency_ms == 100
        finally:
            endpoint.release()

        assert endpoint.try_acquire()
        try:
            # report a latency of 300ms, ewma should be (0.5 * 300) + (0.5 * 100) = 200ms
            endpoint.report_success(latency_ms=300)
            assert endpoint._ewma_latency_ms == 200
            assert endpoint.get_stats_snapshot().ewma_latency_ms == 200

            assert endpoint._latest_latency_ms == 300
            assert endpoint.get_stats_snapshot().latest_latency_ms == 300
        finally:
            endpoint.release()

        assert endpoint.try_acquire()
        try:
            # report a latency of 50ms, ewma should be (0.5 * 50) + (0.5 * 200) = 125ms
            endpoint.report_success(latency_ms=50)
            assert endpoint._ewma_latency_ms == 125
            assert endpoint.get_stats_snapshot().ewma_latency_ms == 125

            assert endpoint._latest_latency_ms == 50
            assert endpoint.get_stats_snapshot().latest_latency_ms == 50
        finally:
            endpoint.release()

        assert endpoint.try_acquire()
        try:
            # report a latency of 400ms, ewma should be (0.5 * 1000) + (0.5 * 125) = 562.5ms
            endpoint.report_success(latency_ms=1000)
            assert endpoint._ewma_latency_ms == 562.5
            assert endpoint.get_stats_snapshot().ewma_latency_ms == 562.5

            assert endpoint._latest_latency_ms == 1000
            assert endpoint.get_stats_snapshot().latest_latency_ms == 1000
        finally:
            endpoint.release()

    def test_report_request_failure(self):
        initial_min_capacity = 10
        max_capacity = 100
        endpoint = RPCEndpoint(
            endpoint_uri=self.URI,
            min_in_flight_capacity=initial_min_capacity,
            max_in_flight_capacity=max_capacity,
        )

        num_inflight_usages = 0
        # 1 failure the first time
        assert endpoint.try_acquire()
        num_inflight_usages += 1
        try:
            endpoint.report_failure(Exception("simulated failure"))

            # check current usage
            assert endpoint._num_in_flight_usage == num_inflight_usages
            assert (
                endpoint.get_stats_snapshot().num_in_flight_usage == num_inflight_usages
            )

            # capacity should decrease by half since failure until at min capacity
            expected_capacity = max(initial_min_capacity // 2, initial_min_capacity)
            assert endpoint._in_flight_capacity == expected_capacity
            assert endpoint.get_stats_snapshot().in_flight_capacity == expected_capacity

            # failure noted
            assert endpoint._consecutive_request_failures == 1
            assert endpoint.get_stats_snapshot().consecutive_request_failures == 1

            # check unreachable failure count (no change since separate counts for exec vs unreachable failures)
            assert endpoint._consecutive_unreachable_failures == 0
            assert endpoint.get_stats_snapshot().consecutive_unreachable_failures == 0
        finally:
            endpoint.release()
            num_inflight_usages -= 1

        # report successes first to increase capacity
        current_capacity = initial_min_capacity
        while endpoint._in_flight_capacity < max_capacity // 2:
            assert endpoint.try_acquire()
            num_inflight_usages += 1

            random_latency_ms = random.random() * 1000.0
            utilization = endpoint._num_in_flight_usage / endpoint._in_flight_capacity
            endpoint.report_success(
                latency_ms=random_latency_ms
            )  # below target latency

            # success wipes out consecutive failures
            assert endpoint._consecutive_request_failures == 0
            assert endpoint.get_stats_snapshot().consecutive_request_failures == 0
            assert endpoint._consecutive_unreachable_failures == 0
            assert endpoint.get_stats_snapshot().consecutive_unreachable_failures == 0

            # capacity should increase since successful, below target latency, and utilization > 50%
            assert endpoint._num_in_flight_usage == num_inflight_usages
            assert (
                endpoint.get_stats_snapshot().num_in_flight_usage == num_inflight_usages
            )

            if utilization >= endpoint.scale_up_utilization_threshold:
                current_capacity += 1

            expected_capacity = min(current_capacity, max_capacity)
            assert endpoint._in_flight_capacity == expected_capacity
            assert endpoint.get_stats_snapshot().in_flight_capacity == expected_capacity

        # release all to reset usage for next test; the built-up capacity should still be there
        for i in range(num_inflight_usages):
            endpoint.release()
            num_inflight_usages -= 1
            assert endpoint._num_in_flight_usage == num_inflight_usages
            assert (
                endpoint.get_stats_snapshot().num_in_flight_usage == num_inflight_usages
            )

        # report failures to trigger exponential backoff
        assert current_capacity == max_capacity // 2
        assert endpoint._in_flight_capacity == current_capacity
        assert endpoint.get_stats_snapshot().in_flight_capacity == current_capacity

        # trigger 1 failure, capacity should decrease by half but not enter cooldown yet
        assert endpoint.try_acquire()
        num_inflight_usages += 1
        try:
            endpoint.report_failure(Exception("simulated failure"))

            # check unreachable failure count (no change since separate counts for exec vs unreachable failures)
            assert endpoint._consecutive_unreachable_failures == 0
            assert endpoint.get_stats_snapshot().consecutive_unreachable_failures == 0

            # failure noted
            assert endpoint._consecutive_request_failures == 1
            assert endpoint.get_stats_snapshot().consecutive_request_failures == 1

            current_capacity = max(current_capacity // 2, initial_min_capacity)
            assert endpoint._in_flight_capacity == current_capacity
            assert endpoint.get_stats_snapshot().in_flight_capacity == current_capacity
        finally:
            endpoint.release()
            num_inflight_usages -= 1

        # after 2 consecutive failures (1 more failure), capacity should decrease by half and endpoint enters cooldown
        assert endpoint.try_acquire()
        num_inflight_usages += 1
        try:
            report_time = time.monotonic()
            endpoint.report_failure(Exception("simulated failure"))

            # check unreachable failure count (no change since separate counts for exec vs unreachable failures)
            assert endpoint._consecutive_unreachable_failures == 0
            assert endpoint.get_stats_snapshot().consecutive_unreachable_failures == 0

            # failure noted
            assert endpoint._consecutive_request_failures == 2
            assert endpoint.get_stats_snapshot().consecutive_request_failures == 2

            # capacity should decrease by half since failure until at min capacity
            current_capacity = current_capacity // 2
            expected_capacity = max(current_capacity, initial_min_capacity)
            assert endpoint._in_flight_capacity == expected_capacity
            assert endpoint.get_stats_snapshot().in_flight_capacity == expected_capacity

            # endpoint in cooldown
            assert endpoint._cool_down_until > report_time
            assert not endpoint.is_cooled_down()
        finally:
            endpoint.release()
            num_inflight_usages -= 1

        # acquire should fail when in cooldown
        assert not endpoint.try_acquire(), "can't acquire when in cooldown"

    def test_endpoint_in_cooldown_from_failures(self):
        endpoint = RPCEndpoint(endpoint_uri=self.URI, max_backoff_s=5.0)

        # initially not in cooldown
        assert endpoint._cool_down_until == 0.0

        assert endpoint.try_acquire()
        endpoint.report_failure(Exception("simulated failure"))
        endpoint.release()

        assert (
            endpoint._cool_down_until == 0.0
        ), "should not be in cooldown after 1 failure"

        assert endpoint.try_acquire()
        report_time = time.monotonic()
        endpoint.report_failure(Exception("simulated failure"))
        endpoint.release()

        assert (
            endpoint._cool_down_until > report_time
        ), "should be in cooldown after 2 consecutive failures"
        assert (
            not endpoint.is_cooled_down()
        ), "should be in cooldown after 2 consecutive failures"
        assert not endpoint.try_acquire(), "can't acquire when in cooldown"

    def test_endpoint_at_reduced_capacity_from_failures_doesnt_allow_acquire(self):
        initial_min_capacity = 10
        max_capacity = 100
        endpoint = RPCEndpoint(
            endpoint_uri=self.URI,
            min_in_flight_capacity=initial_min_capacity,
            max_in_flight_capacity=max_capacity,
        )
        num_inflight_usages = 0

        # report successes first to increase capacity
        current_capacity = initial_min_capacity
        while endpoint._in_flight_capacity < max_capacity // 2:
            assert endpoint.try_acquire()
            num_inflight_usages += 1

            random_latency_ms = random.random() * 1000.0
            utilization = endpoint._num_in_flight_usage / endpoint._in_flight_capacity
            endpoint.report_success(
                latency_ms=random_latency_ms
            )  # below target latency

            # capacity should increase since successful, below target latency, and utilization > 50%
            assert endpoint._num_in_flight_usage == num_inflight_usages
            assert (
                endpoint.get_stats_snapshot().num_in_flight_usage == num_inflight_usages
            )

            if utilization >= endpoint.scale_up_utilization_threshold:
                current_capacity += 1

            expected_capacity = min(current_capacity, max_capacity)
            assert endpoint._in_flight_capacity == expected_capacity
            assert endpoint.get_stats_snapshot().in_flight_capacity == expected_capacity

        # trigger 1 failure, capacity should decrease by half but not enter cooldown yet
        assert endpoint.try_acquire()
        num_inflight_usages += 1
        try:
            endpoint.report_failure(Exception("simulated failure"))

            # failure noted
            assert endpoint._consecutive_request_failures == 1
            assert endpoint.get_stats_snapshot().consecutive_request_failures == 1

            # check unreachable failure count (no change since separate counts for exec vs unreachable failures)
            assert endpoint._consecutive_unreachable_failures == 0
            assert endpoint.get_stats_snapshot().consecutive_unreachable_failures == 0

            current_capacity = max(current_capacity // 2, initial_min_capacity)
            assert endpoint._in_flight_capacity == current_capacity
            assert endpoint.get_stats_snapshot().in_flight_capacity == current_capacity
        finally:
            endpoint.release()
            num_inflight_usages -= 1

        # capacity dropped below current usage, so acquire should fail
        assert endpoint._in_flight_capacity < endpoint._num_in_flight_usage

        assert not endpoint.try_acquire(), "can't acquire when usage exceeds capacity"

        while endpoint._in_flight_capacity < endpoint._num_in_flight_usage:
            # release until usage is within capacity again
            endpoint.release()
            num_inflight_usages -= 1
            assert endpoint._num_in_flight_usage == num_inflight_usages
            assert (
                endpoint.get_stats_snapshot().num_in_flight_usage == num_inflight_usages
            )

        assert not endpoint.try_acquire(), "can't acquire when usage equals capacity"

        # one more release to get usage below capacity
        endpoint.release()
        num_inflight_usages -= 1
        assert endpoint._num_in_flight_usage == num_inflight_usages
        assert endpoint.get_stats_snapshot().num_in_flight_usage == num_inflight_usages
        assert (
            endpoint.try_acquire()
        ), "should be able to acquire when usage is below capacity again"

    def test_cool_down_consecutive_failures(self, mocker):
        endpoint = RPCEndpoint(endpoint_uri=self.URI, max_backoff_s=35)

        num_consecutive_failures = 0

        # 2**5 = 32 which is < max_backoff_s
        # with each consecutive failure, cooldown should be applied with exponentially increasing backoff time (with some jitter)
        for i in range(6):
            assert endpoint.try_acquire()
            try:
                now = 20_002.123  # fixed time for testing
                mocker.patch("time.monotonic", return_value=now)
                endpoint.report_failure(Exception("simulated failure"))
                num_consecutive_failures += 1

                # failure noted
                assert (
                    endpoint._consecutive_request_failures == num_consecutive_failures
                )
                assert (
                    endpoint.get_stats_snapshot().consecutive_request_failures
                    == num_consecutive_failures
                )

                # check unreachable failure count (no change since separate counts for exec vs unreachable failures)
                assert endpoint._consecutive_unreachable_failures == 0
                assert (
                    endpoint.get_stats_snapshot().consecutive_unreachable_failures == 0
                )

                if num_consecutive_failures >= 2:
                    backoff = 2 ** (num_consecutive_failures - 1)

                    # endpoint in cooldown
                    assert (
                        endpoint._cool_down_until >= now + backoff * 0.8
                    ), f"cooldown should be at least {backoff * 0.8}s after report time"
                    assert (
                        endpoint._cool_down_until <= now + backoff * 1.2
                    ), f"cooldown should be at most {backoff * 1.2}s after report time"
                    assert not endpoint.is_cooled_down()

            finally:
                endpoint.release()

            # fake that cool down was waited
            endpoint._cool_down_until = time.monotonic() - 1
            assert endpoint.is_cooled_down()

        # 2**6 = 64 which exceeds max_backoff_s, so cooldown should be capped at max_backoff_s
        # next consecutive failure should still be recorded and cooldown should still be applied with max_backoff_s cooldown
        assert endpoint.try_acquire()
        try:
            now = 30_123.456  # fixed time for testing
            mocker.patch("time.monotonic", return_value=now)
            endpoint.report_failure(Exception("simulated failure"))
            num_consecutive_failures += 1

            # failure noted
            assert endpoint._consecutive_request_failures == num_consecutive_failures
            assert (
                endpoint.get_stats_snapshot().consecutive_request_failures
                == num_consecutive_failures
            )

            # check unreachable failure count (no change since separate counts for exec vs unreachable failures)
            assert endpoint._consecutive_unreachable_failures == 0
            assert endpoint.get_stats_snapshot().consecutive_unreachable_failures == 0

            assert endpoint._cool_down_until >= now + (
                0.8 * endpoint.max_backoff_s
            ), "cooldown should be at least 80% of max_backoff_s after report time"
            assert (
                endpoint._cool_down_until <= now + endpoint.max_backoff_s
            ), "cooldown should be at most max_backoff_s after report time"
            assert not endpoint.is_cooled_down()
        finally:
            endpoint.release()

    def test_consider_increasing_in_flight_capacity(self):
        initial_min_capacity = 10
        max_capacity = 50
        scale_up_utilization = 0.5
        endpoint = RPCEndpoint(
            endpoint_uri=self.URI,
            min_in_flight_capacity=initial_min_capacity,
            max_in_flight_capacity=max_capacity,
            scale_up_utilization_threshold=scale_up_utilization,
        )

        # hasn't been used yet, so shouldn't increase capacity even if utilization is high
        assert not endpoint.consider_increasing_in_flight_capacity()

        num_inflight_usages = 0
        # acquire just below scale up utilization (without any success reporting or release
        # this mimics a scenario where we are hitting capacity but haven't yet had a chance to
        # report successes to trigger capacity increase
        for i in range(int((initial_min_capacity * scale_up_utilization) - 1)):
            assert endpoint.try_acquire()
            num_inflight_usages += 1

            # utilization should be at threshold, so should increase capacity
            assert not endpoint.consider_increasing_in_flight_capacity()

            assert (
                endpoint._in_flight_capacity == initial_min_capacity
            )  # unchanged since we haven't reported successes to trigger increase yet
            assert (
                endpoint.get_stats_snapshot().in_flight_capacity == initial_min_capacity
            )

        # even after that we are still just below scale up utilization, so should not increase capacity
        assert num_inflight_usages // initial_min_capacity < scale_up_utilization
        assert endpoint._num_in_flight_usage == num_inflight_usages
        assert num_inflight_usages < initial_min_capacity
        assert not endpoint.consider_increasing_in_flight_capacity()

        # now we go just over the utilization to consider proactively increasing capacity without any reporting
        minimum_threshold = int((initial_min_capacity * scale_up_utilization) + 1)
        while num_inflight_usages < minimum_threshold:
            assert endpoint.try_acquire()
            num_inflight_usages += 1

        assert endpoint._num_in_flight_usage == num_inflight_usages
        assert endpoint._in_flight_capacity == initial_min_capacity

        # now we should be able to increase capacity proactively
        # let's test other scenarios that would prevent increasing capacity first, eg. existing failures etc.
        # 1. in cool down
        endpoint._cool_down_until = time.monotonic() + 60
        assert not endpoint.is_cooled_down()
        assert (
            not endpoint.consider_increasing_in_flight_capacity()
        ), "won't because in cool down"
        assert (
            endpoint._in_flight_capacity == initial_min_capacity
        ), "capacity unchanged"
        endpoint._cool_down_until = 0.0  # reset cool down

        # 2. has had consecutive request failures (some prior reporting was received)
        endpoint._consecutive_request_failures = 3
        assert (
            not endpoint.consider_increasing_in_flight_capacity()
        ), "won't because has consecutive failures"
        assert (
            endpoint._in_flight_capacity == initial_min_capacity
        ), "capacity unchanged"
        endpoint._consecutive_request_failures = 0  # reset failure count

        # 3. has had consecutive unreachable failures (some prior reporting was received)
        endpoint._consecutive_unreachable_failures = 2
        assert (
            not endpoint.consider_increasing_in_flight_capacity()
        ), "won't because has consecutive unreachable failures"
        assert (
            endpoint._in_flight_capacity == initial_min_capacity
        ), "capacity unchanged"
        endpoint._consecutive_unreachable_failures = 0  # reset failure count

        # 4. Already at max capacity
        endpoint._in_flight_capacity = max_capacity
        assert (
            not endpoint.consider_increasing_in_flight_capacity()
        ), "won't because at max capacity"
        assert endpoint._in_flight_capacity == max_capacity, "capacity unchanged"
        endpoint._in_flight_capacity = (
            initial_min_capacity  # reset capacity to be at min
        )

        # 5. min utilization factor not met
        endpoint._num_in_flight_usage = int(
            (initial_min_capacity * scale_up_utilization) - 1
        )
        endpoint._in_flight_capacity = initial_min_capacity
        assert (
            not endpoint.consider_increasing_in_flight_capacity()
        ), "won't because utilization not met"

        # Now let's try again with all conditions favorable and test that capacity does proactively increase
        endpoint._num_in_flight_usage = (
            initial_min_capacity - 1
        )  # set usage just below full utilization
        assert (
            endpoint.consider_increasing_in_flight_capacity()
        ), "capacity proactively increased"
        assert (
            endpoint._in_flight_capacity == initial_min_capacity + 2
        ), "proactively increased capacity by 2"

    def test_report_unreachable_failure(self, mocker):
        initial_min_capacity = 10
        max_capacity = 50
        scale_up_utilization = 0.5
        unreachable_quarantine_after = 3
        max_unreachable_quarantine_s = 900
        endpoint = RPCEndpoint(
            endpoint_uri=self.URI,
            min_in_flight_capacity=initial_min_capacity,
            max_in_flight_capacity=max_capacity,
            scale_up_utilization_threshold=scale_up_utilization,
            unreachable_quarantine_after=unreachable_quarantine_after,
            max_unreachable_quarantine_s=max_unreachable_quarantine_s,
        )

        connection_failure = requests.exceptions.ConnectionError(
            "simulated connection error"
        )

        # one less than unreachable_quarantine_after failures should not trigger unreachable quarantine
        for i in range(unreachable_quarantine_after - 1):
            assert endpoint.try_acquire()
            try:
                endpoint.report_failure(connection_failure)

                # check request failure count (no change since separate counts for exec vs unreachable failures)
                assert endpoint._consecutive_request_failures == 0
                assert endpoint.get_stats_snapshot().consecutive_request_failures == 0

                # unreachable failure noted
                assert endpoint._consecutive_unreachable_failures == (
                    i + 1
                ), "should have recorded 1 consecutive unreachable failure"
                assert (
                    endpoint.get_stats_snapshot().consecutive_unreachable_failures
                    == (i + 1)
                )

                # no cool down enacted as yet
                assert endpoint._cool_down_until == 0.0, "should not be in cooldown yet"
            finally:
                endpoint.release()

        # in flight capacity has been dropped by half twice
        assert endpoint._in_flight_capacity == (initial_min_capacity // 2) // 2

        first_quarantine_now = time.monotonic()

        # last failure should trigger unreachable quarantine
        assert endpoint.try_acquire()
        try:
            endpoint.report_failure(connection_failure)
            # we should now be in quarantine

            # check request failure count (no change since separate counts for exec vs unreachable failures)
            assert endpoint._consecutive_request_failures == 0
            assert endpoint.get_stats_snapshot().consecutive_request_failures == 0

            # check unreachable failure count
            assert (
                endpoint._consecutive_unreachable_failures
                == unreachable_quarantine_after
            )
            assert (
                endpoint.get_stats_snapshot().consecutive_unreachable_failures
                == unreachable_quarantine_after
            )

            # check updated capacity
            assert endpoint._in_flight_capacity == 1, "in quarantine so dropped to 1"
            assert endpoint.get_stats_snapshot().in_flight_capacity == 1

            # in quarantine (with some minimum jitter)
            assert (
                endpoint._cool_down_until
                >= first_quarantine_now + 0.8 * endpoint.max_unreachable_quarantine_s
            ), "cooldown should be at least 80% of quarantine time after report time"
        finally:
            endpoint.release()

        assert not endpoint.try_acquire(), "can't acquire endpoint in quarantine"
        assert (
            endpoint._num_in_flight_usage == 0
        ), "all acquires have been already released"

        # jump forward to after quarantine period
        after_first_quarantine = first_quarantine_now + max_unreachable_quarantine_s + 1
        mocker.patch(
            "time.monotonic",
            return_value=after_first_quarantine,
        )

        # still failing after 1st quarantine
        assert endpoint.try_acquire(), "we can acquire after quarantine period"
        try:
            assert endpoint._in_flight_capacity == 1, "in quarantine so dropped to 1"
            assert endpoint.get_stats_snapshot().in_flight_capacity == 1

            endpoint.report_failure(connection_failure)  # report failure

            # quarantine immediately enacted again
            assert endpoint._consecutive_request_failures == 0
            assert endpoint.get_stats_snapshot().consecutive_request_failures == 0
            assert (
                endpoint._consecutive_unreachable_failures
                == unreachable_quarantine_after + 1
            )
            assert (
                endpoint.get_stats_snapshot().consecutive_unreachable_failures
                == unreachable_quarantine_after + 1
            )

            # check capacity still unchanged
            assert endpoint._in_flight_capacity == 1, "in quarantine so dropped to 1"
            assert endpoint.get_stats_snapshot().in_flight_capacity == 1

            # still in quarantine (with some minimum jitter)
            assert endpoint._cool_down_until >= (
                after_first_quarantine + 0.8 * endpoint.max_unreachable_quarantine_s
            ), "2nd straight quarantine"
        finally:
            endpoint.release()

        assert not endpoint.try_acquire(), "can't acquire endpoint in quarantine"
        assert (
            endpoint._num_in_flight_usage == 0
        ), "all acquires have been already released"

        # jump forward to after 2nd quarantine period
        after_second_quarantine = (
            after_first_quarantine + max_unreachable_quarantine_s + 1
        )
        mocker.patch(
            "time.monotonic",
            return_value=after_second_quarantine,
        )

        # log first success after coming out of quarantine
        assert endpoint.try_acquire(), "we can acquire after quarantine period"
        try:
            assert endpoint._in_flight_capacity == 1, "in quarantine so dropped to 1"
            assert endpoint.get_stats_snapshot().in_flight_capacity == 1

            endpoint.report_success(
                latency_ms=1000
            )  # report success to exit quarantine

            # failure counts reset
            assert endpoint._consecutive_request_failures == 0
            assert endpoint.get_stats_snapshot().consecutive_request_failures == 0
            assert endpoint._consecutive_unreachable_failures == 0
            assert endpoint.get_stats_snapshot().consecutive_unreachable_failures == 0

            # cooled down reset
            assert endpoint._cool_down_until == 0.0

            # capacity restored in min_in_flight_capacity since a success was reported
            assert (
                endpoint._in_flight_capacity == initial_min_capacity
            ), "capacity should be restored to min capacity after success"
            assert (
                endpoint.get_stats_snapshot().in_flight_capacity == initial_min_capacity
            )
        finally:
            endpoint.release()


class TestRPCEndpointManager:
    """Focused unit tests for RPCEndpointManager behavior."""

    def test_at_least_one_endpoint_must_be_provided(self):
        session_manager = ThreadLocalSessionManager(max_pool_size=2)
        with pytest.raises(
            ValueError, match="At least one endpoint URI must be provided"
        ):
            RPCEndpointManager(session_manager=session_manager, endpoints=[])

    def test_preferred_endpoints_must_be_distinct_from_regular_endpoints(self):
        session_manager = ThreadLocalSessionManager(max_pool_size=2)
        endpoints = ["https://one.example", "https://two.example"]
        preferred = ["https://one.example"]  # overlap with regular endpoints

        with pytest.raises(
            ValueError, match="Preferred endpoints cannot overlap with other endpoints"
        ):
            RPCEndpointManager(
                session_manager=session_manager,
                endpoints=endpoints,
                preferred_endpoints=preferred,
            )

    def test_preferred_endpoint_bias(self, mocker):
        session_manager = ThreadLocalSessionManager(max_pool_size=2)
        endpoints = ["https://one.example", "https://two.example"]
        preferred = ["https://preferred.example"]

        manager = RPCEndpointManager(
            session_manager=session_manager,
            endpoints=endpoints,
            preferred_endpoints=preferred,
        )

        preferred_endpoint_acquire_spy = mocker.spy(
            manager.preferred_endpoints[0], "try_acquire"
        )
        preferred_endpoint_release_spy = mocker.spy(
            manager.preferred_endpoints[0], "release"
        )
        preferred_endpoint_success_spy = mocker.spy(
            manager.preferred_endpoints[0], "report_success"
        )
        preferred_endpoint_failure_spy = mocker.spy(
            manager.preferred_endpoints[0], "report_failure"
        )

        # simple successful call; preferred endpoint should be used first
        result = manager.call(lambda w3: "ok", request_timeout=1.0)
        assert result == "ok"

        assert preferred_endpoint_acquire_spy.call_count == 1
        assert preferred_endpoint_release_spy.call_count == 1
        assert preferred_endpoint_success_spy.call_count == 1
        assert preferred_endpoint_failure_spy.call_count == 0

        # preferred endpoint should have been used
        pref_stats = manager.preferred_endpoints[0].get_stats_snapshot()
        assert pref_stats.last_used > 0
        assert pref_stats.num_in_flight_usage == 0, "should have released after call"
        assert pref_stats.ewma_latency_ms > 0.0, "should have recorded latency"

    def test_call_tries_alternate_endpoints_on_failure_and_raises_if_all_fail(
        self, mocker
    ):
        session_manager = ThreadLocalSessionManager(max_pool_size=2)
        endpoints = ["https://a.example", "https://b.example"]

        manager = RPCEndpointManager(
            session_manager=session_manager,
            endpoints=endpoints,
        )

        endpoints_0_acquire_spy = mocker.spy(manager.endpoints[0], "try_acquire")
        endpoints_0_release_spy = mocker.spy(manager.endpoints[0], "release")
        endpoints_0_success_spy = mocker.spy(manager.endpoints[0], "report_success")
        endpoints_0_failure_spy = mocker.spy(manager.endpoints[0], "report_failure")

        endpoints_1_acquire_spy = mocker.spy(manager.endpoints[1], "try_acquire")
        endpoints_1_release_spy = mocker.spy(manager.endpoints[1], "release")
        endpoints_1_success_spy = mocker.spy(manager.endpoints[1], "report_success")
        endpoints_1_failure_spy = mocker.spy(manager.endpoints[1], "report_failure")

        # function that always raises
        def failing_fn(w3):
            raise Exception("boom")

        with pytest.raises(Exception, match="boom"):
            manager.call(failing_fn, request_timeout=1)

        assert endpoints_0_acquire_spy.call_count == 1
        assert endpoints_0_release_spy.call_count == 1
        assert endpoints_0_success_spy.call_count == 0
        assert endpoints_0_failure_spy.call_count == 1

        assert endpoints_1_acquire_spy.call_count == 1
        assert endpoints_1_release_spy.call_count == 1
        assert endpoints_1_success_spy.call_count == 0
        assert endpoints_1_failure_spy.call_count == 1

        for e in manager.endpoints:
            # each endpoint should have recorded at least 1 failure
            stats = e.get_stats_snapshot()
            assert stats.consecutive_request_failures >= 1
            assert stats.last_used > 0

    def test_no_endpoints_available_raises_when_all_in_cooldown(self):
        session_manager = ThreadLocalSessionManager(max_pool_size=2)
        endpoints = ["https://x.example", "https://y.example"]

        manager = RPCEndpointManager(
            session_manager=session_manager,
            endpoints=endpoints,
            saturated_retry_delay_s=0.01,
        )

        # put every endpoint into cooldown
        future = time.monotonic() + 1000.0
        for e in manager.preferred_endpoints + manager.endpoints:
            e._cool_down_until = future

        with pytest.raises(manager.NoEndpointsAvailable):
            manager.call(lambda w3: "should not run")

    def test_saturated_retries_will_sleep_and_retry(self, mocker):
        session_manager = ThreadLocalSessionManager(max_pool_size=2)
        preferred_endpoints = ["https://a.example"]
        endpoints = ["https://p.example", "https://q.example"]

        saturated_retries = 5

        manager = RPCEndpointManager(
            session_manager=session_manager,
            endpoints=endpoints,
            preferred_endpoints=preferred_endpoints,
            saturated_retries=saturated_retries,
            saturated_retry_delay_s=0.01,
        )

        # start with all endpoints in cooldown so first round yields no candidates
        for e in manager.preferred_endpoints + manager.endpoints:
            e._cool_down_until = time.monotonic() + 10.0

        sleep_calls = {"count": 0}

        def fake_sleep(duration):
            # on sleep, make endpoints available for the next round
            sleep_calls["count"] += 1
            if sleep_calls["count"] == saturated_retries:
                for e in manager.preferred_endpoints + manager.endpoints:
                    e._cool_down_until = 0.0

        # patch the time.sleep used inside the endpoint manager to avoid real waiting
        mocker.patch("nucypher.utilities.endpoint.time.sleep", side_effect=fake_sleep)

        result = manager.call(lambda w3: "worked", request_timeout=1.0)
        assert result == "worked"
        assert sleep_calls["count"] == saturated_retries

    def test_saturated_retries_exhausted_due_to_no_candidates(self, mocker):
        # the exception is raised after trying multiple rounds to
        # get candidate endpoints, but there are none (eg. all in cool down)
        session_manager = ThreadLocalSessionManager(max_pool_size=2)
        endpoints = ["https://a.example", "https://b.example", "https://c.example"]

        saturated_retries = 3
        manager = RPCEndpointManager(
            session_manager=session_manager,
            endpoints=endpoints,
            saturated_retries=saturated_retries,
        )

        try_acquire_spy = mocker.spy(RPCEndpoint, "try_acquire")

        def fake_sleep(duration):
            # do nothing
            pass

        # patch the time.sleep used inside the endpoint manager to avoid real waiting
        mocked_sleep = mocker.patch(
            "nucypher.utilities.endpoint.time.sleep", side_effect=fake_sleep
        )

        # patch manager so that _get_candidates is actually called but has no candidates to return
        mocker.patch.object(manager, "_cooled_down_and_sorted", return_value=[])

        with pytest.raises(
            RPCEndpointManager.NoEndpointsAvailable,
            match=f"All endpoints at capacity or in cool down after {saturated_retries} retries",
        ):
            _ = manager.call(lambda w3: "worked", request_timeout=1.0)

        # viable candidates available so try_acquire is called for each candidate
        assert (
            try_acquire_spy.call_count == 0
        ), "no try acquire since no candidates available "

        assert (
            mocked_sleep.call_count == saturated_retries
        ), "should have slept for each retry when no candidates available"

    def test_consider_increasing_in_flight_capacity(self, mocker):
        session_manager = ThreadLocalSessionManager(max_pool_size=2)
        endpoints = ["https://a.example", "https://b.example", "https://c.example"]

        manager = RPCEndpointManager(
            session_manager=session_manager,
            endpoints=endpoints,
        )

        consider_increasing_spy = mocker.spy(
            RPCEndpoint, "consider_increasing_in_flight_capacity"
        )

        # call consider_increasing_in_flight_capacity multiple times and ensure it's being called
        n_times_manager_called = 5
        for i in range(n_times_manager_called):
            manager.consider_increasing_capacity_on_saturation()

        # manager asks endpoints to consider increasing capacity so the next call could potentially succeed
        assert consider_increasing_spy.call_count == (
            n_times_manager_called * len(endpoints)
        ), "every endpoint called"

    def test_proactive_increase_of_in_flight_capacity_due_to_cant_try_acquire_candidate(
        self, mocker
    ):
        # the exception is raised after having possible candidates
        # but then try_acquire() on the candidate fails because candidate is no longer viable i.e. there
        # was a change in situation between getting candidate and using candidate
        session_manager = ThreadLocalSessionManager(max_pool_size=2)
        endpoints = ["https://a.example", "https://b.example", "https://c.example"]

        manager = RPCEndpointManager(
            session_manager=session_manager,
            endpoints=endpoints,
        )
        consider_increasing_spy = mocker.spy(
            RPCEndpoint, "consider_increasing_in_flight_capacity"
        )
        try_acquire_spy = mocker.spy(RPCEndpoint, "try_acquire")

        def fake_sleep(duration):
            # do nothing
            pass

        # patch the time.sleep used inside the endpoint manager to avoid real waiting
        mocker.patch("nucypher.utilities.endpoint.time.sleep", fake_sleep)

        # only first 2
        num_candidates = 2
        mocker.patch.object(
            manager, "_get_candidates", return_value=manager.endpoints[:num_candidates]
        )

        # simulate all endpoints being at high utilization to trigger proactive capacity increase
        for e in manager.endpoints:
            e._num_in_flight_usage = (
                e._in_flight_capacity
            )  # max out usage to not have any endpoint candidates for use and trigger increase

        with pytest.raises(
            RPCEndpointManager.NoEndpointsAvailable,
            match="All endpoints at capacity or in cool down",
        ):
            _ = manager.call(lambda w3: "worked", request_timeout=1.0)

        # viable candidates available so try_acquire is called for each candidate
        assert (
            try_acquire_spy.call_count == num_candidates
        ), "should have tried to acquire all candidates and failed"

        # manager asks endpoints to consider increasing capacity so the next call could potentially succeed
        assert consider_increasing_spy.call_count == len(
            endpoints
        ), "should have called consider_increasing_in_flight_capacity on all endpoints"

    def test_sorting_endpoints_for_call(self, mocker):
        session_manager = ThreadLocalSessionManager(max_pool_size=2)
        endpoints = ["https://a.example", "https://b.example", "https://c.example"]

        # endpoints get shuffled so any ties can be random; mock the random.shuffle to keep the
        # order deterministic for testing
        mocked_shuffle = mocker.patch(
            "nucypher.utilities.endpoint.random.shuffle", side_effect=lambda x: x
        )

        manager = RPCEndpointManager(
            session_manager=session_manager,
            endpoints=endpoints,
        )

        endpoint_0 = manager.endpoints[0]
        endpoint_0._ewma_latency_ms = 857.2
        endpoint_0._latest_latency_ms = 200.1

        endpoint_1 = manager.endpoints[1]
        # lower ewma, higher latest latency than endpoint_0
        endpoint_1._ewma_latency_ms = endpoint_0._ewma_latency_ms - 123.4
        endpoint_1._latest_latency_ms = endpoint_0._latest_latency_ms + 50.5

        endpoint_2 = manager.endpoints[2]
        # same as endpoint_0
        endpoint_2._ewma_latency_ms = endpoint_0._ewma_latency_ms
        endpoint_2._latest_latency_ms = endpoint_0._latest_latency_ms

        # capture w3 instances used for calls
        w3_instances = []

        def failing_fn(w3):
            w3_instances.append(w3)
            raise Exception("boom")

        # sort by lowest ewma latency
        with pytest.raises(Exception, match="boom"):
            manager.call(
                failing_fn,
                request_timeout=1,
                endpoint_sort_strategy=lambda stats: (stats.ewma_latency_ms,),
            )
        assert mocked_shuffle.call_count == 1
        mocked_shuffle.reset_mock()

        assert len(w3_instances) == 3, "all endpoints tried due to fallback"
        assert w3_instances[0].provider.endpoint_uri == endpoint_1.endpoint_uri
        assert w3_instances[1].provider.endpoint_uri == endpoint_0.endpoint_uri
        assert w3_instances[2].provider.endpoint_uri == endpoint_2.endpoint_uri

        # sort by lowest ewma latency then lowest last used
        # (careful because _last_used gets updated on call, so we set it manually here to have a deterministic order)
        now = time.time()
        endpoint_0._last_used = now
        endpoint_1._last_used = endpoint_0._last_used - 100
        endpoint_2._last_used = endpoint_0._last_used - 200

        w3_instances.clear()  # reset instances
        # reset failures so that nodes aren't excluded / set to cool down
        for e in manager.endpoints:
            e._consecutive_request_failures = 0
        with pytest.raises(Exception, match="boom"):
            manager.call(
                failing_fn,
                request_timeout=1,
                endpoint_sort_strategy=lambda stats: (
                    stats.ewma_latency_ms,
                    stats.last_used,
                ),
            )
        assert mocked_shuffle.call_count == 1
        mocked_shuffle.reset_mock()

        assert len(w3_instances) == 3, "all endpoints tried due to fallback"
        assert (
            w3_instances[0].provider.endpoint_uri == endpoint_1.endpoint_uri
        )  # lowest ewma latency
        assert (
            w3_instances[1].provider.endpoint_uri == endpoint_2.endpoint_uri
        )  # tie-breaker is last used so endpoint_2 should be preferred over endpoint_0
        assert w3_instances[2].provider.endpoint_uri == endpoint_0.endpoint_uri

        # sort by lowest latest latency
        w3_instances.clear()  # reset instances
        # reset failures so that nodes aren't excluded / set to cool down
        for e in manager.endpoints:
            e._consecutive_request_failures = 0
        with pytest.raises(Exception, match="boom"):
            manager.call(
                failing_fn,
                request_timeout=1,
                endpoint_sort_strategy=lambda stats: (stats.latest_latency_ms,),
            )

        assert mocked_shuffle.call_count == 1
        mocked_shuffle.reset_mock()

        assert len(w3_instances) == 3, "all endpoints tried due to fallback"
        assert (
            w3_instances[0].provider.endpoint_uri == endpoint_0.endpoint_uri
        )  # lowest latest latency (tie-breaker with endpoint_2 is pre-existing order)
        assert w3_instances[1].provider.endpoint_uri == endpoint_2.endpoint_uri
        assert w3_instances[2].provider.endpoint_uri == endpoint_1.endpoint_uri
