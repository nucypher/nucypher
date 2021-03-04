"""
 This file is part of nucypher.

 nucypher is free software: you can redistribute it and/or modify
 it under the terms of the GNU Affero General Public License as published by
 the Free Software Foundation, either version 3 of the License, or
 (at your option) any later version.

 nucypher is distributed in the hope that it will be useful,
 but WITHOUT ANY WARRANTY; without even the implied warranty of
 MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 GNU Affero General Public License for more details.

 You should have received a copy of the GNU Affero General Public License
 along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""

import random
from unittest.mock import patch

from prometheus_client import CollectorRegistry

from nucypher.utilities.prometheus.collector import (
    UrsulaInfoMetricsCollector,
    BlockchainMetricsCollector,
    StakerMetricsCollector,
    WorkerMetricsCollector,
    CommitmentMadeEventMetricsCollector
)
from nucypher.utilities.prometheus.metrics import create_staking_events_metric_collectors
from tests.constants import TEST_PROVIDER_URI


def test_ursula_info_metrics_collector(test_registry,
                                       blockchain_ursulas,
                                       agency):
    ursula = random.choice(blockchain_ursulas)
    collector = UrsulaInfoMetricsCollector(ursula=ursula)

    collector_registry = CollectorRegistry()
    prefix = 'test_ursula_info_metrics_collector'
    collector.initialize(metrics_prefix=prefix, registry=collector_registry)
    collector.collect()

    known_nodes = collector_registry.get_sample_value('test_ursula_info_metrics_collector_known_nodes')
    assert known_nodes == len(ursula.known_nodes)

    availability_score = collector_registry.get_sample_value('test_ursula_info_metrics_collector_availability_score')
    assert availability_score == (ursula._availability_tracker.score
                                  if (ursula._availability_tracker and ursula._availability_tracker.running) else -1)

    policies_held = collector_registry.get_sample_value('test_ursula_info_metrics_collector_policies_held')
    assert policies_held == 0

    work_orders = collector_registry.get_sample_value('test_ursula_info_metrics_collector_work_orders')
    assert work_orders == 0

    mode = 'running' if ursula._learning_task.running else 'stopped'
    learning_mode = collector_registry.get_sample_value('test_ursula_info_metrics_collector_node_discovery',
                                              labels={'test_ursula_info_metrics_collector_node_discovery': f'{mode}'})
    assert learning_mode == 1


def test_blockchain_metrics_collector(testerchain):
    collector = BlockchainMetricsCollector(provider_uri=TEST_PROVIDER_URI)

    collector_registry = CollectorRegistry()
    prefix = 'test_blockchain_metrics_collector'
    collector.initialize(metrics_prefix=prefix, registry=collector_registry)
    collector.collect()

    metric_name = f"{prefix}_current_eth_block_number"
    assert metric_name in collector_registry._names_to_collectors.keys()

    block_number = collector_registry.get_sample_value(metric_name)
    assert block_number == testerchain.get_block_number()


def test_staker_metrics_collector(test_registry, stakers):
    staker = random.choice(stakers)
    collector = StakerMetricsCollector(domain=staker.network,
                                       staker_address=staker.checksum_address,
                                       contract_registry=test_registry)
    collector_registry = CollectorRegistry()
    prefix = 'test_staker_metrics_collector'
    collector.initialize(metrics_prefix=prefix, registry=collector_registry)
    collector.collect()

    current_period = collector_registry.get_sample_value(f'{prefix}_current_period')
    assert current_period == staker.staking_agent.get_current_period()

    # only floats can be stored
    eth_balance = collector_registry.get_sample_value(f'{prefix}_staker_eth_balance')
    assert eth_balance == float(staker.eth_balance)

    nu_balance = collector_registry.get_sample_value(f'{prefix}_staker_token_balance')
    assert nu_balance == float(int(staker.token_balance))

    sub_stakes_count = collector_registry.get_sample_value(f'{prefix}_substakes_count')
    assert sub_stakes_count == \
           staker.staking_agent.contract.functions.getSubStakesLength(staker.checksum_address).call()

    locked_tokens = collector_registry.get_sample_value(f'{prefix}_active_stake')
    assert locked_tokens == float(staker.locked_tokens().to_nunits())

    owned_tokens = collector_registry.get_sample_value(f'{prefix}_owned_tokens')
    assert owned_tokens == float(staker.owned_tokens().to_nunits())

    unlocked_tokens = collector_registry.get_sample_value(f'{prefix}_unlocked_tokens')
    assert unlocked_tokens == (owned_tokens - locked_tokens)

    missing_commitments = collector_registry.get_sample_value(f'{prefix}_missing_commitments')
    assert missing_commitments == staker.missing_commitments


def test_worker_metrics_collector(test_registry, blockchain_ursulas):
    ursula = random.choice(blockchain_ursulas)
    collector = WorkerMetricsCollector(domain=ursula.domain,
                                       worker_address=ursula.worker_address,
                                       contract_registry=test_registry)
    collector_registry = CollectorRegistry()
    prefix = 'test_worker_metrics_collector'
    collector.initialize(metrics_prefix=prefix, registry=collector_registry)
    collector.collect()

    worker_eth = collector_registry.get_sample_value(f'{prefix}_worker_eth_balance')
    assert worker_eth == float(ursula.eth_balance)

    worker_nunits = collector_registry.get_sample_value(f'{prefix}_worker_token_balance')
    assert worker_nunits == float(int(ursula.token_balance))


def test_create_staking_events_metric_collectors(blockchain_ursulas):
    ursula = random.choice(blockchain_ursulas)

    collector_registry = CollectorRegistry()
    prefix = 'test_create_staking_events_metric_collectors'
    event_collectors = create_staking_events_metric_collectors(ursula=ursula, metrics_prefix=prefix)

    for collector in event_collectors:
        if isinstance(collector, CommitmentMadeEventMetricsCollector):
            continue  # skip
        collector.initialize(metrics_prefix=prefix, registry=collector_registry)
        collector.collect()

    # Restake set
    restake_set = collector_registry.get_sample_value(f'{prefix}_restaking')
    assert restake_set == ursula.staking_agent.is_restaking(ursula.checksum_address)

    # WindDown set
    restake_set = collector_registry.get_sample_value(f'{prefix}_wind_down')
    assert restake_set == ursula.staking_agent.is_winding_down(ursula.checksum_address)

    # Worker bonded
    current_worker_is_me = collector_registry.get_sample_value(f'{prefix}_current_worker_is_me')
    assert current_worker_is_me == \
           (ursula.staking_agent.get_worker_from_staker(ursula.checksum_address) == ursula.worker_address)
