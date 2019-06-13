import os
from collections import namedtuple

import pytest
from eth_utils.address import to_checksum_address
from twisted.logger import globalLogPublisher, LogLevel

from bytestring_splitter import VariableLengthBytestring
from constant_sorrow.constants import NOT_SIGNED

from nucypher.characters.base import Character
from nucypher.network.nicknames import nickname_from_seed
from nucypher.network.nodes import FleetStateTracker
from nucypher.utilities.sandbox.middleware import MockRestMiddleware
from nucypher.utilities.sandbox.ursula import make_federated_ursulas


def test_blockchain_ursula_stamp_verification_tolerance(blockchain_ursulas, caplog):

    #
    # Setup
    #

    # TODO: #1035
    lonely_blockchain_learner, blockchain_teacher, unsigned, *the_others, non_staking_ursula = list(blockchain_ursulas)

    warnings = []

    def warning_trapper(event):
        if event['log_level'] == LogLevel.warn:
            warnings.append(event)

    #
    # Attempt to verify unsigned stamp
    #

    unsigned._Teacher__decentralized_identity_evidence = NOT_SIGNED

    # Wipe known nodes!
    lonely_blockchain_learner._Learner__known_nodes = FleetStateTracker()
    lonely_blockchain_learner._current_teacher_node = blockchain_teacher
    lonely_blockchain_learner.remember_node(blockchain_teacher)

    globalLogPublisher.addObserver(warning_trapper)
    lonely_blockchain_learner.learn_from_teacher_node()
    globalLogPublisher.removeObserver(warning_trapper)

    # We received one warning during learning, and it was about this very matter.
    assert len(warnings) == 1
    warning = warnings[0]['log_format']
    assert str(unsigned) in warning
    assert "stamp is unsigned" in warning  # TODO: Cleanup logging templates
    assert unsigned not in lonely_blockchain_learner.known_nodes

    # TODO: #1035
    # minus 3: self, a non-staking ursula, and the unsigned ursula.
    assert len(lonely_blockchain_learner.known_nodes) == len(blockchain_ursulas) - 3
    assert blockchain_teacher in lonely_blockchain_learner.known_nodes


@pytest.mark.skip("See Issue #1075")  # TODO: Issue #1075
def test_non_staking_ursula_tolerance(blockchain_ursulas):

    lonely_blockchain_learner, blockchain_teacher, unsigned, *the_others, non_staking_ursula = list(blockchain_ursulas)

    warnings = []

    def warning_trapper(event):
        if event['log_level'] == LogLevel.warn:
            warnings.append(event)

    lonely_blockchain_learner._current_teacher_node = non_staking_ursula
    globalLogPublisher.addObserver(warning_trapper)
    lonely_blockchain_learner.learn_from_teacher_node()
    globalLogPublisher.removeObserver(warning_trapper)

    assert len(warnings) == 2
    warning = warnings[1]['log_format']
    assert str(non_staking_ursula) in warning
    assert "no active stakes" in warning  # TODO: Cleanup logging templates
    assert non_staking_ursula not in lonely_blockchain_learner.known_nodes


def test_emit_warning_upon_new_version(ursula_federated_test_config, caplog):

    nodes = make_federated_ursulas(ursula_config=ursula_federated_test_config,
                                   quantity=3,
                                   know_each_other=False)
    teacher, learner, new_node = nodes

    learner.remember_node(teacher)
    teacher.remember_node(learner)
    teacher.remember_node(new_node)

    new_node.TEACHER_VERSION = learner.LEARNER_VERSION + 1

    warnings = []

    def warning_trapper(event):
        if event['log_level'] == LogLevel.warn:
            warnings.append(event)

    globalLogPublisher.addObserver(warning_trapper)
    learner.learn_from_teacher_node()

    assert len(warnings) == 1
    assert warnings[0]['log_format'] == learner.unknown_version_message.format(new_node,
                                                                               new_node.TEACHER_VERSION,
                                                                               learner.LEARNER_VERSION)

    # Now let's go a little further: make the version totally unrecognizable.

    # First, there's enough garbage to at least scrape a potential checksum address
    fleet_snapshot = os.urandom(32 + 4)
    random_bytes = os.urandom(50)  # lots of garbage in here
    future_version = learner.LEARNER_VERSION + 42
    version_bytes = future_version.to_bytes(2, byteorder="big")
    crazy_bytes = fleet_snapshot + VariableLengthBytestring(version_bytes + random_bytes)
    signed_crazy_bytes = bytes(teacher.stamp(crazy_bytes))

    Response = namedtuple("MockResponse", ("content", "status_code"))
    response = Response(content=signed_crazy_bytes + crazy_bytes, status_code=200)

    learner._current_teacher_node = teacher
    learner.network_middleware.get_nodes_via_rest = lambda *args, **kwargs: response
    learner.learn_from_teacher_node()

    # If you really try, you can read a node representation from the garbage
    accidental_checksum = to_checksum_address(random_bytes[:20])
    accidental_nickname = nickname_from_seed(accidental_checksum)[0]
    accidental_node_repr = Character._display_name_template.format("Ursula", accidental_nickname, accidental_checksum)

    assert len(warnings) == 2
    assert warnings[1]['log_format'] == learner.unknown_version_message.format(accidental_node_repr,
                                                                               future_version,
                                                                               learner.LEARNER_VERSION)

    # This time, however, there's not enough garbage to assume there's a checksum address...
    random_bytes = os.urandom(2)
    crazy_bytes = fleet_snapshot + VariableLengthBytestring(version_bytes + random_bytes)
    signed_crazy_bytes = bytes(teacher.stamp(crazy_bytes))

    response = Response(content=signed_crazy_bytes + crazy_bytes, status_code=200)

    learner._current_teacher_node = teacher
    learner.learn_from_teacher_node()

    assert len(warnings) == 3
    # ...so this time we get a "really unknown version message"
    assert warnings[2]['log_format'] == learner.really_unknown_version_message.format(future_version,
                                                                                      learner.LEARNER_VERSION)

    globalLogPublisher.removeObserver(warning_trapper)


def test_node_posts_future_version(federated_ursulas):
    ursula = list(federated_ursulas)[0]
    middleware = MockRestMiddleware()

    warnings = []

    def warning_trapper(event):
        if event['log_level'] == LogLevel.warn:
            warnings.append(event)

    globalLogPublisher.addObserver(warning_trapper)

    crazy_node = b"invalid-node"
    middleware.get_nodes_via_rest(node=ursula,
                                  announce_nodes=(crazy_node,))
    assert len(warnings) == 1
    future_node = list(federated_ursulas)[1]
    future_node.TEACHER_VERSION = future_node.TEACHER_VERSION + 10
    future_node_bytes = bytes(future_node)
    middleware.get_nodes_via_rest(node=ursula,
                                  announce_nodes=(future_node_bytes,))
    assert len(warnings) == 2
