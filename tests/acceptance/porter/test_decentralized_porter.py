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

from tests.utils.middleware import MockRestMiddleware
from tests.utils.policy import retrieval_request_setup


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


def test_retrieve_cfrags(blockchain_porter,
                         random_blockchain_policy,
                         blockchain_bob,
                         blockchain_alice):
    # Setup
    network_middleware = MockRestMiddleware()
    # enact new random policy since idle_blockchain_policy/enacted_blockchain_policy already modified in previous tests
    enacted_policy = random_blockchain_policy.enact(network_middleware=network_middleware)
    retrieval_args, _ = retrieval_request_setup(enacted_policy, blockchain_bob, blockchain_alice)

    # use porter
    result = blockchain_porter.retrieve_cfrags(**retrieval_args)
    assert result
