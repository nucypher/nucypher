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
from nucypher.blockchain.eth.networks import NetworksInventory
from nucypher.exceptions import DevelopmentInstallationRequired

try:
    from prometheus_client import Gauge, Enum, Counter, Info, Histogram, Summary
except ImportError:
    raise ImportError('"prometheus_client" must be installed - run "pip install nucypher[ursula]" and try again.')

try:
    from prometheus_client.core import Timestamp
    from prometheus_client.registry import CollectorRegistry, REGISTRY
    from prometheus_client.utils import floatToGoString
except ImportError:
    raise DevelopmentInstallationRequired(importable_name='prometheus_client')

import json

from nucypher.utilities.prometheus.collector import (
    MetricsCollector,
    UrsulaInfoMetricsCollector,
    BlockchainMetricsCollector,
    StakerMetricsCollector,
    WorkerMetricsCollector,
    WorkLockMetricsCollector,
    EventMetricsCollector,
    ReStakeEventMetricsCollector,
    WindDownEventMetricsCollector,
    WorkerBondedEventMetricsCollector,
    CommitmentMadeEventMetricsCollector,
    WorkLockRefundEventMetricsCollector)

from typing import List

from twisted.internet import reactor, task
from twisted.web.resource import Resource

from nucypher.blockchain.eth.agents import ContractAgency, StakingEscrowAgent, PolicyManagerAgent, WorkLockAgent


class PrometheusMetricsConfig:
    """Prometheus configuration."""
    def __init__(self,
                 port: int,
                 metrics_prefix: str,
                 listen_address: str = '',  # default to localhost ip
                 collection_interval: int = 90,  # every 1.5 minutes
                 start_now: bool = False):

        if not port:
            raise ValueError('port must be provided')
        if not metrics_prefix:
            raise ValueError('metrics prefix must be provided')

        self.port = port
        self.metrics_prefix = metrics_prefix
        self.listen_address = listen_address
        self.collection_interval = collection_interval
        self.start_now = start_now


class MetricsEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Timestamp):
            return obj.__float__()
        return json.JSONEncoder.default(self, obj)


class JSONMetricsResource(Resource):
    """
    Twisted ``Resource`` that serves prometheus in JSON.
    """
    isLeaf = True

    def __init__(self, registry=REGISTRY):
        super().__init__()
        self.registry = registry

    def render_GET(self, request):
        request.setHeader(b'Content-Type', "text/json")
        return self.generate_latest_json()

    @staticmethod
    def get_exemplar(sample, metric):
        if not sample.exemplar:
            return {}
        elif metric.type not in ('histogram', 'gaugehistogram') or not sample.name.endswith('_bucket'):
            raise ValueError(
                "Metric {} has exemplars, but is not a "
                "histogram bucket".format(metric.name)
            )
        return {
            "labels": sample.exemplar.labels,
            "value": floatToGoString(sample.exemplar.value),
            "timestamp": sample.exemplar.timestamp
        }

    def get_sample(self, sample, metric):
        return {
            "sample_name": sample.name,
            "labels": sample.labels,
            "value": floatToGoString(sample.value),
            "timestamp": sample.timestamp,
            "exemplar": self.get_exemplar(sample, metric)
        }

    def get_metric(self, metric):
        return {
            "samples": [self.get_sample(sample, metric) for sample in metric.samples],
            "help": metric.documentation,
            "type": metric.type
        }

    def generate_latest_json(self):
        """
        Returns the prometheus from the registry
        in latest JSON format as a string.
        """
        output = {}
        for metric in self.registry.collect():
            try:
                output[metric.name] = self.get_metric(metric)
            except Exception as exception:
                exception.args = (exception.args or ('',)) + (metric,)
                raise

        json_dump = json.dumps(output, cls=MetricsEncoder).encode('utf-8')
        return json_dump


def collect_prometheus_metrics(metrics_collectors: List[MetricsCollector]) -> None:
    for collector in metrics_collectors:
        collector.collect()


def start_prometheus_exporter(ursula: 'Ursula',
                              prometheus_config: PrometheusMetricsConfig,
                              registry: CollectorRegistry = REGISTRY) -> None:
    """Configure, collect, and serve prometheus metrics."""
    from prometheus_client.twisted import MetricsResource
    from twisted.web.resource import Resource
    from twisted.web.server import Site

    metrics_collectors = create_metrics_collectors(ursula, prometheus_config.metrics_prefix)
    # initialize collectors
    for collector in metrics_collectors:
        collector.initialize(metrics_prefix=prometheus_config.metrics_prefix, registry=registry)

    # TODO: was never used
    # "requests_counter": Counter(f'{metrics_prefix}_http_failures', 'HTTP Failures', ['method', 'endpoint']),

    # Scheduling
    metrics_task = task.LoopingCall(collect_prometheus_metrics,
                                    metrics_collectors=metrics_collectors)
    metrics_task.start(interval=prometheus_config.collection_interval,
                       now=prometheus_config.start_now)

    # WSGI Service
    root = Resource()
    root.putChild(b'metrics', MetricsResource())
    root.putChild(b'json_metrics', JSONMetricsResource())
    factory = Site(root)
    reactor.listenTCP(prometheus_config.port, factory, interface=prometheus_config.listen_address)


def create_metrics_collectors(ursula: 'Ursula', metrics_prefix: str) -> List[MetricsCollector]:
    """Create collectors used to obtain metrics."""
    collectors: List[MetricsCollector] = [UrsulaInfoMetricsCollector(ursula=ursula)]

    if not ursula.federated_only:
        # Blockchain prometheus
        collectors.append(BlockchainMetricsCollector(provider_uri=ursula.provider_uri))

        # Staker prometheus
        collectors.append(StakerMetricsCollector(domain=ursula.domain,
                                                 staker_address=ursula.checksum_address,
                                                 contract_registry=ursula.registry))

        # Worker prometheus
        collectors.append(WorkerMetricsCollector(domain=ursula.domain,
                                                 worker_address=ursula.worker_address,
                                                 contract_registry=ursula.registry))

        #
        # Events
        #

        # Staking Events
        staking_events_collectors = create_staking_events_metric_collectors(ursula=ursula,
                                                                            metrics_prefix=metrics_prefix)
        collectors.extend(staking_events_collectors)

        # Policy Events
        policy_events_collectors = create_policy_events_metric_collectors(ursula=ursula,
                                                                          metrics_prefix=metrics_prefix)
        collectors.extend(policy_events_collectors)

        #
        # WorkLock information - only collected for mainnet
        #
        if ursula.domain == NetworksInventory.MAINNET:
            # WorkLock metrics
            collectors.append(WorkLockMetricsCollector(staker_address=ursula.checksum_address,
                                                       contract_registry=ursula.registry))

            # WorkLock Events
            worklock_events_collectors = create_worklock_events_metric_collectors(ursula=ursula,
                                                                                  metrics_prefix=metrics_prefix)
            collectors.extend(worklock_events_collectors)

    return collectors


def create_staking_events_metric_collectors(ursula: 'Ursula', metrics_prefix: str) -> List[MetricsCollector]:
    """Create collectors for staking-related events."""
    collectors: List[MetricsCollector] = []
    staking_agent = ContractAgency.get_agent(StakingEscrowAgent, registry=ursula.registry)

    staker_address = ursula.checksum_address

    # CommitmentMade
    collectors.append(CommitmentMadeEventMetricsCollector(
        event_args_config={
            "value": (Gauge,
                      f'{metrics_prefix}_activity_confirmed_value',
                      'CommitmentMade to next period with value of locked tokens'),
            "period": (Gauge, f'{metrics_prefix}_activity_confirmed_period', 'Commitment made for period')
        },
        staker_address=staker_address,
        contract_agent=staking_agent))

    # Minted
    collectors.append(EventMetricsCollector(
        event_name='Minted',
        event_args_config={
            "value": (Gauge, f'{metrics_prefix}_mined_value', 'Minted value'),
            "period": (Gauge, f'{metrics_prefix}_mined_period', 'Minted period'),
            "block_number": (Gauge, f'{metrics_prefix}_mined_block_number', 'Minted block number')
        },
        argument_filters={'staker': staker_address},
        contract_agent=staking_agent))

    # Slashed
    collectors.append(EventMetricsCollector(
        event_name='Slashed',
        event_args_config={
            "penalty": (Gauge, f'{metrics_prefix}_last_slashed_penalty', 'Penalty for slashing'),
            "block_number": (Gauge,
                             f'{metrics_prefix}_last_slashed_penalty_block_number',
                             'Slashed penalty block number')
        },
        argument_filters={'staker': staker_address},
        contract_agent=staking_agent))

    # RestakeSet
    collectors.append(ReStakeEventMetricsCollector(
        event_args_config={
            "reStake": (Gauge, f'{metrics_prefix}_restaking', 'Restake set')
        },
        staker_address=staker_address,
        contract_agent=staking_agent))

    # WindDownSet
    collectors.append(WindDownEventMetricsCollector(
        event_args_config={
            "windDown": (Gauge, f'{metrics_prefix}_wind_down', 'is windDown')
        },
        staker_address=staker_address,
        contract_agent=staking_agent))

    # WorkerBonded
    collectors.append(WorkerBondedEventMetricsCollector(
        event_args_config={
            "startPeriod": (Gauge, f'{metrics_prefix}_worker_set_start_period', 'New worker was bonded'),
            "block_number": (Gauge, f'{metrics_prefix}_worker_set_block_number', 'WorkerBonded block number')
        },
        staker_address=staker_address,
        worker_address=ursula.worker_address,
        contract_agent=staking_agent))

    return collectors


def create_worklock_events_metric_collectors(ursula: 'Ursula', metrics_prefix: str) -> List[MetricsCollector]:
    """Create collectors for worklock-related events."""
    collectors: List[MetricsCollector] = []
    worklock_agent = ContractAgency.get_agent(WorkLockAgent, registry=ursula.registry)
    staker_address = ursula.checksum_address

    # Refund
    collectors.append(WorkLockRefundEventMetricsCollector(
        event_args_config={
            "refundETH": (Gauge, f'{metrics_prefix}_worklock_refund_refundETH',
                          'Refunded ETH'),
        },
        staker_address=staker_address,
        contract_agent=worklock_agent,
    ))

    return collectors


def create_policy_events_metric_collectors(ursula: 'Ursula', metrics_prefix: str) -> List[MetricsCollector]:
    """Create collectors for policy-related events."""
    collectors: List[MetricsCollector] = []
    policy_manager_agent = ContractAgency.get_agent(PolicyManagerAgent, registry=ursula.registry)

    # Withdrawn
    collectors.append(EventMetricsCollector(
        event_name='Withdrawn',
        event_args_config={
            "value": (Gauge, f'{metrics_prefix}_policy_withdrawn_reward', 'Policy reward')
        },
        argument_filters={"recipient": ursula.checksum_address},
        contract_agent=policy_manager_agent))

    return collectors
