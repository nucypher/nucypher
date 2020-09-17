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

from functools import partial

from nucypher.acumen.perception import FleetSensor
from nucypher.config.storages import TemporaryFileBasedNodeStorage, LocalFileBasedNodeStorage


def test_learner_learns_about_domains_separately(lonely_ursula_maker, caplog):
    _lonely_ursula_maker = partial(lonely_ursula_maker, know_each_other=True, quantity=3)

    global_learners = _lonely_ursula_maker(domain="nucypher1.test_suite")
    first_domain_learners = _lonely_ursula_maker(domain="nucypher1.test_suite")
    second_domain_learners = _lonely_ursula_maker(domain="nucypher2.test_suite")

    big_learner = global_learners.pop()

    assert len(big_learner.known_nodes) == 2

    # Learn about the fist domain.
    big_learner._current_teacher_node = first_domain_learners.pop()
    big_learner.learn_from_teacher_node()

    # Learn about the second domain.
    big_learner._current_teacher_node = second_domain_learners.pop()
    big_learner.learn_from_teacher_node()

    # All domain 1 nodes
    assert len(big_learner.known_nodes) == 5

    new_first_domain_learner = _lonely_ursula_maker(domain="nucypher1.test_suite").pop()
    _new_second_domain_learner = _lonely_ursula_maker(domain="nucypher2.test_suite")

    new_first_domain_learner._current_teacher_node = big_learner
    new_first_domain_learner.learn_from_teacher_node()

    # This node, in the first domain, didn't learn about the second domain.
    assert not set(second_domain_learners).intersection(new_first_domain_learner.known_nodes)

    # However, it learned about *all* of the nodes in its own domain.
    assert set(first_domain_learners).intersection(
            n.mature() for n in new_first_domain_learner.known_nodes) == first_domain_learners


def test_learner_restores_metadata_from_storage(lonely_ursula_maker, tmpdir):

    # Create a local file-based node storage
    root = tmpdir.mkdir("known_nodes")
    metadata = root.mkdir("metadata")
    certs = root.mkdir("certs")
    old_storage = LocalFileBasedNodeStorage(federated_only=True,
                                            metadata_dir=metadata,
                                            certificates_dir=certs,
                                            storage_root=root)

    # Use the ursula maker with this storage so it's populated with nodes from one domain
    _some_ursulas = lonely_ursula_maker(domain="fistro",
                                        node_storage=old_storage,
                                        know_each_other=True,
                                        quantity=3,
                                        save_metadata=True)

    # Create a pair of new learners in a different domain, using the previous storage, and learn from it
    new_learners = lonely_ursula_maker(domain="duodenal",
                                       node_storage=old_storage,
                                       quantity=2,
                                       know_each_other=True,
                                       save_metadata=False)
    learner, buddy = new_learners
    buddy._Learner__known_nodes = FleetSensor()

    # The learner shouldn't learn about any node from the first domain, since it's different.
    learner.learn_from_teacher_node()
    for restored_node in learner.known_nodes:
        assert restored_node.mature().serving_domain == learner.learning_domain

    # In fact, since the storage only contains nodes from a different domain,
    # the learner should only know its buddy from the second domain.
    assert set(learner.known_nodes) == {buddy}
