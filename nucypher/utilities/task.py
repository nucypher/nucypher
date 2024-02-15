from abc import ABC, abstractmethod

from twisted.internet import reactor
from twisted.internet.task import LoopingCall
from twisted.python.failure import Failure

from nucypher.utilities.logging import Logger


class SimpleTask(ABC):
    """Simple Twisted Looping Call abstract base class."""

    INTERVAL = NotImplemented
    CLOCK = reactor

    def __init__(self, interval: float = None):
        self.interval = interval or self.INTERVAL
        self.log = Logger(self.__class__.__name__)
        self._task = LoopingCall(self.run)
        self._task.clock = self.CLOCK

    @property
    def running(self) -> bool:
        """Determine whether the task is already running."""
        return self._task.running

    def start(self, now: bool = False) -> None:
        """Start task."""
        if not self.running:
            d = self._task.start(interval=self.interval, now=now)
            d.addErrback(self.handle_errors)

    def stop(self) -> None:
        """Stop task."""
        if self.running:
            self._task.stop()

    @abstractmethod
    def run(self) -> None:
        """Task method that should be periodically run."""
        raise NotImplementedError

    @abstractmethod
    def handle_errors(self, *args, **kwargs) -> None:
        """Error callback for error handling during execution."""
        raise NotImplementedError

    @staticmethod
    def clean_traceback(failure: Failure) -> str:
        # FIXME: Amazing.
        cleaned_traceback = failure.getTraceback().replace("{", "").replace("}", "")
        return cleaned_traceback
