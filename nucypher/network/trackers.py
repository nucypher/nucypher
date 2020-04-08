import random
from typing import Union

import maya
from twisted.internet import reactor, threads
from twisted.internet.defer import Deferred
from twisted.internet.task import LoopingCall
from twisted.logger import Logger

from nucypher.network.exceptions import NodeSeemsToBeDown
from nucypher.network.middleware import RestMiddleware
from nucypher.network.nodes import NodeSprout


class AvailabilityTracker:

    FAST_INTERVAL = 15    # Seconds
    SLOW_INTERVAL = 60 * 2
    SEEDING_DURATION = 60
    MAXIMUM_ALONE_TIME = 120

    MAXIMUM_SCORE = 10.0  # Score
    SAMPLE_SIZE = 1       # Ursulas
    SENSITIVITY = 0.5     # Threshold
    CHARGE_RATE = 0.9     # Measurement Multiplier

    class Unreachable(RuntimeError):
        pass

    class Solitary(Unreachable):
        message = "Cannot connect to any teacher nodes."

    class Lonely(Unreachable):
        message = "Cannot connect to enough teacher nodes."

    def __init__(self, ursula, enforce_loneliness: bool = True, crash_on_error: bool = False):

        self.log = Logger(self.__class__.__name__)
        self._ursula = ursula
        self.enforce_loneliness = enforce_loneliness
        self.crash_on_error = crash_on_error

        self.__excuses = dict()  # List of failure reasons
        self.__score = 10
        # 10 == Perfect Score
        self.warnings = {
            9: self.mild_warning,
            7: self.medium_warning,
            2: self.severe_warning,
            # 1: self.shutdown_everything  # uncomment to enable auto-shutdown; 0 is unobtainable.
        }

        self._start_time = None
        self.__task = None
        self.responders = set()  # track responders that support the endpoint
        self.__responses = 0     # track all responses
        self.__round = 0         # track the looping round itself
        self.__active = None     # track tracking

    @property
    def excuses(self):
        return self.__excuses

    def mild_warning(self) -> None:
        self.log.info(f'[UNREACHABLE NOTICE (SCORE {self.score})] This node was recently reported as unreachable.')

    def medium_warning(self) -> None:
        self.log.warn(f'[UNREACHABLE CAUTION (SCORE {self.score})] This node is reporting as unreachable.'
                      f'Please check your network and firewall configuration.')

    def severe_warning(self) -> None:
        self.log.warn(f'[UNREACHABLE WARNING (SCORE {self.score})] '
                      f'Please check your network and firewall configuration.'
                      f'Auto-shutdown will commence soon if the services do not become available.')

    def shutdown_everything(self, failure=None, halt_reactor=False):
        self.log.warn(f'[NODE IS UNREACHABLE (SCORE {self.score})] Commencing auto-shutdown sequence...')
        self._ursula.stop(halt_reactor=False)
        try:
            if failure:
                raise failure(failure.message)
            raise self.Unreachable(f'{self._ursula} is unreachable (scored {self.score}).')
        finally:
            if halt_reactor:
                self._halt_reactor()

    @staticmethod
    def _halt_reactor() -> None:
        if reactor.running:
            reactor.stop()

    def handle_measurement_errors(self, *args, **kwargs) -> None:
        failure = args[0]
        cleaned_traceback = failure.getTraceback().replace('{', '').replace('}', '')  # FIXME: Amazing.
        self.log.warn("Unhandled error during availability check: {}".format(cleaned_traceback))
        if self.crash_on_error:
            failure.raiseException()

        # Restart on failure
        if not self.running:
            self.log.debug(f"Availability check crashed, restarting...")
            self.start(now=True)

    @property
    def __threshold(self) -> float:
        threshold = (self.SENSITIVITY * self.MAXIMUM_SCORE)
        return threshold

    def status(self) -> bool:
        """Returns bool current indication of availability based on sensitivity"""
        result = self.score > self.__threshold
        return result

    def describe(self):
        self.log.info(f'Availability score {self.score} <= threshold ({self.__threshold}); logging current availability issues')
        for time, reason in self.__excuses.items():
            self.log.info(f'Availability Issue: [{time}] - {reason["error"]}')
            # prune excuses once logged
            del self.__excuses[time]

    @property
    def running(self) -> bool:
        if not self.__task:
            return False
        return self.__task.running

    def __start(self, now=True):
        self.__task = LoopingCall(self.maintain)
        task = self.__task.start(interval=self.FAST_INTERVAL, now=now)
        task.addErrback(self.handle_measurement_errors)

    def start(self, now: bool = True, on_main_thread: bool = False) -> Union[None, Deferred]:
        if not self.running:
            self._start_time = maya.now()
            if on_main_thread:
                self.__start(now=now)
            else:
                reactor.callFromThread(self.__start, now=now)

    def stop(self) -> None:
        if self.running:
            self.__task.stop()

    def maintain(self) -> None:

        self.__round += 1

        # one at a time
        if self.__active:
            return
        else:
            self.__active = True

        known_nodes_is_smaller_than_sample_size = len(self._ursula.known_nodes) < self.SAMPLE_SIZE

        # If there are no known nodes or too few known nodes, skip this round...
        # ... but not for longer than the maximum allotted alone time
        if known_nodes_is_smaller_than_sample_size:
            if not self._ursula.lonely and self.enforce_loneliness:
                now = maya.now().epoch
                uptime = now - self._start_time.epoch
                if uptime >= self.MAXIMUM_ALONE_TIME:
                    self.severe_warning()
                    reason = self.Solitary if not self._ursula.known_nodes else self.Lonely
                    self.shutdown_everything(failure=reason)
            return

        if self.__task.interval == self.FAST_INTERVAL:
            now = maya.now().epoch
            uptime = now - self._start_time.epoch
            if uptime >= self.SEEDING_DURATION:
                self.__task.interval = self.SLOW_INTERVAL  # Slow down

        try:
            self.__responses += 1
            self.measure_sample()
        finally:
            self.__active = False

        uptime = maya.now() - self._start_time
        self.log.info(f"Current availability score is {self.score} measured since {uptime}")
        self.issue_warnings()

    def issue_warnings(self, cascade: bool = True) -> None:
        warnings = sorted(self.warnings.items(), key=lambda t: t[0])
        for threshold, action in warnings:
            if self.score <= threshold:
                action()
                if not cascade:
                    # Exit after the first active warning is issued
                    return

    def sample(self, quantity: int) -> list:
        population = tuple(self._ursula.known_nodes._nodes.values())
        ursulas = random.sample(population=population, k=quantity)
        return ursulas

    @property
    def score(self) -> float:
        return self.__score

    def record(self, result: bool = None, reason: dict = None) -> None:
        """Score the result and cache it."""
        if reason:
            self.__excuses[maya.now().epoch] = reason

        score = int(result) + self.CHARGE_RATE * self.__score
        if score >= self.MAXIMUM_SCORE:
            self.__score = self.MAXIMUM_SCORE
        else:
            self.__score = score

        if not result and reason:
            self.log.info(f"Availability check failed; availability score decreased: {reason.values()}")
        self.log.debug(f"Recorded new availability score ({self.score})")

    def measure_sample(self, ursulas: list = None) -> None:
        """
        Measure self-availability from a sample of Ursulas or automatically from known nodes.
        Handle the possibility of unreachable or invalid remote nodes in the sample.
        """

        # TODO: Relocate?
        Unreachable = (*NodeSeemsToBeDown,
                       self._ursula.NotStaking,
                       self._ursula.node_storage.InvalidNodeCertificate,
                       self._ursula.network_middleware.UnexpectedResponse,
                       self._ursula.network_middleware.NotFound)

        if not ursulas:
            ursulas = self.sample(quantity=self.SAMPLE_SIZE)

        for ursula_or_sprout in ursulas:
            try:
                self.measure(ursula_or_sprout=ursula_or_sprout)
            except Unreachable as e:
                # This node is either not an Ursula, not available, does not support availability checks, or is not staking...
                # ...do nothing and move on without changing the score.
                self.log.debug(f"{ursula_or_sprout} responded to availability check with {str(e).replace('{', '').replace('}', '')}")
                continue

    def measure(self, ursula_or_sprout: Union['Ursula', NodeSprout]) -> None:
        """Measure self-availability from a single remote node that participates availability checks."""
        try:
            response = self._ursula.network_middleware.check_rest_availability(initiator=self._ursula, responder=ursula_or_sprout)

        except RestMiddleware.BadRequest as e:
            self.responders.add(ursula_or_sprout.checksum_address)
            self.record(False, reason={'result': f"{ursula_or_sprout.checksum_address} cannot reach this node; Reason: {e.reason}."})

        else:
            if response.status_code == 200:
                self.responders.add(ursula_or_sprout.checksum_address)
                self.record(True)
            self.log.debug(f"{ursula_or_sprout.checksum_address} returned {response.status_code} from 'ping' endpoint.")
