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

import time

from nucypher.characters.lawful import Ursula
from tests.performance_mocks import mock_cert_storage, mock_cert_loading, mock_verify_node, \
    mock_message_verification, \
    mock_metadata_validation, mock_signature_bytes, mock_stamp_call, mock_pubkey_from_bytes, VerificationTracker

"""
Node Discovery happens in phases.  The first step is for a network actor to learn about the mere existence of a Node.
This is a straightforward step which we currently do with our own logic, but which may someday be replaced by something
like libp2p, depending on the course of development of those sorts of tools.

After this, our "Learning Loop" does four other things in sequence which are not part of the offering of node discovery tooling alone:

* Instantiation of an actual Node object (currently, an Ursula object) from node metadata.
* Validation of the node's metadata (non-interactive; shows that the Node's public material is indeed signed by the wallet holder of its Staker).
* Verification of the Node itself (interactive; shows that the REST server operating at the Node's interface matches the node's metadata).
* Verification of the Stake (reads the blockchain; shows that the Node is sponsored by a Staker with sufficient Stake to support a Policy).

These tests show that each phase of this process is done correctly, and in some cases, with attention to specific
performance bottlenecks.
"""


def test_alice_can_learn_about_a_whole_bunch_of_ursulas(highperf_mocked_alice):
    # During the fixture execution, Alice verified one node.
    # TODO: Consider changing this - #1449
    assert VerificationTracker.node_verifications == 1

    with mock_cert_storage, mock_cert_loading, mock_verify_node, mock_message_verification, mock_metadata_validation:
        with mock_pubkey_from_bytes, mock_stamp_call, mock_signature_bytes:
            started = time.time()
            highperf_mocked_alice.block_until_number_of_known_nodes_is(8, learn_on_this_thread=True)
            ended = time.time()
            elapsed = ended - started

    assert VerificationTracker.node_verifications == 1  # We have only verified the first Ursula.
    assert sum(
        isinstance(u, Ursula) for u in highperf_mocked_alice.known_nodes) < 20  # We haven't instantiated many Ursulas.
    assert elapsed < 6  # 6 seconds is still a little long to discover 8 out of 5000 nodes, but before starting the optimization that went with this test, this operation took about 18 minutes on jMyles' laptop.
    VerificationTracker.node_verifications = 0  # Cleanup


@pytest.mark.parametrize('fleet_of_highperf_mocked_ursulas', [100], indirect=True)
def test_alice_verifies_ursula_just_in_time(fleet_of_highperf_mocked_ursulas, highperf_mocked_alice,
                                            highperf_mocked_bob):
    _umbral_pubkey_from_bytes = UmbralPublicKey.from_bytes

    def actual_random_key_instead(*args, **kwargs):
        _previous_bytes = args[0]
        serial = _previous_bytes[-5:]
        pubkey = NotAPublicKey(serial=serial)
        return pubkey

    def mock_set_policy(id_as_hex):
        return ""

    def mock_receive_treasure_map(treasure_map_id):
        return Response(bytes(), status=202)

    with NotARestApp.replace_route("receive_treasure_map", mock_receive_treasure_map):
        with NotARestApp.replace_route("set_policy", mock_set_policy):
            with patch('umbral.keys.UmbralPublicKey.__eq__', lambda *args, **kwargs: True):
                with patch('umbral.keys.UmbralPublicKey.from_bytes',
                           new=actual_random_key_instead), mock_message_verification:
                    highperf_mocked_alice.grant(highperf_mocked_bob, b"any label", m=20, n=30,
                                                expiration=maya.when('next week'))
    assert VerificationTracker.node_verifications == 30
