import pytest_twisted as pt
import requests
from flask import Response
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
            ursula._availability_sensor.record(False, reason={'error': 'fake failure reason'})

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

        # to keep this test fast, were just checking for a single entry
        # (technically there will be 10, but resolution is one second.)
        assert len(sensor._AvailabilitySensor__excuses) > 0

    def raise_to_maximum():
        for i in range(150):
            ursula._availability_sensor.record(True)
        assert ursula._availability_sensor.score > 9.98

    # Run the Callbacks
    try:
        d = threads.deferToThread(measure)
        yield d
        d = threads.deferToThread(maintain)
        yield d
        d = threads.deferToThread(raise_to_maximum)
        yield d
    finally:
        if ursula._availability_sensor:
            ursula._availability_sensor.stop()
            ursula._availability_sensor = None


@pt.inlineCallbacks
def test_availability_sensor_integration(blockchain_ursulas, monkeypatch):

    # Start up self-services
    ursula = blockchain_ursulas.pop()
    start_pytest_ursula_services(ursula=ursula)

    ursula._availability_sensor = AvailabilitySensor(ursula=ursula)

    def maintain():
        sensor = ursula._availability_sensor

        def mock_public_information_endpoint(route, *args, **kwargs):
            if 'public_information' in route:
                ursula_were_looking_for = str(ursula.rest_interface.port) in route
                if ursula_were_looking_for:
                    return Response(status=400)  # Make this node unreachable
            else:
                response = Response(response=bytes(ursula), mimetype='application/octet-stream')
                return response

        # apply the monkeypatch for requests.get to mock_get
        monkeypatch.setattr(requests, "get", mock_public_information_endpoint)

        ursula._availability_sensor.start()
        sensor.measure()  # This makes a REST Call

        # to keep this test fast, were just checking for a single entry
        # (technically there will be 10, but resolution is one second.)
        assert len(sensor._AvailabilitySensor__excuses) > 0

    # Run the Callbacks
    try:
        d = threads.deferToThread(maintain)
        yield d
    finally:
        if ursula._availability_sensor:
            ursula._availability_sensor.stop()
            ursula._availability_sensor = None
