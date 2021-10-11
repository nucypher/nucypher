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


import contextlib
import time
from datetime import datetime
from unittest.mock import patch

import maya
import pytest
from flask import Response

from nucypher.characters.lawful import Ursula
from nucypher.crypto.signing import SignatureStamp
from nucypher.crypto.umbral_adapter import SecretKey, Signer, PublicKey, encrypt
from nucypher.datastore.base import RecordField
from nucypher.network.nodes import Teacher
from tests.markers import skip_on_circleci
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
    mock_verify_node
)
from tests.utils.middleware import SluggishLargeFleetMiddleware
from tests.utils.ursula import MOCK_KNOWN_URSULAS_CACHE

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


@skip_on_circleci  # TODO: #2552 Taking 6-10 seconds on CircleCI, passing locally.
def test_alice_can_learn_about_a_whole_bunch_of_ursulas(highperf_mocked_alice):
    # During the fixture execution, Alice verified one node.
    # TODO: Consider changing this - #1449
    assert VerificationTracker.node_verifications == 1

    _teacher = highperf_mocked_alice.current_teacher_node()

    # Ursulas in the fleet have mocked keys,
    # but we need the teacher to be able to sign the MetadataResponse.
    signer = Signer(SecretKey.random())
    _teacher._stamp = SignatureStamp(verifying_key=signer.verifying_key(), signer=signer)

    actual_ursula = MOCK_KNOWN_URSULAS_CACHE[_teacher.rest_interface.port]

    # A quick setup so that the bytes casting of Ursulas (on what in the real world will be the remote node)
    # doesn't take up all the time.
    _teacher_known_nodes_bytestring = actual_ursula.bytestring_of_known_nodes()
    actual_ursula.bytestring_of_known_nodes = lambda *args, **kwargs: _teacher_known_nodes_bytestring  # TODO: Formalize this?  #1537

    with mock_cert_storage, mock_cert_loading, mock_verify_node, mock_message_verification, mock_metadata_validation:
        started = time.time()
        highperf_mocked_alice.block_until_number_of_known_nodes_is(4000, learn_on_this_thread=True)
        ended = time.time()
        elapsed = ended - started

    # TODO: probably can be brought down a lot when the core is moved to Rust
    assert elapsed < 6  # 6 seconds is still a little long to discover 4000 out of 5000 nodes, but before starting the optimization that went with this test, this operation took about 18 minutes on jMyles' laptop.
    assert VerificationTracker.node_verifications == 1  # We have only verified the first Ursula.
    assert sum(
        isinstance(u, Ursula) for u in highperf_mocked_alice.known_nodes) < 20  # We haven't instantiated many Ursulas.
    VerificationTracker.node_verifications = 0  # Cleanup


_POLICY_PRESERVER = []


@skip_on_circleci  # TODO: #2552 Taking 6-10 seconds on CircleCI, passing locally.
def test_alice_verifies_ursula_just_in_time(fleet_of_highperf_mocked_ursulas,
                                            highperf_mocked_alice,
                                            highperf_mocked_bob):
    # Patch the Datastore PolicyArrangement model with the highperf
    # NotAPublicKey
    not_public_key_record_field = RecordField(NotAPublicKey, encode=bytes,
                                              decode=NotAPublicKey.from_bytes)

    def mock_set_policy(id_as_hex):
        return ""

    def mock_receive_treasure_map():
        return Response(bytes(), status=201)

    def mock_encrypt(public_key, plaintext):
        if not isinstance(public_key, PublicKey):
            public_key = public_key.i_want_to_be_a_real_boy()
        return encrypt(public_key, plaintext)

    mocks = (
        NotARestApp.replace_route("receive_treasure_map", mock_receive_treasure_map),
        NotARestApp.replace_route("set_policy", mock_set_policy),
        patch('nucypher.crypto.umbral_adapter.PublicKey.__eq__', lambda *args, **kwargs: True),
        mock_pubkey_from_bytes(),
        mock_secret_source(),
        mock_cert_loading,
        mock_metadata_validation,
        mock_message_verification,
        patch("nucypher.datastore.models.PolicyArrangement._alice_verifying_key",
              new=not_public_key_record_field),
        patch('nucypher.crypto.umbral_adapter.encrypt', new=mock_encrypt),
        )

    with contextlib.ExitStack() as stack:
        for mock in mocks:
            stack.enter_context(mock)

        policy = highperf_mocked_alice.grant(
            highperf_mocked_bob, b"any label", threshold=20, shares=30,
            expiration=maya.when('next week'))

    # TODO: Make some assertions about policy.
    total_verified = sum(node.verified_node for node in highperf_mocked_alice.known_nodes)
    # Alice may be able to verify more than `n`, but certainly not less,
    # otherwise `grant()` would fail.
    assert total_verified >= 30
    _POLICY_PRESERVER.append(policy)
