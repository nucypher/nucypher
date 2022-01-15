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
def alice_web_controller_test_client(blockchain_alice):
    web_controller = blockchain_alice.make_web_controller(crash_on_error=True)
    yield web_controller.test_client()


@pytest.fixture(scope='module')
def bob_web_controller_test_client(blockchain_bob):
    web_controller = blockchain_bob.make_web_controller(crash_on_error=True)
    yield web_controller.test_client()


@pytest.fixture(scope='module')
def enrico_web_controller_test_client(capsule_side_channel_blockchain):
    _message_kit = capsule_side_channel_blockchain()
    web_controller = capsule_side_channel_blockchain.enrico.make_web_controller(crash_on_error=True)
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
    _message_kit = capsule_side_channel_blockchain()

    # RPC Controler
    rpc_controller = capsule_side_channel_blockchain.enrico.make_rpc_controller(crash_on_error=True)
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
        'threshold': 2,
        'shares': 3,
        'expiration': (maya.now() + datetime.timedelta(days=35)).iso8601(),
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
        'threshold': 2,
        'shares': 3,
        'expiration': (maya.now() + datetime.timedelta(days=35)).iso8601(),
        'value': 3 * 3 * 10 ** 16
    }
    return method_name, params


@pytest.fixture(scope='function')
def retrieve_control_request(blockchain_alice, blockchain_bob, enacted_blockchain_policy, capsule_side_channel_blockchain):
    capsule_side_channel_blockchain.reset()
    method_name = 'retrieve_and_decrypt'
    message_kit = capsule_side_channel_blockchain()

    params = {
        'alice_verifying_key': bytes(enacted_blockchain_policy.publisher_verifying_key).hex(),
        'message_kits': [b64encode(bytes(message_kit)).decode()],
        'encrypted_treasure_map': b64encode(bytes(enacted_blockchain_policy.treasure_map)).decode()
    }
    return method_name, params


@pytest.fixture(scope='module')
def encrypt_control_request():
    method_name = 'encrypt_message'
    params = {
        'message': b64encode(b"The admiration I had for your work has completely evaporated!").decode(),
    }
    return method_name, params
