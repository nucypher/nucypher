import random
import time
from typing import List

import pytest
from prometheus_client import CollectorRegistry
from web3 import Web3
from web3.types import Timestamp

from nucypher.blockchain.eth.agents import (
    ContractAgency,
    TACoApplicationAgent,
    TACoChildApplicationAgent,
)
from nucypher.utilities.prometheus.collector import (
    BlockchainMetricsCollector,
    MetricsCollector,
    OperatorMetricsCollector,
    StakingProviderMetricsCollector,
    UrsulaInfoMetricsCollector,
)
from nucypher.utilities.prometheus.metrics import (
    PrometheusMetricsConfig,
    create_metrics_collectors,
)
from tests.constants import MOCK_ETH_PROVIDER_URI


@pytest.fixture(scope="function")
def mock_taco_child_app_info(mock_taco_child_application_agent, testerchain):
    mock_taco_child_application_agent.is_operator_confirmed.return_value = True
    mock_taco_child_application_agent.blockchain = testerchain


@pytest.fixture(scope="function")
def mock_taco_app_staking_provider_info(random_address, mock_taco_application_agent):
    info = TACoApplicationAgent.StakingProviderInfo(
        operator=random_address,
        operator_confirmed=True,
        operator_start_timestamp=Timestamp(int(time.time()))
    )
    mock_taco_application_agent.get_staking_provider_info.return_value = info


def test_start_prometheus_exporter_called(ursulas, mock_prometheus):
    port = 9101

    # Reset start_prometheus_exporter mock just in case it was previously called
    mock_prometheus.reset_mock()

    prometheus_config = PrometheusMetricsConfig(port=port)
    ursula = random.choice(ursulas)

    ursula.run(
        start_reactor=False,
        prometheus_config=prometheus_config,
        preflight=False,
        block_until_ready=False,
    )
    ursula.stop()

    mock_prometheus.assert_called_once()
    assert (
        mock_prometheus.call_args.kwargs["prometheus_config"].port == port
    ), "Wrong port set in prometheus_config"
    assert (
        mock_prometheus.call_args.kwargs["prometheus_config"].listen_address
        == prometheus_config.listen_address
    ), "Wrong listen address set in prometheus_config"
    assert (
        mock_prometheus.call_args.kwargs["prometheus_config"].collection_interval
        == prometheus_config.collection_interval
    ), "Wrong listen address set in prometheus_config"
    assert (
        mock_prometheus.call_args.kwargs["prometheus_config"].start_now
        == prometheus_config.start_now
    ), "Wrong listen address set in prometheus_config"


def test_ursula_info_metrics_collector(ursulas):
    ursula = random.choice(ursulas)
    collector = UrsulaInfoMetricsCollector(ursula=ursula)

    collector_registry = CollectorRegistry()
    collector.initialize(registry=collector_registry)
    collector.collect()

    discovery_status = collector_registry.get_sample_value("node_discovery_running")
    assert discovery_status == ursula._learning_task.running

    known_nodes = collector_registry.get_sample_value("known_nodes")
    assert known_nodes == len(ursula.known_nodes)


def test_blockchain_metrics_collector(testerchain):
    collector = BlockchainMetricsCollector(
        root_net_endpoint=MOCK_ETH_PROVIDER_URI,
        child_net_endpoint=MOCK_ETH_PROVIDER_URI,
    )

    collector_registry = CollectorRegistry()
    collector.initialize(registry=collector_registry)
    collector.collect()

    metric_name = "root_net_chain_id"
    assert metric_name in collector_registry._names_to_collectors.keys()
    chain_id = collector_registry.get_sample_value("root_net_chain_id")
    assert chain_id == testerchain.client.chain_id

    metric_name = "root_net_current_block_number"
    assert metric_name in collector_registry._names_to_collectors.keys()
    block_number = collector_registry.get_sample_value(metric_name)
    assert block_number == testerchain.get_block_number()

    metric_name = "child_net_chain_id"
    assert metric_name in collector_registry._names_to_collectors.keys()
    chain_id = collector_registry.get_sample_value("child_net_chain_id")
    assert chain_id == testerchain.client.chain_id

    metric_name = "child_net_current_block_number"
    assert metric_name in collector_registry._names_to_collectors.keys()
    block_number = collector_registry.get_sample_value(metric_name)
    assert block_number == testerchain.get_block_number()


@pytest.mark.usefixtures("mock_taco_app_staking_provider_info")
def test_staking_provider_metrics_collector(test_registry, staking_providers):

    staking_provider_address = random.choice(staking_providers)
    collector = StakingProviderMetricsCollector(
        staking_provider_address=staking_provider_address,
        contract_registry=test_registry,
        eth_endpoint=MOCK_ETH_PROVIDER_URI,
    )
    collector_registry = CollectorRegistry()
    collector.initialize(registry=collector_registry)
    collector.collect()

    taco_application_agent = ContractAgency.get_agent(
        TACoApplicationAgent,
        registry=test_registry,
        blockchain_endpoint=MOCK_ETH_PROVIDER_URI,
    )

    active_stake = collector_registry.get_sample_value("active_stake")
    # only floats can be stored
    assert active_stake == float(
        Web3.from_wei(
            taco_application_agent.get_authorized_stake(
                staking_provider=staking_provider_address
            ),
            "ether",
        )
    )

    staking_provider_info = taco_application_agent.get_staking_provider_info(
        staking_provider=staking_provider_address
    )

    operator_start = collector_registry.get_sample_value("operator_bonded_timestamp")
    assert operator_start == staking_provider_info.operator_start_timestamp


@pytest.mark.usefixtures("mock_taco_child_app_info")
def test_operator_metrics_collector(
    test_registry, operator_address, testerchain, mock_taco_child_application_agent
):
    collector = OperatorMetricsCollector(
        operator_address=operator_address,
        contract_registry=test_registry,
        polygon_endpoint=MOCK_ETH_PROVIDER_URI,
    )
    collector_registry = CollectorRegistry()
    collector.initialize(registry=collector_registry)
    collector.collect()

    taco_child_application_agent = ContractAgency.get_agent(
        TACoChildApplicationAgent,
        registry=test_registry,
        blockchain_endpoint=MOCK_ETH_PROVIDER_URI,
    )

    operator_confirmed = collector_registry.get_sample_value("operator_confirmed")
    assert operator_confirmed
    assert operator_confirmed == taco_child_application_agent.is_operator_confirmed(
        operator_address
    )

    operator_matic_balance = collector_registry.get_sample_value(
        "operator_matic_balance"
    )
    assert operator_matic_balance == Web3.from_wei(
        testerchain.client.get_balance(operator_address), "ether"
    )

    # switch operator confirmed and collect again
    mock_taco_child_application_agent.is_operator_confirmed.return_value = False
    collector.collect()
    operator_confirmed = collector_registry.get_sample_value("operator_confirmed")
    assert not operator_confirmed


@pytest.mark.usefixtures("mock_taco_child_app_info")
@pytest.mark.usefixtures("mock_taco_app_staking_provider_info")
def test_all_metrics_collectors_sanity_collect(ursulas):
    ursula = random.choice(ursulas)

    collector_registry = CollectorRegistry()

    metrics_collectors = create_metrics_collectors(ursula=ursula)
    initialize_collectors(
        metrics_collectors=metrics_collectors, collector_registry=collector_registry
    )

    for collector in metrics_collectors:
        collector.collect()


def initialize_collectors(
    metrics_collectors: List["MetricsCollector"],
    collector_registry: "CollectorRegistry",
) -> None:
    for collector in metrics_collectors:
        collector.initialize(registry=collector_registry)
