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
from base64 import b64decode, b64encode

import pytest
from umbral.keys import UmbralPublicKey

from nucypher.crypto.powers import DecryptingPower
from nucypher.network.nodes import Learner
from nucypher.policy.collections import TreasureMap


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
    # Failure case
    #
    failed_ursula_params = dict(get_ursulas_params)
    failed_ursula_params['quantity'] = len(federated_ursulas_list) + 1  # too many to get
    with pytest.raises(Learner.NotEnoughNodes):
        federated_porter_web_controller.get('/get_ursulas', data=json.dumps(failed_ursula_params))


def test_publish_and_get_treasure_map(federated_porter_web_controller,
                                      federated_alice,
                                      federated_bob,
                                      enacted_federated_policy):
    # Send bad data to assert error return
    response = federated_porter_web_controller.get('/get_treasure_map', data=json.dumps({'bad': 'input'}))
    assert response.status_code == 400

    response = federated_porter_web_controller.post('/publish_treasure_map', data=json.dumps({'bad': 'input'}))
    assert response.status_code == 400

    random_bob_encrypting_key = UmbralPublicKey.from_bytes(
        bytes.fromhex("026d1f4ce5b2474e0dae499d6737a8d987ed3c9ab1a55e00f57ad2d8e81fe9e9ac"))
    random_treasure_map_id = "f6ec73c93084ce91d5542a4ba6070071f5565112fe19b26ae9c960f9d658903a"  # federated is 32 bytes
    random_treasure_map = b64decode("Qld7S8sbKFCv2B8KxfJo4oxiTOjZ4VPyqTK5K1xK6DND6TbLg2hvlGaMV69aiiC5QfadB82w/5q1"
                                    "Sw+SNFHN2esWgAbs38QuUVUGCzDoWzQAAAGIAuhw12ZiPMNV8LaeWV8uUN+au2HGOjWilqtKsaP9f"
                                    "mnLAzFiTUAu9/VCxOLOQE88BPoWk1H7OxRLDEhnBVYyflpifKbOYItwLLTtWYVFRY90LtNSAzS8d3v"
                                    "NH4c3SHSZwYsCKY+5LvJ68GD0CqhydSxCcGckh0unttHrYGSOQsURUI4AAAEBsSMlukjA1WyYA+Fouq"
                                    "kuRtk8bVHcYLqRUkK2n6dShEUGMuY1SzcAbBINvJYmQp+hhzK5m47AzCl463emXepYZQC/evytktG7y"
                                    "Xxd3k8Ak+Qr7T4+G2VgJl4YrafTpIT6wowd+8u/SMSrrf/M41OhtLeBC4uDKjO3rYBQfVLTpEAgiX/9"
                                    "jxB80RtNMeCwgcieviAR5tlw2IlxVTEhxXbFeopcOZmfEuhVWqgBUfIakqsNCXkkubV0XS2l5G1vtTM8"
                                    "oNML0rP8PyKd4+0M5N6P/EQqFkHH93LCDD0IQBq9usm3MoJp0eT8N3m5gprI05drDh2xe/W6qnQfw3YXn"
                                    "jdvf2A=")

    # ensure that random treasure map cannot be obtained since not available
    with pytest.raises(TreasureMap.NowhereToBeFound):
        get_treasure_map_params = {
            'treasure_map_id': random_treasure_map_id,
            'bob_encrypting_key': random_bob_encrypting_key.hex()
        }
        federated_porter_web_controller.get('/get_treasure_map', data=json.dumps(get_treasure_map_params))

    # publish the random treasure map
    publish_treasure_map_params = {
        'treasure_map': b64encode(bytes(random_treasure_map)).decode(),
        'bob_encrypting_key': random_bob_encrypting_key.hex()
    }
    response = federated_porter_web_controller.post('/publish_treasure_map',
                                                    data=json.dumps(publish_treasure_map_params))
    assert response.status_code == 200

    # try getting the random treasure map now
    get_treasure_map_params = {
        'treasure_map_id': random_treasure_map_id,
        'bob_encrypting_key': random_bob_encrypting_key.hex()
    }
    response = federated_porter_web_controller.get('/get_treasure_map',
                                                   data=json.dumps(get_treasure_map_params))
    assert response.status_code == 200
    response_data = json.loads(response.data)
    assert response_data['result']['treasure_map'] == b64encode(bytes(random_treasure_map)).decode()

    # try getting an already existing policy
    map_id = federated_bob.construct_map_id(federated_alice.stamp,
                                            enacted_federated_policy.label)
    get_treasure_map_params = {
        'treasure_map_id': map_id,
        'bob_encrypting_key': federated_bob.public_keys(DecryptingPower).hex()
    }
    response = federated_porter_web_controller.get('/get_treasure_map',
                                                   data=json.dumps(get_treasure_map_params))
    assert response.status_code == 200
    response_data = json.loads(response.data)
    assert response_data['result']['treasure_map'] == b64encode(bytes(enacted_federated_policy.treasure_map)).decode()
