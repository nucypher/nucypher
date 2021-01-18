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

from nucypher.crypto.powers import DecryptingPower, SigningPower
from nucypher.policy.collections import TreasureMap


def test_complete_treasure_map_journey(federated_alice, federated_bob, federated_ursulas, mocker):

    treasure_map = TreasureMap(m=1)

    mock_arrangement_id = os.urandom(TreasureMap.ID_LENGTH)
    mock_arrangement = mocker.Mock(id=mock_arrangement_id)
    for ursula in federated_ursulas:
        treasure_map.add_arrangement(ursula, mock_arrangement)

    ursula_addresses = [u.checksum_address for u in federated_ursulas]
    for ursula, arrangement_id in treasure_map.destinations.items():
        assert ursula in ursula_addresses
        assert arrangement_id == mock_arrangement_id

    bob_encrypting_key = federated_bob.public_keys(DecryptingPower)
    bob_verifying_key = federated_bob.public_keys(SigningPower)

    treasure_map.prepare_for_publication(bob_encrypting_key=bob_encrypting_key,
                                         bob_verifying_key=bob_verifying_key,
                                         alice_stamp=federated_alice.stamp,
                                         label=b"chili")

    serialized_map = bytes(treasure_map)

    deserialized_map = TreasureMap.from_bytes(serialized_map)

    assert treasure_map.version == deserialized_map.version == TreasureMap.version

    compass = federated_bob.make_compass_for_alice(federated_alice)
    deserialized_map.orient(compass)

    assert treasure_map.m == deserialized_map.m == 1
    assert set(treasure_map.destinations) == set(deserialized_map.destinations)
