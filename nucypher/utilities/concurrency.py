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


import time
from queue import Queue, Empty
from threading import Thread, Event, Lock, Timer, get_ident
from typing import Callable, List, Any, Optional, Dict
import sys

from constant_sorrow.constants import PRODUCER_STOPPED, TIMEOUT_TRIGGERED
from twisted.python.threadpool import ThreadPool


class Success:
    def __init__(self, value, result):
        self.value = value
        self.result = result


class Failure:
    def __init__(self, value, exc_info):
        self.value = value
        self.exc_info = exc_info


class Cancelled(Exception):
    pass


class FutureResult:

    def __init__(self, value=None, exc_info=None):
        self.value = value
        self.exc_info = exc_info


class Future:
    """
    A simplified future object. Can be set to some value (all further sets are ignored),
    can be waited on.
    """

    def __init__(self):
        self._lock = Lock()
        self._set_event = Event()
        self._value = None

    def _set(self, value):
        with self._lock:
            if not self._set_event.is_set():
                self._value = value
                self._set_event.set()

    def set(self, value):
        self._set(FutureResult(value=value))

    def set_exception(self):
        exc_info = sys.exc_info()
        self._set(FutureResult(exc_info=exc_info))

    def is_set(self):
        return self._set_event.is_set()

    def get(self):
        self._set_event.wait()

        if self._value.exc_info is not None:
            (exc_type, exc_value, exc_traceback) = self._value.exc_info
            if exc_value is None:
                exc_value = exc_type()
            if exc_value.__traceback__ is not exc_traceback:
                raise exc_value.with_traceback(exc_traceback)
            raise exc_value
        else:
            return self._value.value


class WorkerPool:
    """
    A generalized class that can start multiple workers in a thread pool with values
    drawn from the given value factory object,
    and wait for their completion and a given number of successes
    (a worker returning something without throwing an exception).
    """

    class TimedOut(Exception):
        "Raised if waiting for the target number of successes timed out."

    class OutOfValues(Exception):
        "Raised if the value factory is out of values, but the target number was not reached."

    def __init__(self,
                 worker: Callable[[Any], Any],
                 value_factory: Callable[[int], Optional[List[Any]]],
                 target_successes,
                 timeout: float,
                 stagger_timeout: float = 0,
                 threadpool_size: int = None):

        # TODO: make stagger_timeout a part of the value factory?

        self._worker = worker
        self._value_factory = value_factory
        self._timeout = timeout
        self._stagger_timeout = stagger_timeout
        self._target_successes = target_successes

        thread_pool_kwargs = {}
        if threadpool_size is not None:
            thread_pool_kwargs['minthreads'] = threadpool_size
            thread_pool_kwargs['maxthreads'] = threadpool_size
        self._threadpool = ThreadPool(**thread_pool_kwargs)

        # These three tasks must be run in separate threads
        # to avoid being blocked by workers in the thread pool.
        self._bail_on_timeout_thread = Thread(target=self._bail_on_timeout)
        self._produce_values_thread = Thread(target=self._produce_values)
        self._process_results_thread = Thread(target=self._process_results)

        self._successes = {}
        self._failures = {}
        self._started_tasks = 0
        self._finished_tasks = 0

        self._cancel_event = Event()
        self._result_queue = Queue()
        self._target_value = Future()
        self._producer_error = Future()
        self._results_lock = Lock()
        self._threadpool_stop_lock = Lock()
        self._threadpool_stopped = False

    def start(self):
        # TODO: check if already started?
        self._threadpool.start()
        self._produce_values_thread.start()
        self._process_results_thread.start()
        self._bail_on_timeout_thread.start()

    def cancel(self):
        """
        Cancels the tasks enqueued in the thread pool and stops the producer thread.
        """
        self._cancel_event.set()

    def _stop_threadpool(self):
        # This can be called from multiple threads
        # (`join()` itself can be called from multiple threads,
        # and we also attempt to stop the pool from the `_process_results()` thread).
        with self._threadpool_stop_lock:
            if not self._threadpool_stopped:
                self._threadpool.stop()
                self._threadpool_stopped = True

    def _check_for_producer_error(self):
        # Check for any unexpected exceptions in the producer thread
        if self._producer_error.is_set():
            # Will raise if Future was set with an exception
            self._producer_error.get()

    def join(self):
        """
        Waits for all the threads to finish.
        Can be called several times.
        """
        self._produce_values_thread.join()
        self._process_results_thread.join()
        self._bail_on_timeout_thread.join()

        # In most cases `_threadpool` will be stopped by the `_process_results()` thread.
        # But in case there's some unexpected bug in its code, we're making sure the pool is stopped
        # to avoid the whole process hanging.
        self._stop_threadpool()

        self._check_for_producer_error()

    def _sleep(self, timeout):
        """
        Sleeps for a given timeout, can be interrupted by a cancellation event.
        """
        if self._cancel_event.wait(timeout):
            raise Cancelled

    def block_until_target_successes(self) -> Dict:
        """
        Blocks until the target number of successes is reached.
        Returns a dictionary of values matched to results.
        Can be called several times.
        """
        self._check_for_producer_error()

        result = self._target_value.get()
        if result == TIMEOUT_TRIGGERED:
            raise self.TimedOut()
        elif result == PRODUCER_STOPPED:
            raise self.OutOfValues()
        return result

    def get_failures(self) -> Dict:
        """
        Get the current failures, as a dictionary of values to thrown exceptions.
        """
        with self._results_lock:
            return dict(self._failures)

    def get_successes(self) -> Dict:
        """
        Get the current successes, as a dictionary of values to worker return values.
        """
        with self._results_lock:
            return dict(self._successes)

    def _bail_on_timeout(self):
        """
        A service thread that cancels the pool on timeout.
        """
        if not self._cancel_event.wait(timeout=self._timeout):
            self._target_value.set(TIMEOUT_TRIGGERED)
        self._cancel_event.set()

    def _worker_wrapper(self, value):
        """
        A wrapper that catches exceptions thrown by the worker
        and sends the results to the processing thread.
        """
        try:
            # If we're in the cancelled state, interrupt early
            self._sleep(0)

            result = self._worker(value)
            self._result_queue.put(Success(value, result))
        except Cancelled as e:
            self._result_queue.put(e)
        except BaseException as e:
            self._result_queue.put(Failure(value, sys.exc_info()))

    def _process_results(self):
        """
        A service thread that processes worker results
        and waits for the target number of successes to be reached.
        """
        producer_stopped = False
        success_event_reached = False
        while True:
            result = self._result_queue.get()

            if result == PRODUCER_STOPPED:
                producer_stopped = True
            else:
                self._finished_tasks += 1
                if isinstance(result, Success):
                    with self._results_lock:
                        self._successes[result.value] = result.result
                        len_successes = len(self._successes)
                    if not success_event_reached and len_successes == self._target_successes:
                        # A protection for the case of repeating values.
                        # Only trigger the target value once.
                        success_event_reached = True
                        self._target_value.set(self.get_successes())
                if isinstance(result, Failure):
                    with self._results_lock:
                        self._failures[result.value] = result.exc_info

            if producer_stopped and self._finished_tasks == self._started_tasks:
                self.cancel() # to cancel the timeout thread
                self._target_value.set(PRODUCER_STOPPED)
                break

        self._stop_threadpool()

    def _produce_values(self):
        while True:
            try:
                with self._results_lock:
                    len_successes = len(self._successes)
                batch = self._value_factory(len_successes)
                if not batch:
                    break

                self._started_tasks += len(batch)
                for value in batch:
                    # There is a possible race between `callInThread()` and `stop()`,
                    # But we never execute them at the same time,
                    # because `join()` checks that the producer thread is stopped.
                    self._threadpool.callInThread(self._worker_wrapper, value)

                self._sleep(self._stagger_timeout)

            except Cancelled:
                break

            except BaseException:
                self._producer_error.set_exception()
                self.cancel()
                break

        self._result_queue.put(PRODUCER_STOPPED)


class AllAtOnceFactory:
    """
    A simple value factory that returns all its values in a single batch.
    """

    def __init__(self, values):
        self.values = values
        self._produced = False

    def __call__(self, _successes):
        if self._produced:
            return None
        else:
            self._produced = True
            return self.values
