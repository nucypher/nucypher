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

from abc import ABC, abstractmethod

from twisted.internet.task import LoopingCall
from twisted.python.failure import Failure

from nucypher.utilities.logging import Logger


class SimpleTask(ABC):
    """Simple Twisted Looping Call abstract base class."""
    INTERVAL = 60  # 60s default

    def __init__(self):
        self.log = Logger(self.__class__.__name__)
        self.__task = LoopingCall(self.run)

    @property
    def running(self) -> bool:
        """Determine whether the task is already running."""
        return self.__task.running

    def start(self, now: bool = False):
        """Start task."""
        if not self.running:
            d = self.__task.start(interval=self.INTERVAL, now=now)
            d.addErrback(self.handle_errors)

    def stop(self):
        """Stop task."""
        if self.running:
            self.__task.stop()

    @abstractmethod
    def run(self):
        """Task method that should be periodically run."""
        raise NotImplementedError

    @abstractmethod
    def handle_errors(self, *args, **kwargs):
        """Error callback for error handling during execution."""
        raise NotImplementedError

    @staticmethod
    def clean_traceback(failure: Failure) -> str:
        # FIXME: Amazing.
        cleaned_traceback = failure.getTraceback().replace('{', '').replace('}', '')
        return cleaned_traceback
