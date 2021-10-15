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

from nucypher.core import HRAC, TreasureMap

from nucypher.crypto.powers import DecryptingPower


@pytest.fixture(scope='module')
def random_federated_treasure_map_data(federated_alice, federated_bob, federated_ursulas):

    label = b'policy label'
    threshold = 2
    shares = threshold + 1
    policy_key, kfrags = federated_alice.generate_kfrags(bob=federated_bob, label=label, threshold=threshold, shares=shares)
    hrac = HRAC.derive(publisher_verifying_key=federated_alice.stamp.as_umbral_pubkey(),
                       bob_verifying_key=federated_bob.stamp.as_umbral_pubkey(),
                       label=label)

    assigned_kfrags = {
        ursula.checksum_address: (ursula.public_keys(DecryptingPower), vkfrag)
        for ursula, vkfrag in zip(list(federated_ursulas)[:shares], kfrags)}

    random_treasure_map = TreasureMap.construct_by_publisher(hrac=hrac,
                                                             policy_encrypting_key=policy_key,
                                                             signer=federated_alice.stamp.as_umbral_signer(),
                                                             assigned_kfrags=assigned_kfrags,
                                                             threshold=threshold)

    bob_key = federated_bob.public_keys(DecryptingPower)
    enc_treasure_map = random_treasure_map.encrypt(signer=federated_alice.stamp.as_umbral_signer(),
                                                   recipient_key=bob_key)

    yield bob_key, enc_treasure_map
