from nucypher.utilities.sandbox.ursula import start_pytest_ursula_services
import pytest_twisted as pt
from twisted.internet import threads


@pt.inlineCallbacks
def test_availability_sensor(blockchain_ursulas):

    # Start up self-services
    ursula = blockchain_ursulas.pop()
    start_pytest_ursula_services(ursula=ursula)

    def measure():
        ursula._availability_sensor.measure()
        assert True

    # Run the Callbacks
    d = threads.deferToThread(measure)
    yield d
