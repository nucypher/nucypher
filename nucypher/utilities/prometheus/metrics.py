
from nucypher.exceptions import DevelopmentInstallationRequired

try:
    from prometheus_client.core import Timestamp
    from prometheus_client.registry import REGISTRY, CollectorRegistry
    from prometheus_client.utils import floatToGoString
except ImportError:
    raise DevelopmentInstallationRequired(importable_name='prometheus_client')

import json
from typing import List

from twisted.internet import reactor, task
from twisted.web.resource import Resource

from nucypher.characters import lawful
from nucypher.utilities.prometheus.collector import (
    BlockchainMetricsCollector,
    MetricsCollector,
    OperatorMetricsCollector,
    StakingProviderMetricsCollector,
    UrsulaInfoMetricsCollector,
)


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


def start_prometheus_exporter(
    ursula: "lawful.Ursula",
    prometheus_config: PrometheusMetricsConfig,
    registry: CollectorRegistry = REGISTRY,
) -> None:
    """Configure, collect, and serve prometheus metrics."""
    from prometheus_client.twisted import MetricsResource
    from twisted.web.resource import Resource
    from twisted.web.server import Site

    metrics_collectors = create_metrics_collectors(ursula)
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


def create_metrics_collectors(ursula: "lawful.Ursula") -> List[MetricsCollector]:
    """Create collectors used to obtain metrics."""
    collectors: List[MetricsCollector] = [UrsulaInfoMetricsCollector(ursula=ursula)]

    # Blockchain prometheus
    # TODO possible include information about payment
    collectors.append(BlockchainMetricsCollector(eth_provider_uri=ursula.eth_endpoint))

    # Staking Provider prometheus
    collectors.append(
        StakingProviderMetricsCollector(
            staking_provider_address=ursula.checksum_address,
            contract_registry=ursula.registry,
            eth_provider_uri=ursula.eth_endpoint,
        )
    )

    # Operator prometheus
    collectors.append(
        OperatorMetricsCollector(
            domain=ursula.domain,
            operator_address=ursula.operator_address,
            contract_registry=ursula.registry,
        )
    )

    return collectors
