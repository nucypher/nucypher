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

from nucypher.characters.lawful import Enrico, Ursula
from nucypher.characters.unlawful import Amonia


@pytest.mark.skip('FIXME - DISABLED FOR TDEC ADAPTATION DEVELOPMENT')
def test_try_to_post_free_service_by_hacking_enact(blockchain_ursulas,
                                                   blockchain_alice,
                                                   blockchain_bob,
                                                   agency,
                                                   testerchain):
    """
    This time we won't rely on the tabulation in Alice's enact() to catch the problem.
    """
    amonia = Amonia.from_lawful_alice(blockchain_alice)
    # Set up the policy details
    shares = 3
    policy_end_datetime = maya.now() + datetime.timedelta(days=35)
    label = b"another_path"

    bupkiss_policy = amonia.circumvent_safegaurds_and_grant_without_paying(bob=blockchain_bob,
                                                                           label=label,
                                                                           threshold=2,
                                                                           shares=shares,
                                                                           expiration=policy_end_datetime)

    # Enrico becomes
    enrico = Enrico(policy_encrypting_key=bupkiss_policy.public_key)
    plaintext = b"A crafty campaign"
    message_kit = enrico.encrypt_message(plaintext)

    with pytest.raises(Ursula.NotEnoughUrsulas):  # Return a more descriptive request error?
        blockchain_bob.retrieve_and_decrypt([message_kit],
                                            alice_verifying_key=amonia.stamp.as_umbral_pubkey(),
                                            encrypted_treasure_map=bupkiss_policy.treasure_map)
