import maya
import pytest_twisted as pt
from twisted.internet import threads

from nucypher.network.sensors import AvailabilitySensor
from nucypher.utilities.sandbox.ursula import start_pytest_ursula_services


@pt.inlineCallbacks
def test_availability_sensor_success(blockchain_ursulas):

    # Start up self-services
    ursula = blockchain_ursulas.pop()
    start_pytest_ursula_services(ursula=ursula)

    ursula._availability_sensor = AvailabilitySensor(ursula=ursula)

    def measure():
        ursula._availability_sensor.start()
        assert ursula._availability_sensor.score == 10
        ursula._availability_sensor.record(False)
        assert ursula._availability_sensor.score == 9.0
        for i in range(7):
            ursula._availability_sensor.record(True)
        assert ursula._availability_sensor.score > 9.5

    def maintain():
        sensor = ursula._availability_sensor
        sensor.maintain()

        # The node goes offline for some time...
        for _ in range(10):
            ursula._availability_sensor.record(False)

        assert sensor.score < 4

        original_issuer = AvailabilitySensor.issue_warnings
        warnings = dict()
        def issue_warnings(sensor, *args, **kwargs):
            result = original_issuer(sensor, *args, **kwargs)
            warnings[sensor.score] = result
        AvailabilitySensor.issue_warnings = issue_warnings
        sensor.maintain()
        assert warnings
        AvailabilitySensor.issue_warnings = original_issuer

    # Run the Callbacks
    try:
        d = threads.deferToThread(measure)
        yield d
        d = threads.deferToThread(maintain)
        yield d
    finally:
        if ursula._availability_sensor:
            ursula._availability_sensor.stop()
            ursula._availability_sensor = None
