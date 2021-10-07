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
from nucypher.network.middleware import RestMiddleware


def test_policy_simple_sinpa(blockchain_ursulas,
                             blockchain_alice,
                             blockchain_bob,
                             agency,
                             testerchain):
    """
    Making a Policy without paying.
    """
    amonia = Amonia.from_lawful_alice(blockchain_alice)

    # Setup the policy details
    shares = 3
    policy_end_datetime = maya.now() + datetime.timedelta(days=35)
    label = b"this_is_the_path_to_which_access_is_being_granted"

    bupkiss_policy = amonia.grant_without_paying(bob=blockchain_bob,
                                                 label=label,
                                                 threshold=2,
                                                 shares=shares,
                                                 rate=int(1e18),  # one ether
                                                 expiration=policy_end_datetime)

    # Enrico becomes
    enrico = Enrico(policy_encrypting_key=bupkiss_policy.public_key)
    plaintext = b"A crafty campaign"
    message_kit = enrico.encrypt_message(plaintext)

    with pytest.raises(Ursula.NotEnoughUrsulas):  # Return a more descriptive request error?
        blockchain_bob.retrieve_and_decrypt([message_kit],
                                            alice_verifying_key=amonia.stamp.as_umbral_pubkey(),
                                            encrypted_treasure_map=bupkiss_policy.treasure_map)

    for ursula in blockchain_ursulas:
        # Reset the Ursula for the next test.
        ursula.suspicious_activities_witnessed['freeriders'] = []


def test_try_to_post_free_service_by_hacking_enact(blockchain_ursulas,
                                                   blockchain_alice,
                                                   blockchain_bob,
                                                   agency,
                                                   testerchain):
    """
    This time we won't rely on the tabulation in Alice's enact() to catch the problem.
    """
    amonia = Amonia.from_lawful_alice(blockchain_alice)
    # Setup the policy details
    shares = 3
    policy_end_datetime = maya.now() + datetime.timedelta(days=35)
    label = b"another_path"

    bupkiss_policy = amonia.circumvent_safegaurds_and_grant_without_paying(bob=blockchain_bob,
                                                                           label=label,
                                                                           threshold=2,
                                                                           shares=shares,
                                                                           rate=int(1e18),  # one ether
                                                                           expiration=policy_end_datetime)

    # Enrico becomes
    enrico = Enrico(policy_encrypting_key=bupkiss_policy.public_key)
    plaintext = b"A crafty campaign"
    message_kit = enrico.encrypt_message(plaintext)

    with pytest.raises(Ursula.NotEnoughUrsulas):  # Return a more descriptive request error?
        blockchain_bob.retrieve_and_decrypt([message_kit],
                                            alice_verifying_key=amonia.stamp.as_umbral_pubkey(),
                                            encrypted_treasure_map=bupkiss_policy.treasure_map)


def test_pay_a_flunky_instead_of_the_arranged_ursula(blockchain_alice,
                                                     blockchain_bob,
                                                     blockchain_ursulas,
                                                     ursula_decentralized_test_config,
                                                     testerchain):
    amonia = Amonia.from_lawful_alice(blockchain_alice)
    target_ursulas = blockchain_ursulas[0], blockchain_ursulas[1], blockchain_ursulas[2]
    flunkies = [blockchain_ursulas[5], blockchain_ursulas[6], blockchain_ursulas[7]]

    # Setup the policy details
    shares = 3
    policy_end_datetime = maya.now() + datetime.timedelta(days=35)
    label = b"back_and_forth_forever"

    bupkiss_policy = amonia.grant_while_paying_the_wrong_nodes(ursulas_to_trick_into_working_for_free=target_ursulas,
                                                               ursulas_to_pay_instead=flunkies,
                                                               bob=blockchain_bob,
                                                               label=label,
                                                               threshold=2,
                                                               shares=shares,
                                                               rate=int(1e18),  # one ether
                                                               expiration=policy_end_datetime)

    # Enrico becomes
    enrico = Enrico(policy_encrypting_key=bupkiss_policy.public_key)
    plaintext = b"A crafty campaign"
    message_kit = enrico.encrypt_message(plaintext)

    with pytest.raises(Ursula.NotEnoughUrsulas):
        blockchain_bob.retrieve_and_decrypt([message_kit],
                                            alice_verifying_key=amonia.stamp.as_umbral_pubkey(),
                                            encrypted_treasure_map=bupkiss_policy.treasure_map)
