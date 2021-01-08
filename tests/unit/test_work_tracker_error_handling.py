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


import pytest
import pytest_twisted
from twisted.internet import task
from twisted.internet import threads
from twisted.internet.task import Clock
from twisted.logger import globalLogPublisher, LogLevel

from nucypher.utilities.gas_strategies import GasStrategyError

from nucypher.blockchain.eth.token import WorkTracker
from nucypher.utilities.logging import Logger, GlobalLoggerSettings

logger = Logger("test-logging")


def log(message):
    logger.debug(message)


class WorkTrackerArbitraryFailureConditions(WorkTracker):

    def __init__(self, clock, abort_on_error, *args, **kwargs):
        self.workdone = 0
        self.attempts = 0
        self.CLOCK = clock
        self.log = Logger('stake-tracker')
        self._tracking_task = task.LoopingCall(self._do_work)
        self._tracking_task.clock = self.CLOCK
        self._abort_on_error = abort_on_error
        self._consecutive_fails = 0

    def _do_work(self) -> None:
        self.attempts += 1

        self.check_success_conditions()

        self.workdone += 1
        self._consecutive_fails = 0

    @property
    def staking_agent(self):
        class MockStakingAgent:
            def get_current_period(self):
                return 1

        return MockStakingAgent()

    def _crash_gracefully(self, failure=None) -> None:
        assert 'zomg something went wrong' in failure.getErrorMessage()

    def check_success_conditions(self):
        pass


class WorkTrackerThatFailsHalfTheTime(WorkTrackerArbitraryFailureConditions):

    def check_success_conditions(self):
        if self.attempts % 2:
            raise BaseException(f"zomg something went wrong: {self.attempts} % 2 = {self.attempts % 2}")


@pytest_twisted.inlineCallbacks
def test_worker_failure_resilience():
    # Control time
    clock = Clock()
    worktracker = WorkTrackerThatFailsHalfTheTime(clock, False)

    def advance_one_cycle(_):
        clock.advance(worktracker.INTERVAL_CEIL)

    def checkworkstate(_):
        if worktracker.attempts % 2:
            assert worktracker._consecutive_fails > 0
        else:
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
        assert "zomg something went wrong" in warning['failure'].getErrorMessage()


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
    assert "zomg something went wrong" in critical[0]['failure'].getErrorMessage()


class WorkTrackerThatFailsFor12HoursThenSucceeds(WorkTrackerArbitraryFailureConditions):

    def check_success_conditions(self):
        if self.CLOCK.seconds() < 60*60*12:
            raise GasStrategyError("Gas is too expensive in the morning.")

    @classmethod
    def random_interval(cls, fails=None):
        return cls.INTERVAL_FLOOR


@pytest_twisted.inlineCallbacks
def test_worker_rate_limiting():
    """
    abort on error is True for this one
    """

    # Control time
    clock = Clock()
    worktracker = WorkTrackerThatFailsFor12HoursThenSucceeds(clock, False)

    seconds_per_step = 1200 # this can be anything.
    # The behavior we want to fix in production is equivalent to seconds_per_step = 1
    # This test does pass with that value but it takes awhile and makes a lot of log file
    # so lets go with 20 minute intervals

    # with a value of 1, we get this log output after 43201 cycles (12 hours and 1 second)
    # [test-logging#debug] 12 hour fail worktracker: attempts: 50, clock: 43201.0, work: 1

    def advance_one_cycle(_):
        clock.advance(seconds_per_step)

    def checkfailures(_):
        log(f"12 hour fail worktracker: attempts: {worktracker.attempts}, "
            f"clock: {worktracker.CLOCK.seconds()}, work: {worktracker.workdone}")
        assert worktracker.attempts <= (worktracker.CLOCK.seconds() / worktracker.INTERVAL_FLOOR) + 2  # account for the single instant retry

    def start():
        worktracker.start()

    d = threads.deferToThread(start)

    iterations = (60*60*12)+1  # 12 hours plus one second
    for i in range(0, iterations, seconds_per_step):
        d.addCallback(advance_one_cycle)
        d.addCallback(checkfailures)

    yield d

    assert worktracker.workdone
