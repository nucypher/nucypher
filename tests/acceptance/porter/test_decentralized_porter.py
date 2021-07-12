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

import pytest
from nucypher.crypto.umbral_adapter import PublicKey

from nucypher.crypto.constants import HRAC_LENGTH
from nucypher.crypto.powers import DecryptingPower
from nucypher.policy.maps import TreasureMap
from tests.utils.middleware import MockRestMiddleware
from tests.utils.policy import work_order_setup


def test_get_ursulas(blockchain_porter, blockchain_ursulas):
    # simple
    quantity = 4
    duration = 2
    ursulas_info = blockchain_porter.get_ursulas(quantity=quantity, duration_periods=duration)
    returned_ursula_addresses = {ursula_info.checksum_address for ursula_info in ursulas_info}
    assert len(returned_ursula_addresses) == quantity  # ensure no repeats

    blockchain_ursulas_list = list(blockchain_ursulas)

    # include specific ursulas
    include_ursulas = [blockchain_ursulas_list[0].checksum_address, blockchain_ursulas_list[1].checksum_address]
    ursulas_info = blockchain_porter.get_ursulas(quantity=quantity,
                                                 duration_periods=duration,
                                                 include_ursulas=include_ursulas)
    returned_ursula_addresses = {ursula_info.checksum_address for ursula_info in ursulas_info}
    assert len(returned_ursula_addresses) == quantity
    for address in include_ursulas:
        assert address in returned_ursula_addresses

    # exclude specific ursulas
    number_to_exclude = len(blockchain_ursulas_list) - 4
    exclude_ursulas = []
    for i in range(number_to_exclude):
        exclude_ursulas.append(blockchain_ursulas_list[i].checksum_address)
    ursulas_info = blockchain_porter.get_ursulas(quantity=quantity,
                                                 duration_periods=duration,
                                                 exclude_ursulas=exclude_ursulas)
    returned_ursula_addresses = {ursula_info.checksum_address for ursula_info in ursulas_info}
    assert len(returned_ursula_addresses) == quantity
    for address in exclude_ursulas:
        assert address not in returned_ursula_addresses

    # include and exclude
    include_ursulas = [blockchain_ursulas_list[0].checksum_address, blockchain_ursulas_list[1].checksum_address]
    exclude_ursulas = [blockchain_ursulas_list[2].checksum_address, blockchain_ursulas_list[3].checksum_address]
    ursulas_info = blockchain_porter.get_ursulas(quantity=quantity,
                                                 duration_periods=duration,
                                                 include_ursulas=include_ursulas,
                                                 exclude_ursulas=exclude_ursulas)
    returned_ursula_addresses = {ursula_info.checksum_address for ursula_info in ursulas_info}
    assert len(returned_ursula_addresses) == quantity
    for address in include_ursulas:
        assert address in returned_ursula_addresses
    for address in exclude_ursulas:
        assert address not in returned_ursula_addresses


def test_publish_and_get_treasure_map(blockchain_porter,
                                      blockchain_alice,
                                      blockchain_bob,
                                      idle_blockchain_policy):
    # ensure that random treasure map cannot be obtained since not available
    with pytest.raises(TreasureMap.NowhereToBeFound):
        random_bob_encrypting_key = PublicKey.from_bytes(
            bytes.fromhex("026d1f4ce5b2474e0dae499d6737a8d987ed3c9ab1a55e00f57ad2d8e81fe9e9ac"))
        random_treasure_map_id = "93a9482bdf3b4f2e9df906a35144ca84"
        assert len(bytes.fromhex(random_treasure_map_id)) == HRAC_LENGTH  # non-federated is 16 bytes
        blockchain_porter.get_treasure_map(map_identifier=random_treasure_map_id,
                                           bob_encrypting_key=random_bob_encrypting_key)

    blockchain_bob_encrypting_key = blockchain_bob.public_keys(DecryptingPower)

    # try publishing a new policy
    network_middleware = MockRestMiddleware()
    enacted_policy = idle_blockchain_policy.enact(network_middleware=network_middleware,
                                                  publish_treasure_map=False)  # enact but don't publish
    treasure_map = enacted_policy.treasure_map
    blockchain_porter.publish_treasure_map(bytes(treasure_map), blockchain_bob_encrypting_key)

    # try getting the recently published treasure map
    map_id = blockchain_bob.construct_map_id(blockchain_alice.stamp,
                                             enacted_policy.label)
    retrieved_treasure_map = blockchain_porter.get_treasure_map(map_identifier=map_id,
                                                                bob_encrypting_key=blockchain_bob_encrypting_key)
    assert retrieved_treasure_map == treasure_map


def test_exec_work_order(blockchain_porter,
                         random_blockchain_policy,
                         blockchain_ursulas,
                         blockchain_bob,
                         blockchain_alice):
    # Setup
    network_middleware = MockRestMiddleware()
    # enact new random policy since idle_blockchain_policy/enacted_blockchain_policy already modified in previous tests
    enacted_policy = random_blockchain_policy.enact(network_middleware=network_middleware,
                                                    publish_treasure_map=False)  # enact but don't publish
    ursula_address, work_order = work_order_setup(enacted_policy,
                                                  blockchain_ursulas,
                                                  blockchain_bob,
                                                  blockchain_alice)
    # use porter
    result = blockchain_porter.exec_work_order(ursula_address=ursula_address,
                                               work_order_payload=work_order.payload())
    assert result
