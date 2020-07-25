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
from datetime import datetime
from unittest.mock import patch

import maya
import pytest
import pytest_twisted
from twisted.internet import defer, reactor
from twisted.internet.threads import deferToThread, blockingCallFromThread

from nucypher.characters.lawful import Ursula
from tests.utils.middleware import SluggishLargeFleetMiddleware
from tests.utils.ursula import MOCK_KNOWN_URSULAS_CACHE
from umbral.keys import UmbralPublicKey
from tests.mock.performance_mocks import (
    NotAPublicKey,
    NotARestApp,
    VerificationTracker,
    mock_cert_loading,
    mock_cert_storage,
    mock_message_verification,
    mock_metadata_validation,
    mock_pubkey_from_bytes,
    mock_secret_source,
    mock_signature_bytes,
    mock_stamp_call,
    mock_verify_node
)

"""
Node Discovery happens in phases.  The first step is for a network actor to learn about the mere existence of a Node.
This is a straightforward step which we currently do with our own logic, but which may someday be replaced by something
like libp2p, depending on the course of development of those sorts of tools.  The introduction of hamming distance
in particular is useful when wanting to learn about a small number (~500) of nodes among a much larger (25,000+) swarm.
This toolchain is not built for that scenario at this time, although it is not a stated nongoal. 

After this, our "Learning Loop" does four other things in sequence which are not part of the offering of node discovery tooling alone:

* Instantiation of an actual Node object (currently, an Ursula object) from node metadata.  TODO
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

    _teacher = highperf_mocked_alice.current_teacher_node()
    actual_ursula = MOCK_KNOWN_URSULAS_CACHE[_teacher.rest_interface.port]

    # A quick setup so that the bytes casting of Ursulas (on what in the real world will be the remote node)
    # doesn't take up all the time.
    _teacher_known_nodes_bytestring = actual_ursula.bytestring_of_known_nodes()
    actual_ursula.bytestring_of_known_nodes = lambda *args, ** kwargs: _teacher_known_nodes_bytestring  # TODO: Formalize this?  #1537

    with mock_cert_storage, mock_cert_loading, mock_verify_node, mock_message_verification, mock_metadata_validation:
        with mock_pubkey_from_bytes(), mock_stamp_call, mock_signature_bytes:
            started = time.time()
            highperf_mocked_alice.block_until_number_of_known_nodes_is(4000, learn_on_this_thread=True)
            ended = time.time()
            elapsed = ended - started

    assert elapsed < 6  # 6 seconds is still a little long to discover 4000 out of 5000 nodes, but before starting the optimization that went with this test, this operation took about 18 minutes on jMyles' laptop.
    assert VerificationTracker.node_verifications == 1  # We have only verified the first Ursula.
    assert sum(
        isinstance(u, Ursula) for u in highperf_mocked_alice.known_nodes) < 20  # We haven't instantiated many Ursulas.
    VerificationTracker.node_verifications = 0  # Cleanup


_POLICY_PRESERVER = []


def test_alice_verifies_ursula_just_in_time(fleet_of_highperf_mocked_ursulas,
                                            highperf_mocked_alice,
                                            highperf_mocked_bob):
    _umbral_pubkey_from_bytes = UmbralPublicKey.from_bytes

    def actual_random_key_instead(*args, **kwargs):
        _previous_bytes = args[0]
        serial = _previous_bytes[-5:]
        pubkey = NotAPublicKey(serial=serial)
        return pubkey

    def mock_set_policy(id_as_hex):
        return ""

    with NotARestApp.replace_route("set_policy", mock_set_policy):
        with patch('umbral.keys.UmbralPublicKey.__eq__', lambda *args, **kwargs: True):
            with patch('umbral.keys.UmbralPublicKey.from_bytes',
                       new=actual_random_key_instead):
                with mock_cert_loading, mock_metadata_validation, mock_message_verification:
                    with mock_secret_source():
                        policy = highperf_mocked_alice.grant(
                            highperf_mocked_bob, b"any label", m=20, n=30,
                            expiration=maya.when('next week'),
                            publish_treasure_map=False)
    _POLICY_PRESERVER.append(policy)

    total_verified = sum(node.verified_node for node in highperf_mocked_alice.known_nodes)
    assert total_verified == 30


@pytest_twisted.inlineCallbacks
def test_mass_treasure_map_placement(fleet_of_highperf_mocked_ursulas,
                                     highperf_mocked_alice,
                                     highperf_mocked_bob):
    """
    Large-scale map placement with a middleware that simulates network latency.

    In three parts.
    """
    # The nodes who match the map distribution criteria.
    nodes_we_expect_to_have_the_map = highperf_mocked_bob.matching_nodes_among(fleet_of_highperf_mocked_ursulas)

    preparation_started = datetime.now()

    # # # Loop through and instantiate actual rest apps so as not to pollute the time measurement (doesn't happen in real world).
    for node in nodes_we_expect_to_have_the_map:
        highperf_mocked_alice.network_middleware.client.parse_node_or_host_and_port(node)  # Causes rest app to be made (happens JIT in other testS)

    highperf_mocked_alice.network_middleware = SluggishLargeFleetMiddleware()

    policy = _POLICY_PRESERVER.pop()

    started = datetime.now()

    with patch('umbral.keys.UmbralPublicKey.__eq__', lambda *args, **kwargs: True), mock_metadata_validation:

        # PART I: The function returns sychronously and quickly.

        defer.setDebugging(False)  # Debugging messes up the timing here; comment this line out if you actually need it.
        # returns instantly.
        policy.publish_treasure_map(network_middleware=highperf_mocked_alice.network_middleware)

        nodes_that_have_the_map_when_we_return = []

        for ursula in nodes_we_expect_to_have_the_map:
            if policy.treasure_map in list(ursula.treasure_maps.values()):
                nodes_that_have_the_map_when_we_return.append(ursula)

        # Very few have gotten the map yet; it's happening in the background.
        # Note: if you put a breakpoint above this line, you will likely need to comment this assertion out.
        assert len(
            nodes_that_have_the_map_when_we_return) <= 5  # Maybe a couple finished already, especially if this is a lightning fast computer.  But more than five is weird.

        defer.setDebugging(True)

        # PART II: We block for a little while to ensure that the distribution is going well.

        # Wait until about ten percent of the distribution has occurred.
        # We do it in a deferred here in the test because it will block the entire process, but in the real-world, we can do this on the granting thread.

        def count_recipients_after_block():
            policy.publishing_mutex.block_for_a_little_while()
            little_while_ended_at = datetime.now()

            # Here we'll just count the nodes that have the map.  In the real world, we can do a sanity check
            # to make sure things haven't gone sideways.

            nodes_that_have_the_map_when_we_unblock = sum(policy.treasure_map in list(u.treasure_maps.values()) for u in nodes_we_expect_to_have_the_map)

            return nodes_that_have_the_map_when_we_unblock, little_while_ended_at

        d = deferToThread(count_recipients_after_block)
        yield d
        nodes_that_have_the_map_when_we_unblock, little_while_ended_at = d.result

        # The number of nodes having the map is at least the minimum to have unblocked.
        assert nodes_that_have_the_map_when_we_unblock >= policy.publishing_mutex._block_until_this_many_are_complete

        # The number of nodes having the map is approximately the number you'd expect from full utilization of Alice's publication threadpool.
        assert nodes_that_have_the_map_when_we_unblock == pytest.approx(highperf_mocked_alice.publication_threadpool.max, .1)

        # PART III: Having made proper assertions about the publication call and the first block, we allow the rest to
        # happen in the background and then ensure that each phase was timely.
        successful_responses = []

        def find_successful_responses(map_publication_responses):
            for was_succssful, http_response in map_publication_responses:
                assert was_succssful
                assert http_response.status_code == 202
                successful_responses.append(http_response)

        policy.publishing_mutex.addCallback(find_successful_responses)
        yield policy.publishing_mutex  # This will block until the distribution is complete.
        complete_distribution_time = datetime.now() - started

        # We have the same number of successful responses as nodes we expected to have the map.
        assert len(successful_responses) == len(nodes_we_expect_to_have_the_map)

        # TODO: Assert that no nodes outside those expected received the map.

        partial_blocking_duration = little_while_ended_at - started
        # Before Treasure Island (1741), this process took about 3 minutes.
        assert partial_blocking_duration.total_seconds() < 3
        assert complete_distribution_time.total_seconds() < 10
        # On CI, we expect these times to be even less.  (Around 1 and 3.5 seconds, respectively)
        # But with debuggers and other processes running on laptops, we give a little leeway.
