from __future__ import unicode_literals
from prometheus_client.utils import floatToGoString
from twisted.web.resource import Resource
from prometheus_client.registry import REGISTRY
import json
from prometheus_client.core import Timestamp


class MetricsEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Timestamp):
            return obj.__float__()
        return json.JSONEncoder.default(self, obj)


class JSONMetricsResource(Resource):
    """
    Twisted ``Resource`` that serves metrics in JSON.
    """
    isLeaf = True

    def __init__(self, registry=REGISTRY):
        self.registry = registry

    def render_GET(self, request):
        request.setHeader(b'Content-Type', "text/json")
        return self.generate_latest_json()

    @staticmethod
    def get_exemplar(sample, metric):
        if not sample.exemplar:
            return {}
        elif metric.type not in ('histogram', 'gaugehistogram') \
                or not sample.name.endswith('_bucket'):
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
        Returns the metrics from the registry
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
