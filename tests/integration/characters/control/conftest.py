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

from base64 import b64encode

import datetime
import maya
import pytest

from nucypher.characters.lawful import Enrico
from nucypher.crypto.powers import DecryptingPower


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
    _message_kit = capsule_side_channel()
    web_controller = capsule_side_channel.enrico.make_web_controller(crash_on_error=True)
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
    _message_kit = capsule_side_channel()

    # RPC Controler
    rpc_controller = capsule_side_channel.enrico.make_rpc_controller(crash_on_error=True)
    yield rpc_controller.test_client()


@pytest.fixture(scope='module')
def enrico_rpc_controller_from_alice(federated_alice, random_policy_label):
    enrico = Enrico.from_alice(federated_alice, random_policy_label)
    rpc_controller = enrico.make_rpc_controller(crash_on_error=True)
    yield rpc_controller.test_client()


@pytest.fixture(scope='module')
def create_policy_control_request(federated_bob):
    method_name = 'create_policy'
    bob_pubkey_enc = federated_bob.public_keys(DecryptingPower)
    params = {
        'bob_encrypting_key': bytes(bob_pubkey_enc).hex(),
        'bob_verifying_key': bytes(federated_bob.stamp).hex(),
        'label': b64encode(bytes(b'test')).decode(),
        'm': 2,
        'n': 3,
        'expiration': (maya.now() + datetime.timedelta(days=3)).iso8601(),
    }
    return method_name, params


@pytest.fixture(scope='module')
def grant_control_request(federated_bob):
    method_name = 'grant'
    bob_pubkey_enc = federated_bob.public_keys(DecryptingPower)
    params = {
        'bob_encrypting_key': bytes(bob_pubkey_enc).hex(),
        'bob_verifying_key': bytes(federated_bob.stamp).hex(),
        'label': 'test',
        'm': 2,
        'n': 3,
        'expiration': (maya.now() + datetime.timedelta(days=3)).iso8601(),
    }
    return method_name, params


@pytest.fixture(scope='module')
def join_control_request(federated_bob, enacted_federated_policy):
    method_name = 'join_policy'

    params = {
        'label': enacted_federated_policy.label.decode(),
        'publisher_verifying_key': bytes(enacted_federated_policy.publisher_verifying_key).hex(),
    }
    return method_name, params


@pytest.fixture(scope='module')
def retrieve_control_request(federated_bob, enacted_federated_policy, capsule_side_channel):
    method_name = 'retrieve'
    message_kit = capsule_side_channel()

    params = {
        'label': enacted_federated_policy.label.decode(),
        'policy_encrypting_key': bytes(enacted_federated_policy.public_key).hex(),
        'alice_verifying_key': bytes(enacted_federated_policy.publisher_verifying_key).hex(),
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
