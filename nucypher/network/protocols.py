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
import random
from collections import deque, namedtuple
from typing import Union
from urllib.parse import urlparse

import maya
from eth_utils import is_checksum_address

from bytestring_splitter import VariableLengthBytestring
from twisted.internet import reactor
from twisted.internet.task import LoopingCall
from twisted.logger import Logger


class SuspiciousActivity(RuntimeError):
    """raised when an action appears to amount to malicious conduct."""


def parse_node_uri(uri: str):
    from nucypher.config.characters import UrsulaConfiguration

    if '@' in uri:
        checksum_address, uri = uri.split("@")
        if checksum_address is None:
            raise ValueError(f"{uri} is not a valid Teacher URI - no checksum address.")
        if not is_checksum_address(checksum_address):
            raise ValueError("{} is not a valid checksum address.".format(checksum_address))
    else:
        checksum_address = None  # federated

    #############################################
    # Strange logic here to ensure https:// - possibly pursuant to https://bugs.python.org/msg179670
    # It's not clear that there is any version of python 3.7+ that requires this, so we may
    # be able to drop it in the near future.
    if not uri.startswith("https://"):
        uri = "https://" + uri
    #############################################

    parsed_uri = urlparse(uri)

    if not parsed_uri.scheme:
        try:
            parsed_uri = urlparse('https://'+uri)
        except Exception:
            raise  # TODO: Do we need even deeper handling/validation here?

    if not parsed_uri.scheme == "https":
        raise ValueError("Invalid teacher scheme or protocol. Is the hostname prefixed with 'https://' ?")

    hostname = parsed_uri.hostname
    port = parsed_uri.port or UrsulaConfiguration.DEFAULT_REST_PORT
    return hostname, port, checksum_address


class InterfaceInfo:
    expected_bytes_length = lambda: VariableLengthBytestring

    def __init__(self, host, port) -> None:
        loopback, localhost = '127.0.0.1', 'localhost'
        self.host = loopback if host == localhost else host
        self.port = int(port)

    def __iter__(self):
        yield self.host
        yield self.port

    @classmethod
    def from_bytes(cls, url_string):
        host_bytes, port_bytes = url_string.split(b':', 1)
        port = int.from_bytes(port_bytes, "big")
        host = host_bytes.decode("utf-8")
        return cls(host=host, port=port)

    @property
    def uri(self):
        return u"{}:{}".format(self.host, self.port)

    @property
    def formal_uri(self):
        return u"{}://{}".format('https', self.uri)

    def __bytes__(self):
        return bytes(self.host, encoding="utf-8") + b":" + self.port.to_bytes(4, "big")

    def __add__(self, other):
        return bytes(self) + bytes(other)

    def __radd__(self, other):
        return bytes(other) + bytes(self)

    def __repr__(self):
        return self.uri


class AvailabilitySensor:

    FAST_INTERVAL = 5          # Seconds
    SLOW_INTERVAL = 60 * 5
    SEEDING_DURATION = 60 * 2
    MAXIMUM_ALONE_TIME = 10

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

        self.__start_time = None
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

    @property
    def status(self) -> bool:
        """Returns current indication of availability"""
        return self.score > self.SENSOR_SENSITIVITY

    @property
    def running(self) -> bool:
        return self.__task.running

    def start(self, now: bool = False):
        if not self.running:
            self.__start_time = maya.now()
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
                delta = now - self.__start_time.epoch
                if delta >= self.MAXIMUM_ALONE_TIME:
                    self.severe_warning()
                    reason = self.Solitary if not self._ursula.known_nodes else self.Lonely
                    self.shutdown_everything(reason=reason)
            return

        if self.__task.interval == self.FAST_INTERVAL:
            now = maya.now().epoch
            delta = now - self.__start_time.epoch
            if delta >= self.SEEDING_DURATION:
                # Slow down
                self.__task.interval = self.SLOW_INTERVAL
                return

        # All systems go
        self.measure()
        delta = (maya.now() - self.__start_time).slang_time()
        self.log.info(f"Current availability score is {self.score} measured since {delta}")
        self.issue_warnings()

    def issue_warnings(self) -> None:
        for threshold, action in self.warnings.items():
            if self.score <= threshold:
                action()

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
        self.__score = self.__score + self.CHARGE_RATE * int(result)

    def measure(self) -> None:

        ursulas = self.sample(quantity=self.SAMPLE_SIZE)
        for ursula in ursulas:

            # Fetch and store teacher certificate
            responding_ursula_address, responding_ursula_port = tuple(ursula.rest_interface)
            certificate = self._ursula.network_middleware.get_certificate(host=responding_ursula_address,
                                                                          port=responding_ursula_port)
            certificate_filepath = self._ursula.node_storage.store_node_certificate(certificate=certificate)

            # Request status check
            response = self._ursula.network_middleware.check_rest_availability(requesting_ursula=self._ursula,
                                                                               responding_ursula=ursula,
                                                                               certificate_filepath=certificate_filepath)
            # Record response
            if response.status_code == 200:
                self.record(True)
            elif response.status_code == 400:
                self.record(False)
            else:
                # Ignore this measurement and move on.
                self.record(None)
            return
