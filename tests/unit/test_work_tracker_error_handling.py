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

import pytest_twisted
from twisted.internet import task
from twisted.internet import threads
from twisted.internet.task import Clock
from twisted.logger import globalLogPublisher, LogLevel

from nucypher.blockchain.eth.token import WorkTracker
from nucypher.utilities.logging import Logger, GlobalLoggerSettings


class WorkTrackerThatFailsHalfTheTime(WorkTracker):

    @property
    def staking_agent(self):
        class MockStakingAgent:
            def get_current_period(self):
                return 1

        return MockStakingAgent()

    def _do_work(self) -> None:
        self.attempts += 1
        if self.attempts % 2:
            raise BaseException("zomg something went wrong")
        self.workdone += 1

    def _crash_gracefully(self, failure=None) -> None:
        assert failure.getErrorMessage() == 'zomg something went wrong'

    def __init__(self, clock, abort_on_error, *args, **kwargs):
        self.workdone = 0
        self.attempts = 0
        self.CLOCK = clock
        self.log = Logger('stake-tracker')
        self._tracking_task = task.LoopingCall(self._do_work)
        self._tracking_task.clock = self.CLOCK
        self._abort_on_error = abort_on_error


@pytest_twisted.inlineCallbacks
def test_worker_failure_resilience():
    # Control time
    clock = Clock()
    worktracker = WorkTrackerThatFailsHalfTheTime(clock, False)

    def advance_one_cycle(_):
        clock.advance(WorkTrackerThatFailsHalfTheTime.INTERVAL_CEIL)

    def checkworkstate(_):
        assert worktracker.attempts / 2 == worktracker.workdone

    def start():
        worktracker.start()

    d = threads.deferToThread(start)

    for i in range(10):
        d.addCallback(advance_one_cycle)
        d.addCallback(checkworkstate)

    warnings = []

    def warning_trapper(event):
        if event['log_level'] == LogLevel.warn:
            warnings.append(event)

    globalLogPublisher.addObserver(warning_trapper)
    yield d
    globalLogPublisher.removeObserver(warning_trapper)

    assert warnings
    for warning in warnings:
        assert warning['failure'].getErrorMessage() == "zomg something went wrong"


@pytest_twisted.inlineCallbacks
def test_worker_failure_non_resilience():
    """
    abort on error is True for this one
    """

    # Control time
    clock = Clock()
    worktracker = WorkTrackerThatFailsHalfTheTime(clock, True)

    def advance_one_cycle(_):
        clock.advance(WorkTrackerThatFailsHalfTheTime.INTERVAL_CEIL)

    def checkworkstate(_):
        assert worktracker.workdone == 0

    def start():
        worktracker.start()

    d = threads.deferToThread(start)

    for i in range(10):
        d.addCallback(advance_one_cycle)
        d.addCallback(checkworkstate)

    critical = []

    def critical_trapper(event):
        if event['log_level'] == LogLevel.critical:
            critical.append(event)

    globalLogPublisher.addObserver(critical_trapper)

    with GlobalLoggerSettings.pause_all_logging_while():  # To suppress the traceback being displayed from the cricial error.
        globalLogPublisher.addObserver(critical_trapper)
        yield d
        globalLogPublisher.removeObserver(critical_trapper)

    assert len(critical) == 1
    assert critical[0]['failure'].getErrorMessage() == "zomg something went wrong"
