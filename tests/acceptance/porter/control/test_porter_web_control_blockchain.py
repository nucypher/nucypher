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

import json
from base64 import b64encode

import pytest
from umbral.keys import UmbralPublicKey

from nucypher.crypto.constants import HRAC_LENGTH
from nucypher.crypto.powers import DecryptingPower
from nucypher.network.nodes import Learner
from nucypher.policy.collections import TreasureMap
from tests.utils.middleware import MockRestMiddleware


def test_get_ursulas(blockchain_porter_web_controller, blockchain_ursulas):
    # Send bad data to assert error return
    response = blockchain_porter_web_controller.get('/get_ursulas', data=json.dumps({'bad': 'input'}))
    assert response.status_code == 400

    quantity = 4
    duration = 2
    blockchain_ursulas_list = list(blockchain_ursulas)
    include_ursulas = [blockchain_ursulas_list[0].checksum_address, blockchain_ursulas_list[1].checksum_address]
    exclude_ursulas = [blockchain_ursulas_list[2].checksum_address, blockchain_ursulas_list[3].checksum_address]

    get_ursulas_params = {
        'quantity': quantity,
        'duration_periods': duration,
        'include_ursulas': include_ursulas,
        'exclude_ursulas': exclude_ursulas
    }

    #
    # Success
    #
    response = blockchain_porter_web_controller.get('/get_ursulas', data=json.dumps(get_ursulas_params))
    assert response.status_code == 200

    response_data = json.loads(response.data)
    ursulas_info = response_data['result']['ursulas']
    returned_ursula_addresses = {ursula_info['checksum_address'] for ursula_info in ursulas_info}  # ensure no repeats
    assert len(returned_ursula_addresses) == quantity
    for address in include_ursulas:
        assert address in returned_ursula_addresses
    for address in exclude_ursulas:
        assert address not in returned_ursula_addresses

    #
    # Failure case
    #
    failed_ursula_params = dict(get_ursulas_params)
    failed_ursula_params['quantity'] = len(blockchain_ursulas_list) + 1  # too many to get
    with pytest.raises(Learner.NotEnoughNodes):
        blockchain_porter_web_controller.get('/get_ursulas', data=json.dumps(failed_ursula_params))


def test_publish_and_get_treasure_map(blockchain_porter_web_controller,
                                      blockchain_alice,
                                      blockchain_bob,
                                      idle_blockchain_policy):
    # Send bad data to assert error return
    response = blockchain_porter_web_controller.get('/get_treasure_map', data=json.dumps({'bad': 'input'}))
    assert response.status_code == 400

    response = blockchain_porter_web_controller.post('/publish_treasure_map', data=json.dumps({'bad': 'input'}))
    assert response.status_code == 400

    # ensure that random treasure map cannot be obtained since not available
    with pytest.raises(TreasureMap.NowhereToBeFound):
        random_bob_encrypting_key = UmbralPublicKey.from_bytes(
            bytes.fromhex("026d1f4ce5b2474e0dae499d6737a8d987ed3c9ab1a55e00f57ad2d8e81fe9e9ac"))
        random_treasure_map_id = "93a9482bdf3b4f2e9df906a35144ca84"
        assert len(bytes.fromhex(random_treasure_map_id)) == HRAC_LENGTH  # non-federated is 16 bytes
        get_treasure_map_params = {
            'treasure_map_id': random_treasure_map_id,
            'bob_encrypting_key': random_bob_encrypting_key.hex()
        }
        blockchain_porter_web_controller.get('/get_treasure_map',
                                             data=json.dumps(get_treasure_map_params))

    blockchain_bob_encrypting_key = blockchain_bob.public_keys(DecryptingPower)
    # try publishing a new policy
    network_middleware = MockRestMiddleware()
    enacted_policy = idle_blockchain_policy.enact(network_middleware=network_middleware,
                                                  publish_treasure_map=False)  # enact but don't publish
    treasure_map = enacted_policy.treasure_map
    publish_treasure_map_params = {
        'treasure_map': b64encode(bytes(treasure_map)).decode(),
        'bob_encrypting_key': blockchain_bob_encrypting_key.hex()
    }
    response = blockchain_porter_web_controller.post('/publish_treasure_map', data=json.dumps(publish_treasure_map_params))
    assert response.status_code == 200
    response_data = json.loads(response.data)
    assert response_data['result']['published']

    # try getting the recently published treasure map
    map_id = blockchain_bob.construct_map_id(blockchain_alice.stamp,
                                             enacted_policy.label)
    get_treasure_map_params = {
        'treasure_map_id': map_id,
        'bob_encrypting_key': blockchain_bob_encrypting_key.hex()
    }
    response = blockchain_porter_web_controller.get('/get_treasure_map',
                                                    data=json.dumps(get_treasure_map_params))
    assert response.status_code == 200
    response_data = json.loads(response.data)
    assert response_data['result']['treasure_map'] == b64encode(bytes(treasure_map)).decode()


def test_get_ursulas_basic_auth(blockchain_porter_basic_auth_web_controller):
    quantity = 4
    duration = 2
    get_ursulas_params = {
        'quantity': quantity,
        'duration_periods': duration,
    }

    response = blockchain_porter_basic_auth_web_controller.get('/get_ursulas', data=json.dumps(get_ursulas_params))
    assert response.status_code == 401  # user is unauthorized

    credentials = b64encode(b"admin:admin").decode('utf-8')
    response = blockchain_porter_basic_auth_web_controller.get('/get_ursulas',
                                                               data=json.dumps(get_ursulas_params),
                                                               headers={"Authorization": f"Basic {credentials}"})
    assert response.status_code == 200  # success - access allowed
    response_data = json.loads(response.data)
    ursulas_info = response_data['result']['ursulas']
    returned_ursula_addresses = {ursula_info['checksum_address'] for ursula_info in ursulas_info}  # ensure no repeats
    assert len(returned_ursula_addresses) == quantity
