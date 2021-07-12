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
from base64 import b64decode

import pytest
from nucypher.crypto.powers import DecryptingPower
from nucypher.crypto.umbral_adapter import PublicKey
from nucypher.policy.maps import TreasureMap
from tests.utils.policy import work_order_setup


def test_get_ursulas(federated_porter, federated_ursulas):
    # simple
    quantity = 4
    ursulas_info = federated_porter.get_ursulas(quantity=quantity)
    returned_ursula_addresses = {ursula_info.checksum_address for ursula_info in ursulas_info}
    assert len(returned_ursula_addresses) == quantity  # ensure no repeats

    federated_ursulas_list = list(federated_ursulas)

    # include specific ursulas
    include_ursulas = [federated_ursulas_list[0].checksum_address, federated_ursulas_list[1].checksum_address]
    ursulas_info = federated_porter.get_ursulas(quantity=quantity,
                                                include_ursulas=include_ursulas)
    returned_ursula_addresses = {ursula_info.checksum_address for ursula_info in ursulas_info}
    assert len(returned_ursula_addresses) == quantity
    for address in include_ursulas:
        assert address in returned_ursula_addresses

    # exclude specific ursulas
    number_to_exclude = len(federated_ursulas_list) - 4
    exclude_ursulas = []
    for i in range(number_to_exclude):
        exclude_ursulas.append(federated_ursulas_list[i].checksum_address)
    ursulas_info = federated_porter.get_ursulas(quantity=quantity,
                                                exclude_ursulas=exclude_ursulas)
    returned_ursula_addresses = {ursula_info.checksum_address for ursula_info in ursulas_info}
    assert len(returned_ursula_addresses) == quantity
    for address in exclude_ursulas:
        assert address not in returned_ursula_addresses

    # include and exclude
    include_ursulas = [federated_ursulas_list[0].checksum_address, federated_ursulas_list[1].checksum_address]
    exclude_ursulas = [federated_ursulas_list[2].checksum_address, federated_ursulas_list[3].checksum_address]
    ursulas_info = federated_porter.get_ursulas(quantity=quantity,
                                                include_ursulas=include_ursulas,
                                                exclude_ursulas=exclude_ursulas)
    returned_ursula_addresses = {ursula_info.checksum_address for ursula_info in ursulas_info}
    assert len(returned_ursula_addresses) == quantity
    for address in include_ursulas:
        assert address in returned_ursula_addresses
    for address in exclude_ursulas:
        assert address not in returned_ursula_addresses


def test_publish_and_get_treasure_map(federated_porter,
                                      federated_alice,
                                      federated_bob,
                                      enacted_federated_policy,
                                      random_federated_treasure_map_data):
    random_bob_encrypting_key, random_treasure_map_id, random_treasure_map = random_federated_treasure_map_data

    # ensure that random treasure map cannot be obtained since not available
    with pytest.raises(TreasureMap.NowhereToBeFound):
        federated_porter.get_treasure_map(map_identifier=random_treasure_map_id,
                                          bob_encrypting_key=random_bob_encrypting_key)

    # publish the random treasure map
    federated_porter.publish_treasure_map(treasure_map_bytes=random_treasure_map,
                                          bob_encrypting_key=random_bob_encrypting_key)

    # try getting the random treasure map now
    treasure_map = federated_porter.get_treasure_map(map_identifier=random_treasure_map_id,
                                                     bob_encrypting_key=random_bob_encrypting_key)
    assert treasure_map.public_id() == random_treasure_map_id

    # try getting an already existing policy
    map_id = federated_bob.construct_map_id(federated_alice.stamp,
                                            enacted_federated_policy.label)
    treasure_map = federated_porter.get_treasure_map(map_identifier=map_id,
                                                     bob_encrypting_key=federated_bob.public_keys(DecryptingPower))
    assert treasure_map == enacted_federated_policy.treasure_map


def test_exec_work_order(federated_porter,
                         federated_ursulas,
                         federated_bob,
                         federated_alice,
                         enacted_federated_policy):
    # Setup
    ursula_address, work_order = work_order_setup(enacted_federated_policy,
                                                  federated_ursulas,
                                                  federated_bob,
                                                  federated_alice)

    result = federated_porter.exec_work_order(ursula_address=ursula_address,
                                              work_order_payload=work_order.payload())
    assert result, "valid result returned"
