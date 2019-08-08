from functools import partial

import pytest

from nucypher.utilities.sandbox.ursula import make_federated_ursulas

def test_learner_learns_about_domains_separately(ursula_federated_test_config, caplog):
        lonely_ursula_maker = partial(make_federated_ursulas,
                                      ursula_config=ursula_federated_test_config,
                                      quantity=3,
                                      know_each_other=True)

        global_learners = lonely_ursula_maker(domains={"nucypher1.test_suite"})
        first_domain_learners = lonely_ursula_maker(domains={"nucypher1.test_suite"})
        second_domain_learners = lonely_ursula_maker(domains={"nucypher2.test_suite"})

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

        new_first_domain_learner = lonely_ursula_maker(domains={"nucypher1.test_suite"}).pop()
        new_second_domain_learner = lonely_ursula_maker(domains={"nucypher2.test_suite"})

        new_first_domain_learner._current_teacher_node = big_learner
        new_first_domain_learner.learn_from_teacher_node()

        # This node, in the first domain, didn't learn about the second domain.
        assert not set(second_domain_learners).intersection(set(new_first_domain_learner.known_nodes))

        # However, it learned about *all* of the nodes in its own domain.
        assert set(first_domain_learners).intersection(set(new_first_domain_learner.known_nodes)) == first_domain_learners
