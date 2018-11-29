from functools import partial

from nucypher.utilities.sandbox.ursula import make_federated_ursulas


def test_emit_warning_upon_new_version(ursula_federated_test_config, caplog):
    lonely_ursula_maker = partial(make_federated_ursulas,
                                  ursula_config=ursula_federated_test_config,
                                  quantity=2,
                                  know_each_other=True)
    learner = lonely_ursula_maker().pop()
    teacher, new_node = lonely_ursula_maker()

    new_node.TEACHER_VERSION = learner.LEARNER_VERSION + 1

    learner._current_teacher_node = teacher
    learner.learn_from_teacher_node()
