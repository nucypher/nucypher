from typing import List

from nucypher.utilities.prometheus.collector import MetricsCollector
from nucypher.utilities.task import SimpleTask


class PrometheusMetricsTracker(SimpleTask):
    def __init__(self, collectors: List[MetricsCollector], interval: float):
        self.metrics_collectors = collectors
        super().__init__(interval=interval)

    def run(self) -> None:
        for collector in self.metrics_collectors:
            collector.collect()

    def handle_errors(self, *args, **kwargs) -> None:
        self.log.warn(
            "Error during prometheus metrics collection: {}".format(
                args[0].getTraceback()
            )
        )
        if not self._task.running:
            self.log.warn("Restarting prometheus metrics task!")
            self.start(now=False)  # take a breather
