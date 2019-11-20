from nucypher.utilities.sandbox.ursula import start_pytest_ursula_services
import pytest_twisted as pt
from twisted.internet import threads


@pt.inlineCallbacks
def test_availability_sensor(blockchain_ursulas):
    ursula = blockchain_ursulas.pop()

    def start_local_services():
        start_pytest_ursula_services(ursula=ursula)

    def measure(result):
        ursula._availability_sensor.measure()
        assert True

    def more(result):
        assert True

    # Run the Callbacks
    d = threads.deferToThread(start_local_services)
    d.addCallback(measure)
    d.addCallback(more)

    yield d
