import pytest

from nucypher.characters.control.controllers import JSONRPCController, AliceJSONController, BobJSONController, \
    EnricoJSONController
from nucypher.characters.lawful import Enrico


#
# HTTP
#

@pytest.fixture(scope='module')
def alice_web_controller_test_client(federated_alice):
    web_controller = federated_alice.make_web_controller(crash_on_error=True)
    yield web_controller.test_client()


@pytest.fixture(scope='module')
def bob_web_controller_test_client(federated_bob):
    web_controller = federated_bob.make_web_controller(crash_on_error=True)
    yield web_controller.test_client()


@pytest.fixture(scope='module')
def enrico_web_controller_test_client(capsule_side_channel):
    _, data_source = capsule_side_channel
    message_kit, enrico = capsule_side_channel
    web_controller = enrico.make_web_controller(crash_on_error=True)
    yield web_controller.test_client()


@pytest.fixture(scope='module')
def enrico_web_controller_from_alice(federated_alice, random_policy_label):
    enrico = Enrico.from_alice(federated_alice, random_policy_label)
    web_controller = enrico.make_web_controller(crash_on_error=True)
    yield web_controller.test_client()


#
# RPC
#

@pytest.fixture(scope='module')
def alice_rpc_test_client(federated_alice):
    rpc_controller = federated_alice.make_rpc_controller(crash_on_error=True)
    yield rpc_controller.test_client()


@pytest.fixture(scope='module')
def bob_rpc_controller(federated_bob):
    rpc_controller = federated_bob.make_rpc_controller(crash_on_error=True)
    yield rpc_controller.test_client()


@pytest.fixture(scope='module')
def enrico_rpc_controller_test_client(capsule_side_channel):

    # Side Channel
    _, data_source = capsule_side_channel
    _message_kit, enrico = capsule_side_channel

    # RPC Controler
    rpc_controller = enrico.make_rpc_controller(crash_on_error=True)
    yield rpc_controller.test_client()


@pytest.fixture(scope='module')
def enrico_rpc_controller_from_alice(federated_alice, random_policy_label):
    enrico = Enrico.from_alice(federated_alice, random_policy_label)
    rpc_controller = enrico.make_rpc_controller(crash_on_error=True)
    yield rpc_controller.test_client()
