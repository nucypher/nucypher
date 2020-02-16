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
from nucypher.keystore.db.models import PolicyArrangement


@pytest.mark.usefixtures('blockchain_ursulas')
def test_policy_simple_sinpa(blockchain_alice, blockchain_bob, agency, testerchain):
    """
    Making a Policy without paying.
    """
    amonia = Amonia.from_lawful_alice(blockchain_alice)
    # Setup the policy details
    n = 3
    policy_end_datetime = maya.now() + datetime.timedelta(days=5)
    label = b"this_is_the_path_to_which_access_is_being_granted"

    with pytest.raises(amonia.NotEnoughNodes):
        amonia.grant_without_paying(bob=blockchain_bob,
                                    label=label,
                                    m=2,
                                    n=n,
                                    rate=int(1e18),  # one ether
                                    expiration=policy_end_datetime)


def test_try_to_post_free_arrangement_by_hacking_enact(blockchain_ursulas, blockchain_alice, blockchain_bob, agency,
                                                       testerchain):
    """
    This time we won't rely on the tabulation in Alice's enact to catch the problem.
    """
    amonia = Amonia.from_lawful_alice(blockchain_alice)
    # Setup the policy details
    n = 3
    policy_end_datetime = maya.now() + datetime.timedelta(days=5)
    label = b"this_is_the_path_to_which_access_is_being_granted"

    bupkiss_policy = amonia.circumvent_safegaurds_and_grant_without_paying(bob=blockchain_bob,
                                                                           label=label,
                                                                           m=2,
                                                                           n=n,
                                                                           rate=int(1e18),  # one ether
                                                                           expiration=policy_end_datetime)

    for ursula in blockchain_ursulas:
        # Even though the grant executed without error, no Ursula saved a KFrag.
        all_arrangements = ursula.datastore._session_on_init_thread.query(PolicyArrangement).all()
        if all_arrangements:
            assert len(all_arrangements) == 1  # Just the single arrangement has been considered.
            arrangement = all_arrangements[0]
            assert arrangement.kfrag is None
