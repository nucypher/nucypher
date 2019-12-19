import random

import maya
from twisted.internet import reactor
from twisted.internet.task import LoopingCall
from twisted.logger import Logger

from nucypher.network import middleware
from nucypher.network.exceptions import NodeSeemsToBeDown


class AvailabilitySensor:

    FAST_INTERVAL = 5          # Seconds
    SLOW_INTERVAL = 60 * 5
    SEEDING_DURATION = 60 * 2
    MAXIMUM_ALONE_TIME = 10

    MAXIMUM_SCORE = 10.0       # Score
    SAMPLE_SIZE = 1            # Ursulas
    SENSOR_SENSITIVITY = 0.5   # Threshold
    CHARGE_RATE = 0.9          # Measurement Multiplier

    class Unreachable(RuntimeError):
        pass

    class Solitary(Unreachable):
        message = "Cannot connect to any teacher nodes."

    class Lonely(Unreachable):
        message = "Cannot connect to enough teacher nodes."

    def __init__(self, ursula, enforce_loneliness: bool = True):

        self.log = Logger(self.__class__.__name__)
        self._ursula = ursula
        self.enforce_loneliness = enforce_loneliness

        self.__score = 10
        # 10 == Fully available
        self.warnings = {
            9: self.mild_warning,
            7: self.medium_warning,
            2: self.severe_warning,
            0: self.shutdown_everything
        }

        self._start_time = None
        self.__task = LoopingCall(self.maintain)

    def mild_warning(self) -> None:
        self.log.info(f'[UNREACHABLE NOTICE] {self._ursula.rest_url} was recently reported as unreachable.')

    def medium_warning(self) -> None:
        self.log.warn(f'[UNREACHABLE CAUTION] {self._ursula.rest_url} is reporting as unreachable.'
                      f'Please check your network and firewall configuration.')

    def severe_warning(self) -> None:
        self.log.warn(f'[UNREACHABLE WARNING] '
                      f'Please check your network and firewall configuration.'
                      f'Auto-shutdown will commence soon if the services do not become available.')

    def shutdown_everything(self, reason = None):
        try:
            if reason:
                raise reason(reason.message)
            raise self.Unreachable(f'{self._ursula} is unreachable.')
        finally:
            if reactor.running:
                reactor.stop()

    def handle_measurement_errors(self, *args, **kwargs) -> None:
        failure = args[0]
        cleaned_traceback = failure.getTraceback().replace('{', '').replace('}', '')  # FIXME: Amazing.
        self.log.warn("Unhandled error during availability check: {}".format(cleaned_traceback))
        failure.raiseException()

    def status(self) -> bool:
        """Returns current indication of availability"""
        return self.score > self.SENSOR_SENSITIVITY

    @property
    def running(self) -> bool:
        return self.__task.running

    def start(self, now: bool = False):
        if not self.running:
            self._start_time = maya.now()
            d = self.__task.start(interval=self.FAST_INTERVAL, now=now)
            d.addErrback(self.handle_measurement_errors)

    def stop(self) -> None:
        if self.running:
            self.__task.stop()

    def maintain(self) -> None:
        self.log.debug(f"Starting new sensor maintenance round")
        known_nodes_is_smaller_than_sample_size = len(self._ursula.known_nodes) < self.SAMPLE_SIZE

        # If there are no known nodes or too few known nodes, skip this round...
        # ... but not for longer than the maximum allotted alone time
        if known_nodes_is_smaller_than_sample_size:
            if not self._ursula.lonely and self.enforce_loneliness:
                now = maya.now().epoch
                delta = now - self._start_time.epoch
                if delta >= self.MAXIMUM_ALONE_TIME:
                    self.severe_warning()
                    reason = self.Solitary if not self._ursula.known_nodes else self.Lonely
                    self.shutdown_everything(reason=reason)
            return

        if self.__task.interval == self.FAST_INTERVAL:
            now = maya.now().epoch
            delta = now - self._start_time.epoch
            if delta >= self.SEEDING_DURATION:
                # Slow down
                self.__task.interval = self.SLOW_INTERVAL
                return

        # All systems go
        self.measure()
        delta = maya.now() - self._start_time
        self.log.info(f"Current availability score is {self.score} measured since {delta}")
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

    def record(self, result: bool = None) -> None:
        """Score the result and cache it."""
        if result is None:
            return
        score = int(result) + self.CHARGE_RATE * self.__score
        if score >= self.MAXIMUM_SCORE:
            return
        else:
            self.__score = score

    def measure(self) -> None:

        ursulas = self.sample(quantity=self.SAMPLE_SIZE)
        for ursula in ursulas:

            # Fetch and store teacher certificate
            responding_ursula_address, responding_ursula_port = tuple(ursula.rest_interface)
            certificate = self._ursula.network_middleware.get_certificate(host=responding_ursula_address,
                                                                          port=responding_ursula_port)
            certificate_filepath = self._ursula.node_storage.store_node_certificate(certificate=certificate)

            # Request status check
            try:
                response = self._ursula.network_middleware.check_rest_availability(requesting_ursula=self._ursula,
                                                                                   responding_ursula=ursula,
                                                                                   certificate_filepath=certificate_filepath)
            except (*NodeSeemsToBeDown,
                    middleware.NotFound,
                    self._ursula.NotStaking):
                # This node is not available, does not support uptime checks, or is not staking - do nothing.
                continue

            # Record response
            if response.status_code == 200:
                self.record(True)
            elif response.status_code == 400:
                self.record(False)
            else:
                # Ignore this measurement and move on.
                self.record(None)