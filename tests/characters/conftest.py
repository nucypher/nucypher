import pytest

from nucypher.characters.lawful import Enrico

#
# Character Control Flask Test Clients
#

@pytest.fixture(scope='module')
def alice_control_test_client(federated_alice):
    web_controller = federated_alice.make_web_controller(crash_on_error=True)
    yield web_controller._web_app.test_client()


@pytest.fixture(scope='module')
def bob_control_test_client(federated_bob):
    web_controller = federated_bob.make_web_controller(crash_on_error=True)
    yield web_controller._web_app.test_client()


@pytest.fixture(scope='module')
def enrico_control_test_client(capsule_side_channel):
    message_kit, enrico = capsule_side_channel()
    web_controller = enrico.make_web_controller(crash_on_error=True)
    yield web_controller._web_app.test_client()


@pytest.fixture(scope='module')
def enrico_control_from_alice(federated_alice, random_policy_label):
    enrico = Enrico.from_alice(federated_alice, random_policy_label)
    web_controller = enrico.make_web_controller(crash_on_error=True)
    yield web_controller._web_app.test_client()
