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

from nucypher.characters.unlawful import Amonia
from nucypher.datastore.db.models import PolicyArrangement


def test_policy_simple_sinpa(blockchain_ursulas, blockchain_alice, blockchain_bob, agency, testerchain):
    """
    Making a Policy without paying.
    """
    amonia = Amonia.from_lawful_alice(blockchain_alice)
    # Setup the policy details
    n = 3
    policy_end_datetime = maya.now() + datetime.timedelta(days=5)
    label = b"this_is_the_path_to_which_access_is_being_granted"

    with pytest.raises(amonia.NotEnoughNodes):
        _bupkiss_policy = amonia.grant_without_paying(bob=blockchain_bob,
                                                      label=label,
                                                      m=2,
                                                      n=n,
                                                      rate=int(1e18),  # one ether
                                                      expiration=policy_end_datetime)

    for ursula in blockchain_ursulas:
        # Reset the Ursula for the next test.
        ursula.suspicious_activities_witnessed['freeriders'] = []
        ursula.datastore._session_on_init_thread.query(PolicyArrangement).delete()


def test_try_to_post_free_arrangement_by_hacking_enact(blockchain_ursulas, blockchain_alice, blockchain_bob, agency,
                                                       testerchain):
    """
    This time we won't rely on the tabulation in Alice's enact() to catch the problem.
    """
    amonia = Amonia.from_lawful_alice(blockchain_alice)
    # Setup the policy details
    n = 3
    policy_end_datetime = maya.now() + datetime.timedelta(days=5)
    label = b"another_path"

    bupkiss_policy = amonia.circumvent_safegaurds_and_grant_without_paying(bob=blockchain_bob,
                                                                           label=label,
                                                                           m=2,
                                                                           n=n,
                                                                           rate=int(1e18),  # one ether
                                                                           expiration=policy_end_datetime,
                                                                           publish_treasure_map=False)

    for ursula in blockchain_ursulas:
        # Even though the grant executed without error...
        all_arrangements = ursula.datastore._session_on_init_thread.query(PolicyArrangement).all()
        if all_arrangements:
            arrangement = all_arrangements[0]  # ...and Ursula did save the Arrangement after considering it...
            assert arrangement.kfrag is None  # ...Ursula did *not* save a KFrag and will not service this Policy.

            # Additionally, Ursula logged Amonia as a freerider:
            freeriders = ursula.suspicious_activities_witnessed['freeriders']
            assert len(freeriders) == 1
            assert freeriders[0][0] == amonia

            # Reset the Ursula for the next test.
            ursula.suspicious_activities_witnessed['freeriders'] = []
            ursula.datastore._session_on_init_thread.query(PolicyArrangement).delete()


def test_pay_a_flunky_instead_of_the_arranged_ursula(blockchain_alice, blockchain_bob, blockchain_ursulas,
                                                     ursula_decentralized_test_config,
                                                     testerchain):
    amonia = Amonia.from_lawful_alice(blockchain_alice)
    target_ursulas = blockchain_ursulas[0], blockchain_ursulas[1], blockchain_ursulas[2]
    flunkies = [blockchain_ursulas[5], blockchain_ursulas[6], blockchain_ursulas[7]]

    # Setup the policy details
    n = 3
    policy_end_datetime = maya.now() + datetime.timedelta(days=5)
    label = b"back_and_forth_forever"

    bupkiss_policy = amonia.grant_while_paying_the_wrong_nodes(ursulas_to_trick_into_working_for_free=target_ursulas,
                                                               ursulas_to_pay_instead=flunkies,
                                                               bob=blockchain_bob,
                                                               label=label,
                                                               m=2,
                                                               n=n,
                                                               rate=int(1e18),  # one ether
                                                               expiration=policy_end_datetime,
                                                               publish_treasure_map=False)

    # Same exact set of assertions as the last test:
    for ursula in blockchain_ursulas:
        # Even though the grant executed without error...
        all_arrangements = ursula.datastore._session_on_init_thread.query(PolicyArrangement).all()
        if all_arrangements:
            arrangement = all_arrangements[0]  # ...and Ursula did save the Arrangement after considering it...
            assert arrangement.kfrag is None  # ...Ursula did *not* save a KFrag and will not service this Policy.

            # Additionally, Ursula logged Amonia as a freerider:
            freeriders = ursula.suspicious_activities_witnessed['freeriders']
            assert len(freeriders) == 1
            assert freeriders[0][0] == amonia

            # Reset the Ursula for the next test.
            ursula.suspicious_activities_witnessed['freeriders'] = []
            ursula.datastore._session_on_init_thread.query(PolicyArrangement).delete()
