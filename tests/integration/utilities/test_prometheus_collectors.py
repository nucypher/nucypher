import random
import time
from typing import List

import pytest

from nucypher.blockchain.eth.agents import ContractAgency, TACoApplicationAgent
from tests.constants import MOCK_ETH_PROVIDER_URI

try:
    # all prometheus related imports
    from prometheus_client import CollectorRegistry

    # include dependencies that have sub-dependencies on prometheus
    from nucypher.utilities.prometheus.collector import (
        BlockchainMetricsCollector,
        MetricsCollector,
        OperatorMetricsCollector,
        StakingProviderMetricsCollector,
        UrsulaInfoMetricsCollector,
    )
    from nucypher.utilities.prometheus.metrics import create_metrics_collectors

    # flag to skip tests
    PROMETHEUS_INSTALLED = True
except ImportError:
    PROMETHEUS_INSTALLED = False

from web3.types import Timestamp


@pytest.fixture(scope="function")
def mock_operator_confirmation(random_address, mock_taco_application_agent):
    mock_taco_application_agent.is_operator_confirmed.return_value = True
    info = TACoApplicationAgent.StakingProviderInfo(
        operator=random_address,
        operator_confirmed=True,
        operator_start_timestamp=Timestamp(int(time.time()))
    )
    mock_taco_application_agent.get_staking_provider_info.return_value = info


@pytest.mark.skipif(
    condition=(not PROMETHEUS_INSTALLED),
    reason="prometheus_client is required for test",
)
def test_ursula_info_metrics_collector(test_registry, ursulas):
    ursula = random.choice(ursulas)
    collector = UrsulaInfoMetricsCollector(ursula=ursula)

    collector_registry = CollectorRegistry()
    prefix = 'test_ursula_info_metrics_collector'
    collector.initialize(metrics_prefix=prefix, registry=collector_registry)
    collector.collect()

    mode = "running" if ursula._learning_task.running else "stopped"
    learning_mode = collector_registry.get_sample_value(
        f"{prefix}_node_discovery", labels={f"{prefix}_node_discovery": f"{mode}"}
    )
    assert learning_mode == 1

    known_nodes = collector_registry.get_sample_value(f"{prefix}_known_nodes")
    assert known_nodes == len(ursula.known_nodes)

    reencryption_requests = collector_registry.get_sample_value(
        f"{prefix}_reencryption_requests"
    )
    assert reencryption_requests == 0


@pytest.mark.skipif(condition=(not PROMETHEUS_INSTALLED), reason="prometheus_client is required for test")
def test_blockchain_metrics_collector(testerchain):
    collector = BlockchainMetricsCollector(eth_endpoint=MOCK_ETH_PROVIDER_URI)

    collector_registry = CollectorRegistry()
    prefix = 'test_blockchain_metrics_collector'
    collector.initialize(metrics_prefix=prefix, registry=collector_registry)
    collector.collect()

    metric_name = f"{prefix}_eth_chain_id"
    assert metric_name in collector_registry._names_to_collectors.keys()
    chain_id = collector_registry.get_sample_value(f"{prefix}_eth_chain_id")
    assert chain_id == testerchain.client.chain_id

    metric_name = f"{prefix}_eth_block_number"
    assert metric_name in collector_registry._names_to_collectors.keys()
    block_number = collector_registry.get_sample_value(metric_name)
    assert block_number == testerchain.get_block_number()


@pytest.mark.skipif(condition=(not PROMETHEUS_INSTALLED), reason="prometheus_client is required for test")
@pytest.mark.usefixtures("mock_operator_confirmation")
def test_staking_provider_metrics_collector(test_registry, staking_providers):

    staking_provider_address = random.choice(staking_providers)
    collector = StakingProviderMetricsCollector(
        staking_provider_address=staking_provider_address,
        contract_registry=test_registry,
        eth_endpoint=MOCK_ETH_PROVIDER_URI,
    )
    collector_registry = CollectorRegistry()
    prefix = "test_staking_provider_metrics_collector"
    collector.initialize(metrics_prefix=prefix, registry=collector_registry)
    collector.collect()

    taco_application_agent = ContractAgency.get_agent(
        TACoApplicationAgent, registry=test_registry
    )

    active_stake = collector_registry.get_sample_value(
        f"{prefix}_associated_active_stake"
    )
    # only floats can be stored
    assert active_stake == float(
        int(
            taco_application_agent.get_authorized_stake(
                staking_provider=staking_provider_address
            )
        )
    )

    staking_provider_info = taco_application_agent.get_staking_provider_info(
        staking_provider=staking_provider_address
    )

    operator_confirmed = collector_registry.get_sample_value(
        f"{prefix}_operator_confirmed"
    )
    assert operator_confirmed == staking_provider_info.operator_confirmed

    operator_start = collector_registry.get_sample_value(
        f"{prefix}_operator_start_timestamp"
    )
    assert operator_start == staking_provider_info.operator_start_timestamp


@pytest.mark.skipif(condition=(not PROMETHEUS_INSTALLED), reason="prometheus_client is required for test")
def test_operator_metrics_collector(test_registry, ursulas):
    ursula = random.choice(ursulas)
    collector = OperatorMetricsCollector(
        domain=ursula.domain,
        operator_address=ursula.operator_address,
        contract_registry=test_registry,
    )
    collector_registry = CollectorRegistry()
    prefix = 'test_worker_metrics_collector'
    collector.initialize(metrics_prefix=prefix, registry=collector_registry)
    collector.collect()

    operator_eth = collector_registry.get_sample_value(f"{prefix}_operator_eth_balance")
    # only floats can be stored
    assert operator_eth == float(ursula.eth_balance)


@pytest.mark.skipif(condition=(not PROMETHEUS_INSTALLED), reason="prometheus_client is required for test")
@pytest.mark.usefixtures("mock_operator_confirmation")
def test_all_metrics_collectors_sanity_collect(ursulas):
    ursula = random.choice(ursulas)

    collector_registry = CollectorRegistry()
    prefix = 'test_all_metrics_collectors'

    metrics_collectors = create_metrics_collectors(ursula=ursula)
    initialize_collectors(metrics_collectors=metrics_collectors,
                          collector_registry=collector_registry,
                          prefix=prefix)

    for collector in metrics_collectors:
        collector.collect()


def initialize_collectors(metrics_collectors: List['MetricsCollector'],
                          collector_registry: 'CollectorRegistry',
                          prefix: str) -> None:
    for collector in metrics_collectors:
        collector.initialize(metrics_prefix=prefix, registry=collector_registry)
