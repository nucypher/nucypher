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


import datetime

import maya
import pytest

from nucypher.core import EncryptedKeyFrag

from nucypher.crypto.utils import keccak_digest


def test_decentralized_grant(blockchain_alice, blockchain_bob, blockchain_ursulas):
    # Setup the policy details
    shares = 3
    policy_end_datetime = maya.now() + datetime.timedelta(days=35)
    label = b"this_is_the_path_to_which_access_is_being_granted"

    # Create the Policy, Granting access to Bob
    policy = blockchain_alice.grant(bob=blockchain_bob,
                                    label=label,
                                    threshold=2,
                                    shares=shares,
                                    rate=int(1e18),  # one ether
                                    expiration=policy_end_datetime)

    treasure_map = blockchain_bob._decrypt_treasure_map(policy.treasure_map,
                                                        policy.publisher_verifying_key)

    # The number of actual destinations is exactly equal to shares.
    assert len(treasure_map.destinations) == shares

    # Let's look at the destinations.
    for ursula in blockchain_ursulas:
        if ursula.checksum_address in treasure_map.destinations:
            kfrag_kit = treasure_map.destinations[ursula.checksum_address]

            # TODO: try to decrypt?
            assert isinstance(kfrag_kit, EncryptedKeyFrag)
