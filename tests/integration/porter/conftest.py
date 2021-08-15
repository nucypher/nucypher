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
from base64 import b64decode

import pytest

from nucypher.crypto.powers import DecryptingPower
from nucypher.policy.maps import TreasureMap


@pytest.fixture(scope='module')
def random_federated_treasure_map_data(federated_alice, federated_bob, federated_ursulas):

    label = b'policy label'
    threshold = 2
    num_kfrags = threshold + 1
    _policy_key, kfrags = federated_alice.generate_kfrags(bob=federated_bob, label=label, m=threshold, n=num_kfrags)
    random_treasure_map = TreasureMap.construct_by_publisher(publisher=federated_alice,
                                                             bob=federated_bob,
                                                             label=label,
                                                             ursulas=list(federated_ursulas)[:num_kfrags],
                                                             verified_kfrags=kfrags,
                                                             m=threshold)

    yield federated_bob.public_keys(DecryptingPower), random_treasure_map
