import pytest_twisted
from twisted.internet import task
from twisted.internet import threads
from twisted.internet.task import Clock

from nucypher.blockchain.eth.token import WorkTracker
from nucypher.utilities.logging import Logger


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

    yield d


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

    yield d
