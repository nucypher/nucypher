import maya
import pytest_twisted as pt
from twisted.internet import threads

from nucypher.network.protocols import AvailabilitySensor
from nucypher.utilities.sandbox.ursula import start_pytest_ursula_services


@pt.inlineCallbacks
def test_availability_sensor_success(blockchain_ursulas):

    # Start up self-services
    ursula = blockchain_ursulas.pop()
    start_pytest_ursula_services(ursula=ursula)

    def measure():
        assert ursula._availability_sensor.measure()

    def maintain():
        sensor = ursula._availability_sensor
        assert len(sensor._records) == 0
        sensor.maintain()
        assert len(sensor._records) == 1
        assert sensor._records[0].result is True

        # The node goes offline for some time...
        for _ in range(7):
            fake_failed_record = sensor.Record(time=maya.now().epoch, result=False)
            sensor._records.append(fake_failed_record)

        assert sensor.retention == 10
        assert len(sensor._records) == 8
        assert sensor.score == 0.7

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
    d = threads.deferToThread(measure)
    yield d
    d = threads.deferToThread(maintain)
    yield d
