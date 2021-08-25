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
import os
from base64 import b64encode

import pytest

from nucypher.control.specifications.exceptions import InvalidInputData
from nucypher.network.nodes import Learner
from tests.utils.middleware import MockRestMiddleware
from tests.utils.policy import retrieval_request_setup, retrieval_params_decode_from_rest


def test_get_ursulas(blockchain_porter_rpc_controller, blockchain_ursulas):
    method = 'get_ursulas'
    expected_response_id = 0

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
    request_data = {'method': method, 'params': get_ursulas_params}
    response = blockchain_porter_rpc_controller.send(request_data)
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
    rpc_response = blockchain_porter_rpc_controller.send(request=request_data)
    expected_response_id += 1
    assert rpc_response.success
    assert rpc_response.id == expected_response_id

    #
    # Failure case
    #
    failed_ursula_params = dict(get_ursulas_params)
    failed_ursula_params['quantity'] = len(blockchain_ursulas_list) + 1  # too many to get
    request_data = {'method': method, 'params': failed_ursula_params}
    with pytest.raises(Learner.NotEnoughNodes):
        blockchain_porter_rpc_controller.send(request_data)


def test_retrieve_cfrags(blockchain_porter,
                         blockchain_porter_rpc_controller,
                         random_blockchain_policy,
                         blockchain_bob,
                         blockchain_alice):
    method = 'retrieve_cfrags'

    # Setup
    network_middleware = MockRestMiddleware()
    # enact new random policy since idle_blockchain_policy/enacted_blockchain_policy already modified in previous tests
    enacted_policy = random_blockchain_policy.enact(network_middleware=network_middleware)
    retrieve_cfrags_params, _ = retrieval_request_setup(enacted_policy,
                                                        blockchain_bob,
                                                        blockchain_alice,
                                                        encode_for_rest=True)

    # Success
    request_data = {'method': method, 'params': retrieve_cfrags_params}
    response = blockchain_porter_rpc_controller.send(request_data)
    assert response.success

    retrieval_results = response.data['result']['retrieval_results']
    assert retrieval_results

    # expected results - can only compare length of results, ursulas are randomized to obtain cfrags
    retrieve_args = retrieval_params_decode_from_rest(retrieve_cfrags_params)
    expected_results = blockchain_porter.retrieve_cfrags(**retrieve_args)
    assert len(retrieval_results) == len(expected_results)

    # Failure - use encrypted treasure map
    failure_retrieve_cfrags_params = dict(retrieve_cfrags_params)
    failure_retrieve_cfrags_params['treasure_map'] = b64encode(os.urandom(32)).decode()
    request_data = {'method': method, 'params': failure_retrieve_cfrags_params}
    with pytest.raises(InvalidInputData):
        blockchain_porter_rpc_controller.send(request_data)
