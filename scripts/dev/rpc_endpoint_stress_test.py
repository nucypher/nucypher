import random
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, wait
from functools import partial
from threading import Lock
from typing import Dict, Iterable, List, Optional

import click
from web3 import HTTPProvider, Web3
from web3.middleware import geth_poa_middleware

from nucypher.blockchain.eth import domains
from nucypher.blockchain.eth.utils import get_default_rpc_endpoints, obfuscate_rpc_url
from nucypher.utilities.endpoint import RPCEndpointManager, ThreadLocalSessionManager


class AtomicCounter:
    def __init__(self):
        self.value = 0
        self._lock = Lock()

    def increment(self):
        with self._lock:
            self.value += 1

    def get_value(self):
        with self._lock:
            return self.value


def _do_w3_things(endpoint_usage_stats: Dict[str, AtomicCounter], w3: Web3) -> None:
    # web3 calls
    _ = w3.eth.chain_id
    _ = w3.eth.block_number
    _ = w3.eth.get_block("latest")

    endpoint_usage_stats[w3.provider.endpoint_uri].increment()


def new_strategy_rpc_call(
    rpc_manager: RPCEndpointManager,
    failures: AtomicCounter,
    endpoint_usage_stats: Dict[str, AtomicCounter],
    endpoint_sort_strategy: Optional[RPCEndpointManager.EndpointSortStrategy] = None,
) -> None:
    try:
        do_things = partial(_do_w3_things, endpoint_usage_stats)
        rpc_manager.call(
            fn=do_things,
            request_timeout=5,
            endpoint_sort_strategy=endpoint_sort_strategy,
        )
    except Exception as e:
        click.secho(
            f"![FAILURE] RPC call failed with error: {e.__class__.__name__}: {e}",
            fg="red",
        )
        failures.increment()


class OldConditionProviderManagerStrategy:
    def __init__(
        self, preferential_providers: List[HTTPProvider], providers: List[HTTPProvider]
    ):
        self.preferential_providers = preferential_providers
        self.providers = providers

    def web3_endpoints(self) -> Iterable[Web3]:
        rpc_providers = []
        rpc_providers.extend(self.preferential_providers)

        other_providers = self.providers
        random.shuffle(other_providers)
        rpc_providers.extend(other_providers)

        for provider in rpc_providers:
            w3 = self._configure_w3(provider=provider)
            yield w3

    @staticmethod
    def _configure_w3(provider: HTTPProvider) -> Web3:
        # Instantiate a local web3 instance
        w3 = Web3(provider)
        # inject web3 middleware to handle POA chain extra_data field.
        w3.middleware_onion.inject(geth_poa_middleware, layer=0, name="poa")
        return w3


def legacy_strategy_rpc_call(
    provider_manager: OldConditionProviderManagerStrategy,
    failures: AtomicCounter,
    endpoint_usage_stats: Dict[str, AtomicCounter],
) -> None:
    endpoints = provider_manager.web3_endpoints()
    latest_error = ""
    for w3 in endpoints:
        try:
            _do_w3_things(endpoint_usage_stats, w3)
            return
        except Exception as e:
            latest_error = f"RPC call failed: {e.__class__.__name__}: {e}"
            # Something went wrong. Try the next endpoint.
            continue
    else:
        click.secho(
            f"![FAILURE] Legacy RPC call failed with latest error: {latest_error}",
            fg="red",
        )
        failures.increment()


STRATEGIES = [
    "latency",
    "latest_latency",
    "headroom_then_latency",
    "fewest_in_flight_then_latency",
    "last_used",
    "failures_then_latency",
    "failures_then_latency_known_over_unknown",
]


def get_endpoint_sort_strategy(
    strategy: str,
) -> RPCEndpointManager.EndpointSortStrategy:
    if strategy == "latency":
        # sort by latency (lowest latency first)
        return lambda stats: (stats.ewma_latency_ms,)
    elif strategy == "latest_latency":
        # sort by latest latency (most recently updated latency first)
        return lambda stats: (stats.latest_latency_ms,)
    elif strategy == "headroom_then_latency":
        # sort by headroom (endpoint with most headroom first), then latency (lowest latency first)
        return lambda stats: (
            -(stats.in_flight_capacity - stats.num_in_flight_usage),
            stats.ewma_latency_ms,
        )
    elif strategy == "fewest_in_flight_then_latency":
        # sort by lowest num in flight usage, then latency
        return lambda stats: (stats.num_in_flight_usage, stats.ewma_latency_ms)
    elif strategy == "last_used":
        # sort by last used time (oldest first)
        return lambda stats: (stats.last_used,)
    elif strategy == "failures_then_latency":
        # sort by fewest unreachable failures, then exec failures, then latency
        return lambda stats: (
            stats.consecutive_unreachable_failures,
            stats.consecutive_request_failures,
            stats.ewma_latency_ms,
        )
    elif strategy == "failures_then_latency_known_over_unknown":
        # sort by fewest unreachable failures, then exec failures, then latency, but prioritize endpoints
        # with known latency stats over those without any stats
        return lambda stats: (
            stats.consecutive_unreachable_failures,
            stats.consecutive_request_failures,
            stats.ewma_latency_ms if stats.ewma_latency_ms != 0.0 else float("inf"),
        )

    raise ValueError(f"Strategy '{strategy}' not implemented")


@click.command()
@click.option(
    "--chain-id",
    help="Chain ID to perform the stress test on (used for stats tracking).",
    type=click.INT,
    required=True,
)
@click.option(
    "--new-strategy/--legacy-strategy",
    "new_strategy",
    help="Use new strategy or legacy strategy",
    is_flag=True,
    default=True,
)
@click.option(
    "--num-threads",
    "-t",
    help="Number of threads to use for the stress test.",
    type=click.INT,
    default=30,
)
@click.option(
    "--test-executions",
    "-e",
    help="Number of total test executions to perform.",
    type=click.INT,
    default=900,
)
@click.option(
    "--timeout",
    help="Maximum time to wait for all threads to complete before timing out (in seconds).",
    type=click.INT,
    default=120,
)
@click.option(
    "--preferred-endpoint",
    "-p",
    help="Preferred endpoint to use (in addition to default rpc endpoints).",
    type=click.STRING,
    required=False,
)
@click.option(
    "--sort-strategy",
    help="The strategy to use for sorting endpoints in the new strategy.",
    type=click.Choice(STRATEGIES),
    required=False,
)
def rpc_stress_test(
    chain_id: int,
    new_strategy: bool,
    num_threads: int,
    test_executions: int,
    timeout: int,
    preferred_endpoint: Optional[str] = None,
    sort_strategy: Optional[str] = None,
) -> None:
    """
    Runs a stress test that can use either the new load balancing strategy or the legacy strategy
    by performing a number of concurrent RPC calls while tracking the number of failures and usage
    of each endpoint.
    """
    if sort_strategy and not new_strategy:
        raise click.UsageError(
            "The --sort-strategy option can only be used with the --new-strategy option."
        )
    sort_strategy = sort_strategy or "failures_then_latency"
    endpoint_sort_strategy = get_endpoint_sort_strategy(
        sort_strategy
    )  # same default as ConditionProviderManager

    condition_provider_manager = None
    rpc_endpoint_manager = None

    preferred_endpoints = [preferred_endpoint] if preferred_endpoint else []

    default_rpc_endpoints = get_default_rpc_endpoints(domains.LYNX)

    if chain_id not in default_rpc_endpoints:
        raise click.UsageError(
            f"Chain ID {chain_id} not supported in default RPC endpoints Available chain IDs: {list(default_rpc_endpoints.keys())}",
        )

    public_rpc_endpoints = default_rpc_endpoints.get(chain_id, [])
    # for testing with unreachable endpoint for chain 42
    # if chain_id == 42:
    #     public_rpc_endpoints.append("https://rpc.lukso.sigmacore.io")

    if new_strategy:
        thread_local_session_manager = ThreadLocalSessionManager()
        rpc_endpoint_manager = RPCEndpointManager(
            session_manager=thread_local_session_manager,
            preferred_endpoints=preferred_endpoints,
            endpoints=public_rpc_endpoints,
        )
    else:
        condition_provider_manager = OldConditionProviderManagerStrategy(
            providers=[HTTPProvider(endpoint) for endpoint in public_rpc_endpoints],
            preferential_providers=(
                [HTTPProvider(preferred_endpoint)] if preferred_endpoint else []
            ),
        )

    failures = AtomicCounter()
    endpoint_usage_stats = defaultdict(AtomicCounter)

    # use thread pool
    time_taken = time.perf_counter()
    try:
        with ThreadPoolExecutor(num_threads) as executor:
            futures = []
            for _ in range(test_executions):
                if new_strategy:
                    f = executor.submit(
                        new_strategy_rpc_call,
                        rpc_endpoint_manager,
                        failures,
                        endpoint_usage_stats,
                        endpoint_sort_strategy,
                    )
                else:
                    f = executor.submit(
                        legacy_strategy_rpc_call,
                        condition_provider_manager,
                        failures,
                        endpoint_usage_stats,
                    )
                futures.append(f)

            wait(futures, timeout=timeout)  # wait until done or timeout
    finally:
        time_taken = time.perf_counter() - time_taken

    click.echo(
        f"\n[RESULTS]: stress test with {num_threads} threads and {test_executions} test executions"
    )
    click.echo(f"\nTotal time: {time_taken:.2f}s")
    click.secho(
        f"Strategy used: {'NEW STRATEGY' if new_strategy else 'LEGACY'}", bold=True
    )
    if new_strategy:
        click.echo(f"\tEndpoint sort strategy: {sort_strategy}")
    click.secho(
        f"\tNum failures: {failures.get_value()}",
        fg="red" if failures.get_value() > 0 else None,
    )
    click.echo("\tEndpoints:")
    if preferred_endpoint:
        click.secho(
            f"\t\t Preferred Endpoint {obfuscate_rpc_url(preferred_endpoint)} was used {endpoint_usage_stats[preferred_endpoint].get_value()} times.",
            fg="green",
        )
        if new_strategy:
            click.echo(
                f"\t\t\t Stats: {rpc_endpoint_manager.preferred_endpoints[0].get_stats_snapshot()}"
            )
    for i, url in enumerate(public_rpc_endpoints):
        click.echo(
            f"\t\t {url} was used {endpoint_usage_stats[url].get_value()} times."
        )
        if new_strategy:
            assert rpc_endpoint_manager.endpoints[i].endpoint_uri == url
            click.echo(
                f"\t\t\t Stats: {rpc_endpoint_manager.endpoints[i].get_stats_snapshot()}"
            )


if __name__ == "__main__":
    rpc_stress_test()
