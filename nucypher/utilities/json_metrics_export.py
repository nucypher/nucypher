from __future__ import unicode_literals
from prometheus_client.utils import floatToGoString
from twisted.web.resource import Resource
from prometheus_client.registry import REGISTRY
import json


class JSONMetricsResource(Resource):
    """
    Twisted ``Resource`` that serves metrics in JSON.
    """
    isLeaf = True

    def __init__(self, registry=REGISTRY):
        self.registry = registry

    def render_GET(self, request):
        request.setHeader(b'Content-Type', "text/json")
        return generate_latest_json(self.registry)


def generate_latest_json(registry):
    '''Returns the metrics from the registry in latest JSON format as a string.'''
    output = {}
    for metric in registry.collect():
        try:
            for s in metric.samples:
                sample_labels = {}
                if s.labels:
                    sample_labels = {k: v.replace('\\', r'\\').replace('\n', r'\n').replace('"', r'\"') for k, v in
                                     sorted(s.labels.items())}
                exemplar = {}
                if s.exemplar:
                    if metric.type not in ('histogram', 'gaugehistogram') or not s.name.endswith('_bucket'):
                        raise ValueError("Metric {0} has exemplars, but is not a histogram bucket".format(metric.name))
                    exemplar_labels = {k: v.replace('\\', r'\\').replace('\n', r'\n').replace('"', r'\"')
                                       for k, v in sorted(s.exemplar.labels.items())}
                    exemplar = {
                        "labels": exemplar_labels,
                        "value": floatToGoString(s.exemplar.value),
                        "timestamp": s.exemplar.timestamp
                    }
                output[s.name] = {
                    "labels": sample_labels,
                    "value": floatToGoString(s.value),
                    "timestamp": s.timestamp,
                    "exemplar": exemplar
                }
        except Exception as exception:
            exception.args = (exception.args or ('',)) + (metric,)
            raise

    return json.dumps(output).encode('utf-8')
