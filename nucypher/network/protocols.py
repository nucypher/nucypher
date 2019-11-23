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

    DEFAULT_INTERVAL = 5                  # Seconds
    DEFAULT_SAMPLE_SIZE = 3               # Ursulas
    DEFAULT_MEASUREMENT_SENSITIVITY = 2   # Failure indication threshold
    DEFAULT_SENSOR_SENSITIVITY = 0.5      # Successful records
    DEFAULT_RETENTION = 10                # Records
    MAXIMUM_ALONE_TIME = 10               # Seconds

    class Unreachable(RuntimeError):
        pass

    class Solitary(Unreachable):
        message = "Cannot connect to any teacher nodes."

    class Lonely(Unreachable):
        message = "Cannot connect to enough teacher nodes."

    Record = namedtuple('Record', ('time', 'result'))

    def __init__(self,
                 ursula,
                 interval: int = DEFAULT_INTERVAL,
                 sample_size: int = DEFAULT_SAMPLE_SIZE,
                 sensitivity: int = DEFAULT_MEASUREMENT_SENSITIVITY,
                 sensor_sensitivity: int = DEFAULT_SENSOR_SENSITIVITY,
                 retention: int = DEFAULT_RETENTION):

        self.log = Logger(self.__class__.__name__)
        self.interval = interval
        self.sample_size = sample_size
        self.measurement_sensitivity = sensitivity
        self.sensor_sensitivity = sensor_sensitivity
        self.retention = retention

        # 1.0 == Fully available
        self.warnings = {
            0.95: self.mild_warning,
            0.7: self.medium_warning,
            0.2: self.severe_warning,
            0: self.shutdown_everything
        }

        self._ursula = ursula
        self._sample_size = sample_size
        self._records = deque(maxlen=retention)

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
        return self.score > self.sensor_sensitivity

    @property
    def running(self) -> bool:
        return self.__task.running

    def start(self, now: bool = False):
        if not self.running:
            self.__start_time = maya.now().epoch
            d = self.__task.start(interval=self.interval, now=now)
            d.addErrback(self.handle_measurement_errors)

    def stop(self) -> None:
        if self.running:
            self.__task.stop()

    def maintain(self) -> None:
        self.log.debug(f"Starting new sensor maintenance round")
        known_nodes_is_smaller_than_sample_size = len(self._ursula.known_nodes) < self.sample_size
        if known_nodes_is_smaller_than_sample_size:
            # If there are no known nodes or too few known nodes, skip this round...
            # ... but not for longer than the maximum allotted alone time
            if not self._ursula.lonely:
                now = maya.now().epoch
                delta = now - self.__start_time
                if delta >= self.MAXIMUM_ALONE_TIME:
                    self.severe_warning()
                    reason = self.Solitary if not self._ursula.known_nodes else self.Lonely
                    self.shutdown_everything(reason=reason)
            return
        result = self.measure()
        self.record(result)

        if self._records:
            first, last = self._records[0], self._records[-1]
            delta = (last.time - first.time) // 60
            self.log.info(f"Current availability score is {self.score} measured over the last {delta} min.")
        self.issue_warnings()

    @property
    def successful_records(self):
        return (record.result for record in self._records if record.result)

    @property
    def score(self) -> float:
        if len(self._records) == 0:
            return 1.0  # Assume availability by default
        return len(tuple(self.successful_records)) / len(self._records)

    def issue_warnings(self) -> None:
        for threshold, action in self.warnings.items():
            if self.score <= threshold:
                action()
                break

    def sample(self, quantity: int) -> list:
        ursulas = random.sample(population=tuple(self._ursula.known_nodes._nodes.values()), k=quantity)
        return ursulas

    def record(self, result: bool) -> None:
        now = maya.now().epoch
        measurement = self.Record(time=now, result=result)
        self._records.append(measurement)

    def measure(self) -> bool:
        if self.measurement_sensitivity > self.sample_size:
            message = f"Threshold ({self.measurement_sensitivity}) cannot be greater then the sample size ({self.sample_size})."
            raise ValueError(message)
        ursulas = self.sample(quantity=self.sample_size)
        succeeded, failed = 0, 0
        for ursula in ursulas:
            # Fetch and store teacher certificate
            responding_ursula_address, responding_ursula_port = tuple(ursula.rest_interface)
            certificate = self._ursula.network_middleware.get_certificate(host=responding_ursula_address,
                                                                          port=responding_ursula_port)
            certificate_filepath = self._ursula.node_storage.store_node_certificate(certificate=certificate)
            available = self._ursula.network_middleware.check_rest_availability(requesting_ursula=self._ursula,
                                                                                responding_ursula=ursula,
                                                                                certificate_filepath=certificate_filepath)
            if available:
                succeeded += 1
            else:
                failed += 1
        return self.measurement_sensitivity >= failed
