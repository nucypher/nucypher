from prometheus_client import REGISTRY
from web3 import Web3

from nucypher.utilities.prometheus.metrics import (
    PrometheusMetricsConfig,
    start_prometheus_exporter,
)
from tests.utils.ursula import select_test_port


def test_start_prometheus_exporter(ursulas, testerchain):
    ursula = ursulas[0]
    task = None
    try:
        port = select_test_port()
        config = PrometheusMetricsConfig(
            port=port, start_now=True, collection_interval=5
        )
        task = start_prometheus_exporter(ursula, config, REGISTRY)
        REGISTRY.collect()

        assert bool(REGISTRY.get_sample_value("operator_confirmed"))

        authorized_stake = ursula.application_agent.get_authorized_stake(
            staking_provider=ursula.checksum_address
        )
        assert REGISTRY.get_sample_value("active_stake") == float(
            Web3.from_wei(authorized_stake, "ether")
        )
        assert (
            REGISTRY.get_sample_value("root_net_chain_id")
            == ursula.application_agent.blockchain.client.chain_id
        )
        assert (
            REGISTRY.get_sample_value("child_net_chain_id")
            == ursula.child_application_agent.blockchain.client.chain_id
        )
        assert REGISTRY.get_sample_value("known_nodes") == len(ursula.known_nodes)
        assert (
            bool(REGISTRY.get_sample_value("node_discovery_running"))
            == ursula._learning_task.running
        )
    finally:
        task.stop()
