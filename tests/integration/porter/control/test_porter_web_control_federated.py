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
from urllib.parse import urlencode
from base64 import b64encode

import pytest

from nucypher.crypto.powers import DecryptingPower
from nucypher.network.nodes import Learner
from nucypher.policy.maps import TreasureMap
from tests.utils.policy import work_order_setup


def test_get_ursulas(federated_porter_web_controller, federated_ursulas):
    # Send bad data to assert error return
    response = federated_porter_web_controller.get('/get_ursulas', data=json.dumps({'bad': 'input'}))
    assert response.status_code == 400

    quantity = 4
    duration = 2  # irrelevant for federated (but required)
    federated_ursulas_list = list(federated_ursulas)
    include_ursulas = [federated_ursulas_list[0].checksum_address, federated_ursulas_list[1].checksum_address]
    exclude_ursulas = [federated_ursulas_list[2].checksum_address, federated_ursulas_list[3].checksum_address]

    get_ursulas_params = {
        'quantity': quantity,
        'duration_periods': duration,  # irrelevant for federated (but required)
        'include_ursulas': include_ursulas,
        'exclude_ursulas': exclude_ursulas
    }

    #
    # Success
    #
    response = federated_porter_web_controller.get('/get_ursulas', data=json.dumps(get_ursulas_params))
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
    # Test Query parameters
    #
    response = federated_porter_web_controller.get(f'/get_ursulas?quantity={quantity}'
                                                   f'&duration_periods={duration}'
                                                   f'&include_ursulas={",".join(include_ursulas)}'
                                                   f'&exclude_ursulas={",".join(exclude_ursulas)}')
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
    failed_ursula_params['quantity'] = len(federated_ursulas_list) + 1  # too many to get
    with pytest.raises(Learner.NotEnoughNodes):
        federated_porter_web_controller.get('/get_ursulas', data=json.dumps(failed_ursula_params))


def test_publish_and_get_treasure_map(federated_porter_web_controller,
                                      federated_alice,
                                      federated_bob,
                                      enacted_federated_policy,
                                      random_federated_treasure_map_data):
    # Send bad data to assert error return
    response = federated_porter_web_controller.get('/get_treasure_map', data=json.dumps({'bad': 'input'}))
    assert response.status_code == 400

    response = federated_porter_web_controller.post('/publish_treasure_map', data=json.dumps({'bad': 'input'}))
    assert response.status_code == 400

    random_bob_encrypting_key, random_treasure_map_id, random_treasure_map = random_federated_treasure_map_data

    # ensure that random treasure map cannot be obtained since not available
    with pytest.raises(TreasureMap.NowhereToBeFound):
        get_treasure_map_params = {
            'treasure_map_id': random_treasure_map_id,
            'bob_encrypting_key': bytes(random_bob_encrypting_key).hex()
        }
        federated_porter_web_controller.get('/get_treasure_map', data=json.dumps(get_treasure_map_params))

    # publish the random treasure map
    publish_treasure_map_params = {
        'treasure_map': b64encode(bytes(random_treasure_map)).decode(),
        'bob_encrypting_key': bytes(random_bob_encrypting_key).hex()
    }
    response = federated_porter_web_controller.post('/publish_treasure_map',
                                                    data=json.dumps(publish_treasure_map_params))
    assert response.status_code == 200
    response_data = json.loads(response.data)
    assert response_data['result']['published']

    # try getting the random treasure map now
    get_treasure_map_params = {
        'treasure_map_id': random_treasure_map_id,
        'bob_encrypting_key': bytes(random_bob_encrypting_key).hex()
    }
    response = federated_porter_web_controller.get('/get_treasure_map',
                                                   data=json.dumps(get_treasure_map_params))
    assert response.status_code == 200
    response_data = json.loads(response.data)
    assert response_data['result']['treasure_map'] == b64encode(bytes(random_treasure_map)).decode()

    # try getting random treasure map using query parameters
    response = federated_porter_web_controller.get(f'/get_treasure_map'
                                                   f'?{urlencode(get_treasure_map_params)}')
    assert response.status_code == 200
    response_data = json.loads(response.data)
    assert response_data['result']['treasure_map'] == b64encode(bytes(random_treasure_map)).decode()

    # try getting an already existing policy
    map_id = federated_bob.construct_map_id(federated_alice.stamp,
                                            enacted_federated_policy.label)
    get_treasure_map_params = {
        'treasure_map_id': map_id,
        'bob_encrypting_key': bytes(federated_bob.public_keys(DecryptingPower)).hex()
    }
    response = federated_porter_web_controller.get('/get_treasure_map',
                                                   data=json.dumps(get_treasure_map_params))
    assert response.status_code == 200
    response_data = json.loads(response.data)
    assert response_data['result']['treasure_map'] == b64encode(bytes(enacted_federated_policy.treasure_map)).decode()


def test_exec_work_order(federated_porter_web_controller,
                         enacted_federated_policy,
                         federated_ursulas,
                         federated_bob,
                         federated_alice,
                         get_random_checksum_address):
    # Send bad data to assert error return
    response = federated_porter_web_controller.post('/exec_work_order', data=json.dumps({'bad': 'input'}))
    assert response.status_code == 400

    # Setup
    ursula_address, work_order = work_order_setup(enacted_federated_policy,
                                                  federated_ursulas,
                                                  federated_bob,
                                                  federated_alice)
    work_order_payload_b64 = b64encode(work_order.payload()).decode()

    # Success
    exec_work_order_params = {
        'ursula': ursula_address,
        'work_order_payload': work_order_payload_b64
    }
    response = federated_porter_web_controller.post('/exec_work_order', data=json.dumps(exec_work_order_params))
    assert response.status_code == 200

    response_data = json.loads(response.data)
    work_order_result = response_data['result']['work_order_result']
    assert work_order_result

    # Failure
    exec_work_order_params = {
        'ursula': get_random_checksum_address(),  # unknown ursula
        'work_order_payload': work_order_payload_b64
    }
    with pytest.raises(Learner.NotEnoughNodes):
        federated_porter_web_controller.post('/exec_work_order', data=json.dumps(exec_work_order_params))


def test_endpoints_basic_auth(federated_porter_basic_auth_web_controller,
                              random_federated_treasure_map_data,
                              get_random_checksum_address):
    # /get_ursulas
    quantity = 4
    duration = 2  # irrelevant for federated (but required)
    get_ursulas_params = {
        'quantity': quantity,
        'duration_periods': duration,  # irrelevant for federated (but required)
    }
    response = federated_porter_basic_auth_web_controller.get('/get_ursulas', data=json.dumps(get_ursulas_params))
    assert response.status_code == 401  # user unauthorized

    random_bob_encrypting_key, random_treasure_map_id, random_treasure_map = random_federated_treasure_map_data

    # /get_treasure_map
    get_treasure_map_params = {
        'treasure_map_id': random_treasure_map_id,
        'bob_encrypting_key': bytes(random_bob_encrypting_key).hex()
    }
    response = federated_porter_basic_auth_web_controller.get('/get_treasure_map',
                                                              data=json.dumps(get_treasure_map_params))
    assert response.status_code == 401  # user not authenticated

    # /publish_treasure_map
    publish_treasure_map_params = {
        'treasure_map': b64encode(bytes(random_treasure_map)).decode(),
        'bob_encrypting_key': bytes(random_bob_encrypting_key).hex()
    }
    response = federated_porter_basic_auth_web_controller.post('/publish_treasure_map',
                                                               data=json.dumps(publish_treasure_map_params))
    assert response.status_code == 401  # user not authenticated

    # /exec_work_order
    exec_work_order_params = {
        'ursula': get_random_checksum_address(),
        'work_order_payload': b64encode(b"some data").decode()
    }
    response = federated_porter_basic_auth_web_controller.post('/exec_work_order',
                                                               data=json.dumps(exec_work_order_params))
    assert response.status_code == 401  # user not authenticated

    # try get_ursulas with authentication
    credentials = b64encode(b"admin:admin").decode('utf-8')
    response = federated_porter_basic_auth_web_controller.get('/get_ursulas',
                                                              data=json.dumps(get_ursulas_params),
                                                              headers={"Authorization": f"Basic {credentials}"})
    assert response.status_code == 200  # success
