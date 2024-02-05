import contextlib
import time

import maya
import pytest
from nucypher_core.umbral import SecretKey, Signer

from nucypher.characters.lawful import Ursula
from nucypher.crypto.signing import SignatureStamp
from tests.mock.performance_mocks import (
    VerificationTracker,
    mock_cert_loading,
    mock_message_verification,
    mock_metadata_validation,
    mock_secret_source,
    mock_verify_node,
)
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


@pytest.mark.usefixtures("monkeypatch_get_staking_provider_from_operator")
def test_alice_can_learn_about_a_whole_bunch_of_ursulas(highperf_mocked_alice):
    # During the fixture execution, Alice verified one node.
    # TODO: Consider changing this - #1449
    assert VerificationTracker.node_verifications == 1

    _teacher = highperf_mocked_alice.current_teacher_node()

    # Ursulas in the fleet have mocked keys,
    # but we need the teacher to be able to sign the MetadataResponse.
    signer = Signer(SecretKey.random())
    _teacher._stamp = SignatureStamp(
        verifying_key=signer.verifying_key(), signer=signer
    )

    actual_ursula = MOCK_KNOWN_URSULAS_CACHE[_teacher.rest_interface.port]

    # A quick setup so that the bytes casting of Ursulas (on what in the real world will be the remote node)
    # doesn't take up all the time.
    _teacher_known_nodes_bytestring = actual_ursula.bytestring_of_known_nodes()
    actual_ursula.bytestring_of_known_nodes = (
        lambda *args, **kwargs: _teacher_known_nodes_bytestring
    )  # TODO: Formalize this?  #1537

    with (
        mock_cert_loading
    ), mock_verify_node, mock_message_verification, mock_metadata_validation:
        started = time.time()
        highperf_mocked_alice.block_until_number_of_known_nodes_is(
            4000, learn_on_this_thread=True
        )
        ended = time.time()
        elapsed = ended - started

    # TODO: probably can be brought down a lot when the core is moved to Rust
    assert (
        elapsed < 6
    )  # 6 seconds is still a little long to discover 4000 out of 5000 nodes, but before starting the optimization that went with this test, this operation took about 18 minutes on jMyles' laptop.
    assert (
        VerificationTracker.node_verifications == 1
    )  # We have only verified the first Ursula.
    assert (
        sum(isinstance(u, Ursula) for u in highperf_mocked_alice.known_nodes) < 20
    )  # We haven't instantiated many Ursulas.
    VerificationTracker.node_verifications = 0  # Cleanup


_POLICY_PRESERVER = []


@pytest.mark.skip("TODO: This test is not yet unfederated.")
def test_alice_verifies_ursula_just_in_time(
    fleet_of_highperf_mocked_ursulas, highperf_mocked_alice, highperf_mocked_bob
):
    mocks = (
        mock_secret_source(),
        mock_cert_loading,
        mock_metadata_validation,
        mock_message_verification,
    )

    with contextlib.ExitStack() as stack:
        for mock in mocks:
            stack.enter_context(mock)

        policy = highperf_mocked_alice.grant(
            highperf_mocked_bob,
            b"any label",
            threshold=20,
            shares=30,
            expiration=maya.when("next week"),
        )

    # TODO: Make some assertions about policy.
    total_verified = sum(
        node.verified_node for node in highperf_mocked_alice.known_nodes
    )
    # Alice may be able to verify more than `n`, but certainly not less,
    # otherwise `grant()` would fail.
    assert total_verified >= 30
    _POLICY_PRESERVER.append(policy)
