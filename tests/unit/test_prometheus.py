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

from __future__ import unicode_literals

import json
import sys
import time
import unittest
from unittest.mock import Mock

import pytest

TEST_PREFIX = 'test_prefix'

try:
    # all prometheus related imports
    from prometheus_client import (
        CollectorRegistry,
        Counter,
        Enum,
        Gauge,
        Histogram,
        Info,
        Metric,
        Summary
    )

    from prometheus_client.core import GaugeHistogramMetricFamily, Timestamp

    # include dependencies that have sub-dependencies on prometheus
    from nucypher.utilities.prometheus.collector import BaseMetricsCollector, MetricsCollector
    from nucypher.utilities.prometheus.metrics import JSONMetricsResource
    from nucypher.utilities.prometheus.metrics import PrometheusMetricsConfig

    # flag to skip tests
    PROMETHEUS_INSTALLED = True
except ImportError:
    PROMETHEUS_INSTALLED = False


@pytest.mark.skipif(condition=(not PROMETHEUS_INSTALLED), reason="prometheus_client is required for test")
def test_prometheus_metrics_config():
    port = 2020

    # no port
    with pytest.raises(ValueError):
        PrometheusMetricsConfig(port=None, metrics_prefix=TEST_PREFIX)

    # no prefix
    with pytest.raises(ValueError):
        PrometheusMetricsConfig(port=port, metrics_prefix=None)

    prometheus_config = PrometheusMetricsConfig(port=port,
                                                metrics_prefix=TEST_PREFIX)

    assert prometheus_config.port == 2020
    assert prometheus_config.metrics_prefix == TEST_PREFIX
    assert prometheus_config.listen_address == ''

    # defaults
    assert prometheus_config.collection_interval == 90
    assert not prometheus_config.start_now
    assert prometheus_config.listen_address == ''

    # non-defaults
    collection_interval = 5
    listen_address = '111.111.111.111'
    prometheus_config = PrometheusMetricsConfig(port=port,
                                                metrics_prefix=TEST_PREFIX,
                                                listen_address=listen_address,
                                                collection_interval=collection_interval,
                                                start_now=True)
    assert prometheus_config.listen_address == listen_address
    assert prometheus_config.collection_interval == collection_interval
    assert prometheus_config.start_now


@pytest.mark.skipif(condition=(not PROMETHEUS_INSTALLED), reason="prometheus_client is required for test")
def test_base_metrics_collector():
    class TestBastMetricsCollector(BaseMetricsCollector):
        def __init__(self):
            self.collect_internal_run = False
            super().__init__()

        def initialize(self, metrics_prefix: str, registry: CollectorRegistry) -> None:
            self.metrics = {'testmetric': 'gauge'}

        def _collect_internal(self):
            self.collect_internal_run = True

    collector = TestBastMetricsCollector()

    # try to collect before initialization
    with pytest.raises(MetricsCollector.CollectorNotInitialized):
        collector.collect()

    # initialize and then try to collect
    registry = Mock()
    collector.initialize('None', registry)
    collector.collect()
    assert collector.collect_internal_run


@pytest.mark.skipif(condition=(not PROMETHEUS_INSTALLED), reason="prometheus_client is required for test")
class TestGenerateJSON(unittest.TestCase):
    def setUp(self):
        self.registry = CollectorRegistry()

        self.json_exporter = JSONMetricsResource(self.registry)

        # Mock time so _created values are fixed.
        self.old_time = time.time
        time.time = lambda: 123.456

    def tearDown(self):
        time.time = self.old_time

    def custom_collector(self, metric_family):
        class CustomCollector(object):
            def collect(self):
                return [metric_family]

        self.registry.register(CustomCollector())

    def test_counter(self):
        c = Counter('cc', 'A counter', registry=self.registry)
        c.inc()
        self.assertEqual(json.loads("""{"cc": {"samples": [{"sample_name": "cc_total", "labels": {}, "value": "1.0", 
        "timestamp": null, "exemplar": {}}, {"sample_name": "cc_created", "labels": {}, "value": "123.456", 
        "timestamp": null, "exemplar": {}}], "help": "A counter", "type": "counter"}}"""),
                         json.loads(self.json_exporter.generate_latest_json()))

    def test_counter_name_unit_append(self):
        # TODO review with original submitter - it seems that 'total' is a keyword for prometheus
        #  so the unit value used shouldn't be `total`.
        c = Counter('requests', 'Request counter', unit="value", registry=self.registry)
        c.inc()
        self.assertEqual(json.loads("""{"requests_value": {"samples": [{"sample_name": "requests_value_total", 
        "labels": {}, "value": "1.0", "timestamp": null, "exemplar": {}}, {"sample_name": "requests_value_created", 
        "labels": {}, "value": "123.456", "timestamp": null, "exemplar": {}}], "help": "Request counter", "type": 
        "counter"}}"""),
                         json.loads(self.json_exporter.generate_latest_json()))

    def test_counter_total(self):
        c = Counter('cc_total', 'A counter', registry=self.registry)
        c.inc()
        self.assertEqual(json.loads("""{"cc": {"samples": [{"sample_name": "cc_total", "labels": {}, "value": "1.0", 
        "timestamp": null, "exemplar": {}}, {"sample_name": "cc_created", "labels": {}, "value": "123.456", 
        "timestamp": null, "exemplar": {}}], "help": "A counter", "type": "counter"}}"""),
                         json.loads(self.json_exporter.generate_latest_json()))

    def test_gauge(self):
        g = Gauge('gg', 'A gauge', registry=self.registry)
        g.set(17)
        self.assertEqual(json.loads("""{"gg": {"samples": [{"sample_name": "gg", "labels": {}, "value": "17.0",
                                    "timestamp": null, "exemplar": {}}], "help": "A gauge", "type": "gauge"}}"""),
                         json.loads(self.json_exporter.generate_latest_json()))

    def test_summary(self):
        s = Summary('ss', 'A summary', ['a', 'b'], registry=self.registry)
        s.labels('c', 'd').observe(17)
        self.assertEqual(json.loads("""{"ss": {"samples": [{"sample_name": "ss_count", "labels": {"a": "c", 
        "b": "d"}, "value": "1.0", "timestamp": null, "exemplar": {}}, {"sample_name": "ss_sum", "labels": {"a": "c", 
        "b": "d"}, "value": "17.0", "timestamp": null, "exemplar": {}}, {"sample_name": "ss_created", "labels": {"a": 
        "c", "b": "d"}, "value": "123.456", "timestamp": null, "exemplar": {}}], "help": "A summary", 
        "type": "summary"}}"""), json.loads(self.json_exporter.generate_latest_json()))

    @unittest.skipIf(sys.version_info < (2, 7), "Test requires Python 2.7+.")
    def test_histogram(self):
        s = Histogram('hh', 'A histogram', registry=self.registry)
        s.observe(0.05)
        self.assertEqual(json.loads("""{"hh": {"samples": [{"sample_name": "hh_bucket", "labels": {"le": "0.005"}, 
        "value": "0.0", "timestamp": null, "exemplar": {}}, {"sample_name": "hh_bucket", "labels": {"le": "0.01"}, 
        "value": "0.0", "timestamp": null, "exemplar": {}}, {"sample_name": "hh_bucket", "labels": {"le": "0.025"}, 
        "value": "0.0", "timestamp": null, "exemplar": {}}, {"sample_name": "hh_bucket", "labels": {"le": "0.05"}, 
        "value": "1.0", "timestamp": null, "exemplar": {}}, {"sample_name": "hh_bucket", "labels": {"le": "0.075"}, 
        "value": "1.0", "timestamp": null, "exemplar": {}}, {"sample_name": "hh_bucket", "labels": {"le": "0.1"}, 
        "value": "1.0", "timestamp": null, "exemplar": {}}, {"sample_name": "hh_bucket", "labels": {"le": "0.25"}, 
        "value": "1.0", "timestamp": null, "exemplar": {}}, {"sample_name": "hh_bucket", "labels": {"le": "0.5"}, 
        "value": "1.0", "timestamp": null, "exemplar": {}}, {"sample_name": "hh_bucket", "labels": {"le": "0.75"}, 
        "value": "1.0", "timestamp": null, "exemplar": {}}, {"sample_name": "hh_bucket", "labels": {"le": "1.0"}, 
        "value": "1.0", "timestamp": null, "exemplar": {}}, {"sample_name": "hh_bucket", "labels": {"le": "2.5"}, 
        "value": "1.0", "timestamp": null, "exemplar": {}}, {"sample_name": "hh_bucket", "labels": {"le": "5.0"}, 
        "value": "1.0", "timestamp": null, "exemplar": {}}, {"sample_name": "hh_bucket", "labels": {"le": "7.5"}, 
        "value": "1.0", "timestamp": null, "exemplar": {}}, {"sample_name": "hh_bucket", "labels": {"le": "10.0"}, 
        "value": "1.0", "timestamp": null, "exemplar": {}}, {"sample_name": "hh_bucket", "labels": {"le": "+Inf"}, 
        "value": "1.0", "timestamp": null, "exemplar": {}}, {"sample_name": "hh_count", "labels": {}, "value": "1.0", 
        "timestamp": null, "exemplar": {}}, {"sample_name": "hh_sum", "labels": {}, "value": "0.05", "timestamp": 
        null, "exemplar": {}}, {"sample_name": "hh_created", "labels": {}, "value": "123.456", "timestamp": null, 
        "exemplar": {}}], "help": "A histogram", "type": "histogram"}}"""), json.loads(
            self.json_exporter.generate_latest_json()))

    def test_gaugehistogram(self):
        self.custom_collector(GaugeHistogramMetricFamily('gh', 'help', buckets=[('1.0', 4), ('+Inf', 5)], gsum_value=7))
        self.assertEqual(json.loads("""{"gh": {"samples": [{"sample_name": "gh_bucket", "labels": {"le": "1.0"}, 
        "value": "4.0", "timestamp": null, "exemplar": {}}, {"sample_name": "gh_bucket", "labels": {"le": "+Inf"}, 
        "value": "5.0", "timestamp": null, "exemplar": {}}, {"sample_name": "gh_gcount", "labels": {}, 
        "value": "5.0", "timestamp": null, "exemplar": {}}, {"sample_name": "gh_gsum", "labels": {}, "value": "7.0", 
        "timestamp": null, "exemplar": {}}], "help": "help", "type": "gaugehistogram"}}"""), json.loads(
            self.json_exporter.generate_latest_json()))

    def test_info(self):
        i = Info('ii', 'A info', ['a', 'b'], registry=self.registry)
        i.labels('c', 'd').info({'foo': 'bar'})
        self.assertEqual(json.loads("""{"ii": {"samples": [{"sample_name": "ii_info", "labels": {"a": "c", "b": "d", 
        "foo": "bar"}, "value": "1.0", "timestamp": null, "exemplar": {}}], "help": "A info", "type": "info"}}"""),
                         json.loads(self.json_exporter.generate_latest_json()))

    def test_enum(self):
        i = Enum('ee', 'An enum', ['a', 'b'], registry=self.registry, states=['foo', 'bar'])
        i.labels('c', 'd').state('bar')
        self.assertEqual(
            json.loads("""{"ee": {"samples": [{"sample_name": "ee", "labels": {"a": "c", "b": "d", "ee": "foo"},
                       "value": "0.0", "timestamp": null, "exemplar": {}}, {"sample_name": "ee", "labels": {"a":
                       "c", "b": "d", "ee": "bar"}, "value": "1.0", "timestamp": null, "exemplar": {}}],
                       "help": "An enum","type": "stateset"}}"""),
            json.loads(self.json_exporter.generate_latest_json()))

    def test_unicode(self):
        c = Gauge('cc', '\u4500', ['l'], registry=self.registry)
        c.labels('\u4500').inc()
        self.assertEqual(json.loads("""{"cc": {"samples": [{"sample_name": "cc", "labels": {"l": "\\u4500"}, "value":
                                    "1.0", "timestamp": null, "exemplar": {}}], "help": "\\u4500",
                                    "type": "gauge"}}"""),
                         json.loads(self.json_exporter.generate_latest_json()))

    def test_escaping(self):
        g = Gauge('cc', 'A\ngaug\\e', ['a'], registry=self.registry)
        g.labels('\\x\n"').inc(1)
        self.assertEqual(json.loads("""{"cc": {"samples": [{"sample_name": "cc", "labels": {"a": "\\\\x\\n\\""},
                                    "value": "1.0", "timestamp": null, "exemplar": {}}], "help": "A\\ngaug\\\\e",
                                    "type": "gauge"}}"""),
                         json.loads(self.json_exporter.generate_latest_json()))

    def test_nonnumber(self):
        class MyNumber(object):
            def __repr__(self):
                return "MyNumber(123)"

            def __float__(self):
                return 123.0

        class MyCollector(object):
            def collect(self):
                metric = Metric("nonnumber", "Non number", 'untyped')
                metric.add_sample("nonnumber", {}, MyNumber())
                yield metric

        self.registry.register(MyCollector())
        self.assertEqual(json.loads("""{"nonnumber": {"samples": [{"sample_name": "nonnumber", "labels": {}, "value": 
        "123.0", "timestamp": null, "exemplar": {}}], "help": "Non number", "type": "unknown"}}"""),
                         json.loads(self.json_exporter.generate_latest_json()))

    def test_timestamp(self):
        class MyCollector(object):
            def collect(self):
                metric = Metric("ts", "help", 'untyped')
                metric.add_sample("ts", {"foo": "a"}, 0, 123.456)
                metric.add_sample("ts", {"foo": "b"}, 0, -123.456)
                metric.add_sample("ts", {"foo": "c"}, 0, 123)
                metric.add_sample("ts", {"foo": "d"}, 0, Timestamp(123, 456000000))
                metric.add_sample("ts", {"foo": "e"}, 0, Timestamp(123, 456000))
                metric.add_sample("ts", {"foo": "f"}, 0, Timestamp(123, 456))
                yield metric

        self.registry.register(MyCollector())
        self.assertEqual(json.loads("""{"ts": {"samples": [{"sample_name": "ts", "labels": {"foo": "a"}, "value": 
        "0.0", "timestamp": 123.456, "exemplar": {}}, {"sample_name": "ts", "labels": {"foo": "b"}, "value": "0.0", 
        "timestamp": -123.456, "exemplar": {}}, {"sample_name": "ts", "labels": {"foo": "c"}, "value": "0.0", 
        "timestamp": 123, "exemplar": {}}, {"sample_name": "ts", "labels": {"foo": "d"}, "value": "0.0", "timestamp": 
        123.456, "exemplar": {}}, {"sample_name": "ts", "labels": {"foo": "e"}, "value": "0.0", "timestamp": 
        123.000456, "exemplar": {}}, {"sample_name": "ts", "labels": {"foo": "f"}, "value": "0.0", "timestamp": 
        123.000000456, "exemplar": {}}], "help": "help", "type": "unknown"}}"""), json.loads(
            self.json_exporter.generate_latest_json()))


if __name__ == '__main__':
    unittest.main()
