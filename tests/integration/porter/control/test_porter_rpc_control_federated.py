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

from base64 import b64encode, b64decode

import pytest
from nucypher.crypto.umbral_adapter import PublicKey

from nucypher.crypto.powers import DecryptingPower
from nucypher.network.nodes import Learner
from nucypher.policy.maps import TreasureMap


# should always be first test due to checks on response id
from tests.utils.policy import work_order_setup


def test_get_ursulas(federated_porter_rpc_controller, federated_ursulas):
    method = 'get_ursulas'
    expected_response_id = 0

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
    request_data = {'method': method, 'params': get_ursulas_params}
    response = federated_porter_rpc_controller.send(request_data)
    expected_response_id += 1
    assert response.success
    assert response.id == expected_response_id
    ursulas_info = response.data['result']['ursulas']
    returned_ursula_addresses = {ursula_info['checksum_address'] for ursula_info in ursulas_info}  # ensure no repeats
    assert len(returned_ursula_addresses) == quantity
    for address in include_ursulas:
        assert address in returned_ursula_addresses
    for address in exclude_ursulas:
        assert address not in returned_ursula_addresses

    # Confirm the same message send works again, with a unique ID
    request_data = {'method': method, 'params': get_ursulas_params}
    rpc_response = federated_porter_rpc_controller.send(request=request_data)
    expected_response_id += 1
    assert rpc_response.success
    assert rpc_response.id == expected_response_id

    #
    # Failure case
    #
    failed_ursula_params = dict(get_ursulas_params)
    failed_ursula_params['quantity'] = len(federated_ursulas_list) + 1  # too many to get
    request_data = {'method': method, 'params': failed_ursula_params}
    with pytest.raises(Learner.NotEnoughNodes):
        federated_porter_rpc_controller.send(request_data)


def test_publish_and_get_treasure_map(federated_porter_rpc_controller,
                                      federated_alice,
                                      federated_bob,
                                      enacted_federated_policy,
                                      random_federated_treasure_map_data):
    random_bob_encrypting_key, random_treasure_map_id, random_treasure_map = random_federated_treasure_map_data

    # ensure that random treasure map cannot be obtained since not available
    with pytest.raises(TreasureMap.NowhereToBeFound):
        get_treasure_map_params = {
            'treasure_map_id': random_treasure_map_id,
            'bob_encrypting_key': bytes(random_bob_encrypting_key).hex()
        }
        request_data = {'method': 'get_treasure_map', 'params': get_treasure_map_params}
        federated_porter_rpc_controller.send(request_data)

    # publish the random treasure map
    publish_treasure_map_params = {
        'treasure_map': b64encode(bytes(random_treasure_map)).decode(),
        'bob_encrypting_key': bytes(random_bob_encrypting_key).hex()
    }
    request_data = {'method': 'publish_treasure_map', 'params': publish_treasure_map_params}
    response = federated_porter_rpc_controller.send(request_data)
    assert response.success

    # try getting the random treasure map now
    get_treasure_map_params = {
        'treasure_map_id': random_treasure_map_id,
        'bob_encrypting_key': bytes(random_bob_encrypting_key).hex()
    }
    request_data = {'method': 'get_treasure_map', 'params': get_treasure_map_params}
    response = federated_porter_rpc_controller.send(request_data)
    assert response.success
    assert response.content['treasure_map'] == b64encode(bytes(random_treasure_map)).decode()

    # try getting an already existing policy
    map_id = federated_bob.construct_map_id(federated_alice.stamp,
                                            enacted_federated_policy.label)
    get_treasure_map_params = {
        'treasure_map_id': map_id,
        'bob_encrypting_key': bytes(federated_bob.public_keys(DecryptingPower)).hex()
    }
    request_data = {'method': 'get_treasure_map', 'params': get_treasure_map_params}
    response = federated_porter_rpc_controller.send(request_data)
    assert response.success
    assert response.content['treasure_map'] == b64encode(bytes(enacted_federated_policy.treasure_map)).decode()


def test_exec_work_order(federated_porter_rpc_controller,
                         enacted_federated_policy,
                         federated_ursulas,
                         federated_bob,
                         federated_alice,
                         get_random_checksum_address):
    method = 'exec_work_order'
    # Setup
    ursula_address, work_order = work_order_setup(enacted_federated_policy,
                                                  federated_ursulas,
                                                  federated_bob,
                                                  federated_alice)

    work_order_payload_b64 = b64encode(work_order.payload()).decode()

    exec_work_order_params = {
        'ursula': ursula_address,
        'work_order_payload': work_order_payload_b64
    }
    request_data = {'method': method, 'params': exec_work_order_params}
    response = federated_porter_rpc_controller.send(request_data)
    assert response.success
    work_order_result = response.content['work_order_result']
    assert work_order_result

    # Failure
    exec_work_order_params = {
        'ursula': get_random_checksum_address(),  # unknown ursula
        'work_order_payload': work_order_payload_b64
    }
    with pytest.raises(Learner.NotEnoughNodes):
        request_data = {'method': method, 'params': exec_work_order_params}
        federated_porter_rpc_controller.send(request_data)
