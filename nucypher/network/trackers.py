import random
from typing import Union

import maya
from twisted.internet import reactor
from twisted.internet.defer import Deferred
from twisted.internet.task import LoopingCall
from twisted.logger import Logger

from nucypher.config.storages import NodeStorage
from nucypher.network.exceptions import NodeSeemsToBeDown
from nucypher.network.middleware import RestMiddleware
from nucypher.network.nodes import NodeSprout


class AvailabilityTracker:

    # Duration (seconds)
    FAST_INTERVAL = 2
    SLOW_INTERVAL = 5
    SEEDING_DURATION = 60
    MAXIMUM_ALONE_TIME = 120

    # Score
    MINIMUM_SCORE = 1.0
    MAXIMUM_SCORE = 10.0
    INITIAL_SCORE = MAXIMUM_SCORE

    # Sampling
    SAMPLE_SIZE = 1       # Ursulas
    SENSITIVITY = 0.5     # Threshold
    CHARGE_RATE = 0.9     # Measurement Multiplier

    NodeIsUnusable = (*NodeSeemsToBeDown,
                      NodeStorage.InvalidNodeCertificate,
                      RestMiddleware.UnexpectedResponse)

    class Unreachable(RuntimeError):
        pass

    class Solitary(Unreachable):
        """No peers are known."""
        message = "Cannot connect to any teacher nodes."

    class Lonely(Unreachable):
        """Insufficient peers are known."""
        message = "Cannot connect to enough teacher nodes."

    def __init__(self,
                 ursula: 'Ursula',
                 enforce_loneliness: bool = True,
                 crash_on_error: bool = False,
                 cascade_alerts: bool = False):

        self.log = Logger(self.__class__.__name__)
        self.enforce_loneliness = enforce_loneliness
        self.crash_on_error = crash_on_error
        self.cascade_alerts = cascade_alerts
        self.excuses = dict()       # Reasons for negative results

        # Bind alerts ot the instance for access to score
        self.alerts = {
            int(self.MAXIMUM_SCORE*0.8): self.mild_warning,    # For example 0.8 == 80% of max
            int(self.MAXIMUM_SCORE*0.5): self.medium_warning,
            int(self.MAXIMUM_SCORE*0.25): self.severe_warning,

            # uncomment to enable auto-shutdown; 0 is unobtainable.
            # int(self.MINIMUM_SCORE): self.shutdown_everything,
        }

        self.__ursula = ursula
        self.__score = self.INITIAL_SCORE
        self.__start_time = None
        self.__uptime_seconds = None
        self.__task = None            # loopingcall differed
        self.__responders = set()     # Responders that support the endpoint
        self.__responses = 0          # Total supportive endpoints
        self.__round = 0              # Attempt
        self.__active = None          # Track an actively occurring measurement

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
        self.__ursula.stop(halt_reactor=False)
        try:
            if failure:
                raise failure(failure.message)
            raise self.Unreachable(f'{self.__ursula} is unreachable (scored {self.score}).')
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
        """Returns the threshold indicating a boolean availability status"""
        threshold = (self.SENSITIVITY * self.MAXIMUM_SCORE)
        return threshold

    @property
    def responders(self) -> set:
        """A set of responding nodes checksum addresses, both positive and negative."""
        return self.__responders

    @property
    def responses(self) -> int:
        """Returns the number of responses from remote nodes."""
        return self.__responses

    @property
    def round(self) -> int:
        """Returns the number of times the measurement."""
        return self.__round

    @property
    def running(self) -> bool:
        """Return True if the availability service is currently running."""
        if not self.__task:
            return False
        return self.__task.running

    @property
    def active_measurement(self) -> bool:
        """Returns a boolean if there is a measurement currently in progress."""
        return self.__active

    @property
    def score(self) -> float:
        """Returns the current score."""
        return self.__score

    def status(self) -> bool:
        """Returns bool current indication of availability based on sensitivity."""
        result = self.score > self.__threshold
        return result

    def dump_excuses(self):
        self.log.info(f'Availability score {self.score} <= threshold ({self.__threshold}); logging current availability issues')
        for time, reason in self.excuses.items():
            self.log.info(f'Availability Issue: [{time}] - {reason["error"]}')
            del self.excuses[time]              # prune excuses once logged

    def __start(self, now=True) -> None:
        self.__task = LoopingCall(self.maintain)
        task = self.__task.start(interval=self.FAST_INTERVAL, now=now)
        task.addErrback(self.handle_measurement_errors)

    def start(self, now: bool = True, on_main_thread: bool = False) -> None:
        if not self.running:
            self.__start_time = maya.now()
            if on_main_thread:
                self.__start(now=now)
            else:
                reactor.callFromThread(self.__start, now=now)

    def stop(self) -> None:
        if self.running:
            self.__task.stop()

    def __is_socially_distant(self) -> bool:
        """
        If there are no known nodes or too few known nodes, skip this round...
        but not for longer than the maximum allotted alone time.
        """
        known_nodes = len(self.__ursula.known_nodes)
        known_nodes_is_smaller_than_sample_size = known_nodes < self.SAMPLE_SIZE
        seeding_is_complete = self.__uptime_seconds >= self.MAXIMUM_ALONE_TIME
        ursula_wants_to_be_social = not self.__ursula.lonely
        ursula_is_socially_distant = all((seeding_is_complete,
                                          known_nodes_is_smaller_than_sample_size,
                                          ursula_wants_to_be_social,
                                          self.enforce_loneliness))

        return ursula_is_socially_distant

    def maintain(self) -> None:

        # Update tracking
        self.__round += 1
        now = maya.now().epoch
        self.__uptime_seconds = now - self.__start_time.epoch

        # Enforce configured social behaviour
        if self.__is_socially_distant():
            self.severe_warning()
            reason_why = self.Solitary if not self.__ursula.known_nodes else self.Lonely
            self.shutdown_everything(failure=reason_why)
            return  # Abort

        # Toggle interval speed
        if self.__task.interval == self.FAST_INTERVAL:
            if self.__uptime_seconds >= self.SEEDING_DURATION:
                self.__task.interval = self.SLOW_INTERVAL  # Slow down next round, but continue

        # Enforce only a single (threaded) measurement at a time to avoid spawning
        # more threads than needed to collect availability data from other nodes.
        if self.__active:
            return
        self.__active = True

        # Perform the self-check
        try:
            self.measure_sample()  # blocking network-bound call
        finally:
            self.__active = False  # allow another measurement to occur (unblock)

        # Log the result
        pretty_uptime = maya.now() - self.__start_time
        self.log.info(f"Current availability score is {self.score} measured since {pretty_uptime}")
        self.issue_alerts(cascade=self.cascade_alerts)

    def issue_alerts(self, cascade: bool = False) -> None:
        warnings = sorted(self.alerts.items(), key=lambda t: t[0], reverse=True)
        for threshold, action in warnings:
            if self.score >= threshold:
                action()
                if not cascade:
                    # Exit after the first active warning is issued
                    return

    def sample(self, quantity: int) -> set:
        """Select remote nodes to use as availability check responders."""
        known_nodes = self.__ursula.known_nodes._nodes
        ursula_addresses = random.sample(population=set(known_nodes), k=quantity)
        ursulas = {known_nodes[addr] for addr in ursula_addresses}
        return ursulas

    def record(self, result: bool = None, reason: dict = None) -> None:
        """Update the score with a new result"""

        # Score
        score = int(result) + self.CHARGE_RATE * self.__score
        if score >= self.MAXIMUM_SCORE:
            self.__score = self.MAXIMUM_SCORE
        elif score <= self.MINIMUM_SCORE:
            self.__score = self.MINIMUM_SCORE
        else:
            self.__score = score

        # Record, Rhyme & Reason
        if reason:
            self.excuses[maya.now().epoch] = reason
        if result:
            self.log.debug(f"Availability score increased to {self.score}.")
        else:
            if reason:
                self.log.info(f"Availability score decreased to {self.score}. Reason: {reason.values()}")
                return
            self.log.info(f"Availability score decreased to {self.score}.")  # ... for no reason at all

    def measure_sample(self, ursulas: list = None) -> None:
        """
        Measure self-availability from a sample of Ursulas or automatically from known nodes.
        Handle the possibility of unreachable or invalid remote nodes in the sample.
        """
        if not ursulas:
            ursulas = self.sample(quantity=self.SAMPLE_SIZE)
        for ursula_or_sprout in ursulas:
            try:
                self.measure(ursula_or_sprout=ursula_or_sprout)
            except (*AvailabilityTracker.NodeIsUnusable, self.__ursula.NotStaking) as e:  # TODO: BSS #26
                # This node is either not an Ursula, not available, or is not staking...
                # ...do nothing and move on without changing the score.
                cleaned_error = str(e).replace('{', '').replace('}', '')
                self.log.debug(f"{ursula_or_sprout} responded to availability check with {cleaned_error}")
                continue
            except self.__ursula.network_middleware.NotFound:
                # This Ursula either opted out ir does not support serving availability trackers.
                self.log.debug(f"{ursula_or_sprout} responded with 404 to 'ping' endpoint and does not support availability checks")
                continue

    def measure(self, ursula_or_sprout: Union['Ursula', NodeSprout]) -> None:
        """Measure self-availability from a single remote node that participates availability checks."""
        try:
            response = self.__ursula.network_middleware.check_rest_availability(initiator=self.__ursula, responder=ursula_or_sprout)
        except RestMiddleware.BadRequest as e:
            self.__responders.add(ursula_or_sprout.checksum_address)
            self.record(False, reason={'result': f"{ursula_or_sprout.checksum_address} cannot reach this node; Reason: {e.reason}."})
        else:
            if response.status_code == 200:
                self.__responders.add(ursula_or_sprout.checksum_address)
                self.record(True)
            self.log.debug(f"{ursula_or_sprout.checksum_address} returned {response.status_code} from 'ping' endpoint.")
