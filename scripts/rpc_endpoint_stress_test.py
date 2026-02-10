import os
import random
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, wait
from functools import partial
from threading import Lock
from typing import Dict, Iterable, List, Optional

import click
from eth_utils import to_checksum_address
from web3 import HTTPProvider, Web3
from web3.middleware import geth_poa_middleware

from nucypher.utilities.endpoint import RPCEndpointManager, ThreadLocalSessionManager

# ETH mainnet
PUBLIC_RPC_ENDPOINTS = [
    "https://eth.drpc.org",
    "https://ethereum-public.nodies.app",
    "https://ethereum-rpc.publicnode.com",
    "https://mainnet.gateway.tenderly.co",
    "https://rpc.mevblocker.io",
    "https://rpc.mevblocker.io/fast",
]

SIGNING_COORDINATOR_ADDRESS = to_checksum_address(
    "0x281EEE1e2261F895857Cc1eF5Bcc954E1F907386"
)
OPERATOR_ADDRESS = to_checksum_address(os.urandom(20))

COHORT_ID = 3
FUNCTION_ABI = """[
    {
        "inputs":[
            {"internalType":"uint32","name":"cohortId","type":"uint32"},
            {"internalType":"address","name":"operator","type":"address"}
        ],
        "name":"getSigningCohortDataHash",
        "outputs":[
            {"internalType":"bytes32","name":"","type":"bytes32"}
        ],
        "type":"function"
    }
]"""


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
    # call a contract function
    contract_instance = w3.eth.contract(
        address=SIGNING_COORDINATOR_ADDRESS, abi=FUNCTION_ABI
    )
    _ = contract_instance.functions.getSigningCohortDataHash(
        COHORT_ID, OPERATOR_ADDRESS
    ).call()

    # some other calls
    _ = w3.eth.block_number

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
        click.secho("RPC call succeeded", fg="green")
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
            click.secho(f"{w3.provider.endpoint_uri} RPC call succeeded", fg="green")
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

    raise ValueError(f"Strategy '{strategy}' not implemented")


@click.command()
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
    help="Preferred endpoint to use (in addition to rpc endpoint.",
    type=click.STRING,
    required=True,
)
@click.option(
    "--sort-strategy",
    help="The strategy to use for sorting endpoints in the new strategy.",
    type=click.Choice(STRATEGIES),
    required=False,
)
def rpc_stress_test(
    new_strategy: bool,
    num_threads: int,
    test_executions: int,
    timeout: int,
    preferred_endpoint: str,
    sort_strategy: str,
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
    endpoint_sort_strategy = (
        get_endpoint_sort_strategy(sort_strategy) if sort_strategy else None
    )

    condition_provider_manager = None
    rpc_endpoint_manager = None

    if new_strategy:
        thread_local_session_manager = ThreadLocalSessionManager()
        rpc_endpoint_manager = RPCEndpointManager(
            session_manager=thread_local_session_manager,
            preferred_endpoints=[preferred_endpoint],
            endpoints=PUBLIC_RPC_ENDPOINTS,
        )
    else:
        condition_provider_manager = OldConditionProviderManagerStrategy(
            providers=[HTTPProvider(endpoint) for endpoint in PUBLIC_RPC_ENDPOINTS],
            preferential_providers=[HTTPProvider(preferred_endpoint)],
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
    if sort_strategy:
        click.echo(f"\tEndpoint sort strategy: {sort_strategy}")
    click.echo(f"\tNum failures: {failures.get_value()}")
    click.echo("\tEndpoints:")
    click.echo(
        f"\t\t {preferred_endpoint} was used {endpoint_usage_stats[preferred_endpoint].get_value()} times."
    )
    for url in PUBLIC_RPC_ENDPOINTS:
        click.echo(
            f"\t\t {url} was used {endpoint_usage_stats[url].get_value()} times."
        )


if __name__ == "__main__":
    rpc_stress_test()
