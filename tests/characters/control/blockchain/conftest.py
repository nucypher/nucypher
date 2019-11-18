import datetime
from base64 import b64encode

import maya
import pytest

from nucypher.characters.lawful import Enrico
from nucypher.crypto.powers import DecryptingPower


@pytest.fixture(scope='module')
def alice_web_controller_test_client(blockchain_alice):
    web_controller = blockchain_alice.make_web_controller(crash_on_error=True)
    yield web_controller.test_client()


@pytest.fixture(scope='module')
def bob_web_controller_test_client(blockchain_bob):
    web_controller = blockchain_bob.make_web_controller(crash_on_error=True)
    yield web_controller.test_client()


@pytest.fixture(scope='module')
def enrico_web_controller_test_client(capsule_side_channel_blockchain):
    _message_kit, enrico = capsule_side_channel_blockchain()
    web_controller = enrico.make_web_controller(crash_on_error=True)
    yield web_controller.test_client()


@pytest.fixture(scope='module')
def enrico_web_controller_from_alice(blockchain_alice, random_policy_label):
    enrico = Enrico.from_alice(blockchain_alice, random_policy_label)
    web_controller = enrico.make_web_controller(crash_on_error=True)
    yield web_controller.test_client()


#
# RPC
#

@pytest.fixture(scope='module')
def alice_rpc_test_client(blockchain_alice):
    rpc_controller = blockchain_alice.make_rpc_controller(crash_on_error=True)
    yield rpc_controller.test_client()


@pytest.fixture(scope='module')
def bob_rpc_controller(blockchain_bob):
    rpc_controller = blockchain_bob.make_rpc_controller(crash_on_error=True)
    yield rpc_controller.test_client()


@pytest.fixture(scope='module')
def enrico_rpc_controller_test_client(capsule_side_channel_blockchain):

    # Side Channel
    _message_kit, enrico = capsule_side_channel_blockchain()

    # RPC Controler
    rpc_controller = enrico.make_rpc_controller(crash_on_error=True)
    yield rpc_controller.test_client()


@pytest.fixture(scope='module')
def enrico_rpc_controller_from_alice(blockchain_alice, random_policy_label):
    enrico = Enrico.from_alice(blockchain_alice, random_policy_label)
    rpc_controller = enrico.make_rpc_controller(crash_on_error=True)
    yield rpc_controller.test_client()


@pytest.fixture(scope='module')
def create_policy_control_request(blockchain_bob):
    method_name = 'create_policy'
    bob_pubkey_enc = blockchain_bob.public_keys(DecryptingPower)
    params = {
        'bob_encrypting_key': bytes(bob_pubkey_enc).hex(),
        'bob_verifying_key': bytes(blockchain_bob.stamp).hex(),
        'label': b64encode(bytes(b'test')).decode(),
        'm': 2,
        'n': 3,
        'expiration': (maya.now() + datetime.timedelta(days=3)).iso8601(),
        'value': 3 * 3 * 10 ** 16
    }
    return method_name, params


@pytest.fixture(scope='module')
def grant_control_request(blockchain_bob):
    method_name = 'grant'
    bob_pubkey_enc = blockchain_bob.public_keys(DecryptingPower)
    params = {
        'bob_encrypting_key': bytes(bob_pubkey_enc).hex(),
        'bob_verifying_key': bytes(blockchain_bob.stamp).hex(),
        'label': 'test',
        'm': 2,
        'n': 3,
        'expiration': (maya.now() + datetime.timedelta(days=3)).iso8601(),
        'value': 3 * 3 * 10 ** 16
    }
    return method_name, params


@pytest.fixture(scope='module')
def join_control_request(blockchain_bob, enacted_blockchain_policy):
    method_name = 'join_policy'

    params = {
        'label': enacted_blockchain_policy.label.decode(),
        'alice_verifying_key': bytes(enacted_blockchain_policy.alice.stamp).hex(),
    }
    return method_name, params


@pytest.fixture(scope='module')
def retrieve_control_request(blockchain_bob, enacted_blockchain_policy, capsule_side_channel_blockchain):
    method_name = 'retrieve'
    message_kit, data_source = capsule_side_channel_blockchain()

    params = {
        'label': enacted_blockchain_policy.label.decode(),
        'policy_encrypting_key': bytes(enacted_blockchain_policy.public_key).hex(),
        'alice_verifying_key': bytes(enacted_blockchain_policy.alice.stamp).hex(),
        'message_kit': b64encode(message_kit.to_bytes()).decode(),
    }
    return method_name, params


@pytest.fixture(scope='module')
def encrypt_control_request():
    method_name = 'encrypt_message'
    params = {
        'message': b64encode(b"The admiration I had for your work has completely evaporated!").decode(),
    }
    return method_name, params
