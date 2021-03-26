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

from umbral.kfrags import KFrag

from nucypher.crypto.powers import DecryptingPower, SigningPower
from nucypher.policy.collections import TreasureMap


def test_complete_treasure_map_journey(federated_alice, federated_bob, federated_ursulas):

    treasure_map = TreasureMap(m=1)

    mock_kfrag = os.urandom(KFrag.expected_bytes_length())
    for ursula in federated_ursulas:
        treasure_map.add_kfrag(ursula, mock_kfrag, federated_alice.stamp)

    ursula_rolodex = {u.checksum_address: u for u in federated_ursulas}
    for ursula_address, encrypted_kfrag in treasure_map.destinations.items():
        assert ursula_address in ursula_rolodex
        ursula = ursula_rolodex[ursula_address]
        assert mock_kfrag == ursula.verify_from(federated_alice, encrypted_kfrag, decrypt=True)  # FIXME: 2203

    bob_encrypting_key = federated_bob.public_keys(DecryptingPower)
    bob_verifying_key = federated_bob.public_keys(SigningPower)

    treasure_map.prepare_for_publication(bob_encrypting_key=bob_encrypting_key,
                                         bob_verifying_key=bob_verifying_key,
                                         alice_stamp=federated_alice.stamp,
                                         label="chili con carne 🔥".encode('utf-8'))

    serialized_map = bytes(treasure_map)

    deserialized_map = TreasureMap.from_bytes(serialized_map)

    assert treasure_map.version == deserialized_map.version == TreasureMap.version

    compass = federated_bob.make_compass_for_alice(federated_alice)
    deserialized_map.orient(compass)

    assert treasure_map.m == deserialized_map.m == 1
    assert set(treasure_map.destinations) == set(deserialized_map.destinations)
