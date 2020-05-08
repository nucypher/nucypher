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
        return self.generate_latest_json()

    @staticmethod
    def get_sample_labels(labels):
        if not labels:
            return {}
        return {k: v for k, v in sorted(labels.items())}

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
        exemplar_labels = {k: v for k, v
                           in sorted(sample.exemplar.labels.items())}
        return {
            "labels": exemplar_labels,
            "value": floatToGoString(sample.exemplar.value),
            "timestamp": sample.exemplar.timestamp
        }

    def generate_latest_json(self):
        """
        Returns the metrics from the registry
        in latest JSON format as a string.
        """
        output = {}
        for metric in self.registry.collect():
            try:
                for sample in metric.samples:
                    output[sample.name] = {
                        "labels": self.get_sample_labels(sample.labels),
                        "value": floatToGoString(sample.value),
                        "timestamp": sample.timestamp,
                        "exemplar": self.get_exemplar(sample, metric)
                    }
            except Exception as exception:
                exception.args = (exception.args or ('',)) + (metric,)
                raise

        return json.dumps(output).encode('utf-8')
