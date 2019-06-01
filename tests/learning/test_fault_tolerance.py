from collections import namedtuple
from functools import partial

from twisted.logger import globalLogPublisher, LogLevel

from constant_sorrow.constants import NOT_SIGNED

from nucypher.network.nodes import FleetStateTracker
from nucypher.utilities.sandbox.middleware import MockRestMiddleware
from nucypher.utilities.sandbox.ursula import make_federated_ursulas


def test_blockchain_ursula_is_not_valid_with_unsigned_identity_evidence(blockchain_ursulas, caplog):
    lonely_blockchain_learner, blockchain_teacher, unsigned = list(blockchain_ursulas)[0:3]

    unsigned._identity_evidence = NOT_SIGNED

    # Wipe known nodes .
    lonely_blockchain_learner._Learner__known_nodes = FleetStateTracker()
    lonely_blockchain_learner._current_teacher_node = blockchain_teacher

    lonely_blockchain_learner.remember_node(blockchain_teacher)
    warnings = []

    def warning_trapper(event):
        if event['log_level'] == LogLevel.warn:
            warnings.append(event)

    globalLogPublisher.addObserver(warning_trapper)

    lonely_blockchain_learner.learn_from_teacher_node()

    globalLogPublisher.removeObserver(warning_trapper)

    # We received one warning during learning, and it was about this very matter.
    assert len(warnings) == 1
    assert warnings[0]['log_format'] == unsigned.invalid_metadata_message.format(unsigned)

    assert unsigned not in lonely_blockchain_learner.known_nodes

    # TODO: #1035
    # minus 3 for self, a non-staking Ursula, and, of course, the unsigned ursula.
    assert len(lonely_blockchain_learner.known_nodes) == len(blockchain_ursulas) - 3
    assert blockchain_teacher in lonely_blockchain_learner.known_nodes


def test_emit_warning_upon_new_version(ursula_federated_test_config, caplog):
    lonely_ursula_maker = partial(make_federated_ursulas,
                                  ursula_config=ursula_federated_test_config,
                                  quantity=2,
                                  know_each_other=True)

    learner = lonely_ursula_maker().pop()
    teacher, new_node = lonely_ursula_maker()

    new_node.TEACHER_VERSION = learner.LEARNER_VERSION + 1
    learner._current_teacher_node = teacher

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
    crazy_bytes_representation = int(learner.LEARNER_VERSION + 1).to_bytes(2, byteorder="big") \
                                 + b"totally unintelligible nonsense"

    Response = namedtuple("MockResponse", ("content", "status_code"))
    response = Response(content=crazy_bytes_representation, status_code=200)
    learner.network_middleware.get_nodes_via_rest = lambda *args, **kwargs: response
    learner.learn_from_teacher_node()

    # TODO: #1039 - Fails because the above mocked Response is unsigned, and the API now enforces interface signatures
    # assert len(warnings) == 2
    # assert warnings[1]['log_format'] == learner.unknown_version_message.format(new_node,
    #                                                                            new_node.TEACHER_VERSION,
    #                                                                            learner.LEARNER_VERSION)

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
