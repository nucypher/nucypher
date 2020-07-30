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

from collections import namedtuple

import os
from bytestring_splitter import VariableLengthBytestring
from eth_utils.address import to_checksum_address
from twisted.logger import LogLevel, globalLogPublisher

from nucypher.acumen.nicknames import nickname_from_seed
from nucypher.characters.base import Character
from tests.utils.middleware import MockRestMiddleware
from tests.utils.ursula import make_federated_ursulas


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
