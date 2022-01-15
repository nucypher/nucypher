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

from nucypher.control.specifications.exceptions import InvalidInputData
from nucypher.network.nodes import Learner
from tests.utils.policy import retrieval_request_setup, retrieval_params_decode_from_rest


def test_get_ursulas(federated_porter_rpc_controller, federated_ursulas):
    method = 'get_ursulas'

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
    expected_response_id = response.id
    assert response.success
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


def test_retrieve_cfrags(federated_porter,
                         federated_porter_rpc_controller,
                         enacted_federated_policy,
                         federated_bob,
                         federated_alice,
                         random_federated_treasure_map_data):
    method = 'retrieve_cfrags'

    # Setup
    retrieve_cfrags_params, _ = retrieval_request_setup(enacted_federated_policy,
                                                        federated_bob,
                                                        federated_alice,
                                                        encode_for_rest=True)

    # Success
    request_data = {'method': method, 'params': retrieve_cfrags_params}
    response = federated_porter_rpc_controller.send(request_data)
    assert response.success

    retrieval_results = response.data['result']['retrieval_results']
    assert retrieval_results

    # expected results - can only compare length of results, ursulas are randomized to obtain cfrags
    retrieve_args = retrieval_params_decode_from_rest(retrieve_cfrags_params)
    expected_results = federated_porter.retrieve_cfrags(**retrieve_args)
    assert len(retrieval_results) == len(expected_results)

    # Failure - use encrypted treasure map
    failure_retrieve_cfrags_params = dict(retrieve_cfrags_params)
    _, random_treasure_map = random_federated_treasure_map_data
    failure_retrieve_cfrags_params['treasure_map'] = b64encode(bytes(random_treasure_map)).decode()
    request_data = {'method': method, 'params': failure_retrieve_cfrags_params}
    with pytest.raises(InvalidInputData):
        federated_porter_rpc_controller.send(request_data)
