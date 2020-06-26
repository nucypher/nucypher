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

import pytest

from nucypher.characters.control.interfaces import BobInterface, EnricoInterface
from nucypher.crypto.powers import DecryptingPower, SigningPower
from nucypher.policy.collections import DecentralizedTreasureMap
from tests.acceptance.characters.control.test_rpc_control_blockchain import validate_json_rpc_response_data


def test_bob_rpc_character_control_join_policy(bob_rpc_controller, join_control_request, enacted_blockchain_policy):
    # Simulate passing in a teacher-uri
    enacted_blockchain_policy.bob.remember_node(list(enacted_blockchain_policy.accepted_ursulas)[0])

    method_name, params = join_control_request
    request_data = {'method': method_name, 'params': params}
    response = bob_rpc_controller.send(request_data)
    assert validate_json_rpc_response_data(response=response,
                                           method_name=method_name,
                                           interface=BobInterface)


def test_enrico_rpc_character_control_encrypt_message(enrico_rpc_controller_test_client, encrypt_control_request):
    method_name, params = encrypt_control_request
    request_data = {'method': method_name, 'params': params}
    response = enrico_rpc_controller_test_client.send(request_data)
    assert validate_json_rpc_response_data(response=response,
                                           method_name=method_name,
                                           interface=EnricoInterface)


def test_bob_rpc_character_control_retrieve(bob_rpc_controller, retrieve_control_request):
    method_name, params = retrieve_control_request
    request_data = {'method': method_name, 'params': params}
    response = bob_rpc_controller.send(request_data)
    assert validate_json_rpc_response_data(response=response,
                                           method_name=method_name,
                                           interface=BobInterface)


def test_bob_rpc_character_control_retrieve_with_tmap(
        enacted_blockchain_policy, blockchain_bob, blockchain_alice,
        bob_rpc_controller, retrieve_control_request):
    tmap_64 = b64encode(bytes(enacted_blockchain_policy.treasure_map)).decode()
    method_name, params = retrieve_control_request
    params['treasure_map'] = tmap_64
    request_data = {'method': method_name, 'params': params}
    response = bob_rpc_controller.send(request_data)
    assert response.data['result']['cleartexts'][0] == 'Welcome to flippering number 1.'

    # Make a wrong (empty) treasure map

    wrong_tmap = DecentralizedTreasureMap(m=0)
    wrong_tmap.prepare_for_publication(
        blockchain_bob.public_keys(DecryptingPower),
        blockchain_bob.public_keys(SigningPower),
        blockchain_alice.stamp,
        b'Wrong!')
    wrong_tmap._blockchain_signature = b"this is not a signature, but we don't need one for this test....."  # ...because it only matters when Ursula looks at it.
    tmap_bytes = bytes(wrong_tmap)
    tmap_64 = b64encode(tmap_bytes).decode()
    request_data['params']['treasure_map'] = tmap_64
    with pytest.raises(DecentralizedTreasureMap.IsDisorienting):
        bob_rpc_controller.send(request_data)
