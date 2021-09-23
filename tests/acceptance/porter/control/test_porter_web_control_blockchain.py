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
import os
from base64 import b64encode
from urllib.parse import urlencode

from nucypher.core import RetrievalKit

from nucypher.characters.lawful import Enrico
from nucypher.crypto.powers import DecryptingPower
from nucypher.policy.kits import PolicyMessageKit, RetrievalResult
from nucypher.utilities.porter.control.specifications.fields import RetrievalResultSchema, RetrievalKit as RetrievalKitField
from tests.utils.middleware import MockRestMiddleware
from tests.utils.policy import retrieval_request_setup, retrieval_params_decode_from_rest


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
    # Test Query parameters
    #
    response = blockchain_porter_web_controller.get(f'/get_ursulas?quantity={quantity}'
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
    failed_ursula_params['quantity'] = len(blockchain_ursulas_list) + 1  # too many to get
    response = blockchain_porter_web_controller.get('/get_ursulas', data=json.dumps(failed_ursula_params))
    assert response.status_code == 500


def test_retrieve_cfrags(blockchain_porter,
                         blockchain_porter_web_controller,
                         random_blockchain_policy,
                         blockchain_bob,
                         blockchain_alice):
    # Send bad data to assert error return
    response = blockchain_porter_web_controller.post('/retrieve_cfrags', data=json.dumps({'bad': 'input'}))
    assert response.status_code == 400

    # Setup
    network_middleware = MockRestMiddleware()
    # enact new random policy since idle_blockchain_policy/enacted_blockchain_policy already modified in previous tests
    enacted_policy = random_blockchain_policy.enact(network_middleware=network_middleware)

    original_message = b"Those who say it can't be done are usually interrupted by others doing it."  # - James Baldwin
    retrieve_cfrags_params, message_kit = retrieval_request_setup(enacted_policy,
                                                                  blockchain_bob,
                                                                  blockchain_alice,
                                                                  original_message=original_message,
                                                                  encode_for_rest=True)

    #
    # Success
    #
    response = blockchain_porter_web_controller.post('/retrieve_cfrags', data=json.dumps(retrieve_cfrags_params))
    assert response.status_code == 200

    response_data = json.loads(response.data)
    retrieval_results = response_data['result']['retrieval_results']
    assert retrieval_results

    # expected results - can only compare length of results, ursulas are randomized to obtain cfrags
    retrieve_args = retrieval_params_decode_from_rest(retrieve_cfrags_params)
    expected_results = blockchain_porter.retrieve_cfrags(**retrieve_args)
    assert len(retrieval_results) == len(expected_results)

    # check that the re-encryption performed was valid
    treasure_map = retrieve_args['treasure_map']
    policy_message_kit = PolicyMessageKit.from_message_kit(message_kit=message_kit,
                                                           policy_key=enacted_policy.public_key,
                                                           threshold=treasure_map.threshold)
    assert len(retrieval_results) == 1
    field = RetrievalResultSchema()
    cfrags = field.load(retrieval_results[0])['cfrags']
    verified_cfrags = {}
    for ursula, cfrag in cfrags.items():
        # need to obtain verified cfrags (verified cfrags are not deserializable, only non-verified cfrags)
        verified_cfrag = cfrag.verify(capsule=policy_message_kit.message_kit.capsule,
                                      verifying_pk=blockchain_alice.stamp.as_umbral_pubkey(),
                                      delegating_pk=enacted_policy.public_key,
                                      receiving_pk=blockchain_bob.public_keys(DecryptingPower))
        verified_cfrags[ursula] = verified_cfrag
    retrieval_result_object = RetrievalResult(cfrags=verified_cfrags)
    policy_message_kit = policy_message_kit.with_result(retrieval_result_object)

    assert policy_message_kit.is_decryptable_by_receiver()

    cleartext = blockchain_bob._crypto_power.power_ups(DecryptingPower).keypair.decrypt(policy_message_kit)
    assert cleartext == original_message

    #
    # Try using multiple retrieval kits
    #
    multiple_retrieval_kits_params = dict(retrieve_cfrags_params)
    enrico = Enrico(policy_encrypting_key=enacted_policy.public_key)
    retrieval_kit_1 = RetrievalKit.from_message_kit(enrico.encrypt_message(b"Those who say it can't be done"))
    retrieval_kit_2 = RetrievalKit.from_message_kit(enrico.encrypt_message(b"are usually interrupted by others doing it."))
    retrieval_kit_field = RetrievalKitField()
    # use multiple retrieval kits and serialize for json
    multiple_retrieval_kits_params['retrieval_kits'] = [
        retrieval_kit_field._serialize(value=retrieval_kit_1, attr=None, obj=None),
        retrieval_kit_field._serialize(value=retrieval_kit_2, attr=None, obj=None)
    ]
    response = blockchain_porter_web_controller.post('/retrieve_cfrags', data=json.dumps(multiple_retrieval_kits_params))
    assert response.status_code == 200

    response_data = json.loads(response.data)
    retrieval_results = response_data['result']['retrieval_results']
    assert retrieval_results
    assert len(retrieval_results) == 2

    #
    # Try same retrieval (with multiple retrieval kits) using query parameters
    #
    url_retrieve_params = dict(multiple_retrieval_kits_params)  # use multiple kit params from above
    # adjust parameter for url query parameter list format
    url_retrieve_params['retrieval_kits'] = ",".join(url_retrieve_params['retrieval_kits'])   # adjust for list
    response = blockchain_porter_web_controller.post(f'/retrieve_cfrags'
                                                     f'?{urlencode(url_retrieve_params)}')
    assert response.status_code == 200
    response_data = json.loads(response.data)
    retrieval_results = response_data['result']['retrieval_results']
    assert retrieval_results
    assert len(retrieval_results) == 2

    #
    # Failure
    #
    failure_retrieve_cfrags_params = dict(retrieve_cfrags_params)
    # use invalid treasure map bytes
    failure_retrieve_cfrags_params['treasure_map'] = b64encode(os.urandom(32)).decode()
    response = blockchain_porter_web_controller.post('/retrieve_cfrags', data=json.dumps(failure_retrieve_cfrags_params))
    assert response.status_code == 400  # invalid treasure map provided


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
