from pathlib import Path

import pytest

from nucypher.acumen.perception import FleetSensor
from nucypher.characters.lawful import Ursula
from nucypher.config.storages import LocalFileBasedNodeStorage
from nucypher.network.nodes import TEACHER_NODES
from tests.utils.ursula import make_ursulas


@pytest.mark.usefixtures("test_registry_source_manager")
def test_learner_learns_about_domains_separately(lonely_ursula_maker, caplog):
    hero_learner, other_first_domain_learner = lonely_ursula_maker(
        domain="nucypher1.test_suite", quantity=2
    )
    _nobody = lonely_ursula_maker(domain="nucypher1.test_suite", quantity=1).pop()
    other_first_domain_learner.remember_node(_nobody)

    second_domain_learners = lonely_ursula_maker(domain="nucypher2.test_suite", know_each_other=True, quantity=3)

    assert len(hero_learner.known_nodes) == 0

    # Learn from a teacher in our domain.
    hero_learner.remember_node(other_first_domain_learner)
    hero_learner.start_learning_loop(now=True)
    hero_learner.learn_from_teacher_node()

    # All domain 1 nodes
    assert len(hero_learner.known_nodes) == 2

    # Learn about the second domain.
    hero_learner._current_teacher_node = second_domain_learners.pop()
    hero_learner.learn_from_teacher_node()

    # All domain 1 nodes
    assert len(hero_learner.known_nodes) == 2

    new_first_domain_learner = lonely_ursula_maker(domain="nucypher1.test_suite", quantity=1).pop()
    _new_second_domain_learner = lonely_ursula_maker(domain="nucypher2.test_suite", quantity=1).pop()

    new_first_domain_learner.remember_node(hero_learner)

    new_first_domain_learner.learn_from_teacher_node()

    # This node, in the first domain, didn't learn about the second domain.
    assert not set(second_domain_learners).intersection(new_first_domain_learner.known_nodes)

    # However, it learned about *all* of the nodes in its own domain.
    assert hero_learner in new_first_domain_learner.known_nodes
    assert other_first_domain_learner in new_first_domain_learner.known_nodes
    assert _nobody in new_first_domain_learner.known_nodes


def test_learner_restores_metadata_from_storage(lonely_ursula_maker, tmpdir):
    # Create a local file-based node storage
    root = tmpdir.mkdir("known_nodes")
    metadata = root.mkdir("metadata")
    certs = root.mkdir("certs")
    old_storage = LocalFileBasedNodeStorage(metadata_dir=Path(metadata),
                                            certificates_dir=Path(certs),
                                            storage_root=Path(root))

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
    buddy._Learner__known_nodes = FleetSensor(domain="fistro")

    # The learner shouldn't learn about any node from the first domain, since it's different.
    learner.learn_from_teacher_node()
    for restored_node in learner.known_nodes:
        assert restored_node.mature().domain == learner.domain

    # In fact, since the storage only contains nodes from a different domain,
    # the learner should only know its buddy from the second domain.
    assert set(learner.known_nodes) == {buddy}


def test_learner_ignores_stored_nodes_from_other_domains(
    lonely_ursula_maker, tmpdir, testerchain, ursula_test_config
):
    learner, other_staker = make_ursulas(
        ursula_test_config,
        domain="call-it-mainnet",
        quantity=2,
        know_each_other=True,
        staking_provider_addresses=testerchain.stake_providers_accounts[:2],
        operator_addresses=testerchain.ursulas_accounts[:2],
   )

    pest, *other_ursulas_from_the_wrong_side_of_the_tracks = make_ursulas(
        ursula_test_config,
        domain="i-dunno-testt-maybe",
        quantity=5,
        know_each_other=True,
        staking_provider_addresses=testerchain.stake_providers_accounts[2:],
        operator_addresses=testerchain.ursulas_accounts[2:],
    )

    assert pest not in other_staker.known_nodes
    assert pest not in learner.known_nodes
    pest._current_teacher_node = learner
    pest.learn_from_teacher_node()
    assert pest not in other_staker.known_nodes

    ##################################
    # Prior to #2423, learner remembered pest because POSTed node metadata was not domain-checked.
    # This is how ibex nodes initially made their way into mainnet fleet states.
    assert pest not in learner.known_nodes  # But not anymore.

    # Once pest made its way into learner, learner taught passed it to other mainnet nodes.
    assert pest not in learner.known_nodes  # But not anymore.

    learner.known_nodes.record_node(pest)  # This used to happen anyway.

    other_staker._current_teacher_node = learner
    other_staker.learn_from_teacher_node()  # And once it did, the node from the wrong domain spread.
    assert pest not in other_staker.known_nodes  # But not anymore.


def test_learner_with_empty_storage_uses_fallback_nodes(lonely_ursula_maker, mocker):
    domain = "learner-domain"
    mocker.patch.dict(TEACHER_NODES, {domain: ("teacher-uri",)}, clear=True)

    # Create a learner and a teacher
    learner, teacher = lonely_ursula_maker(domain=domain, quantity=2, save_metadata=False)
    mocker.patch.object(Ursula, 'from_teacher_uri', return_value=teacher)

    # Since there are no nodes in local node storage, the learner should only learn about the teacher
    learner.learn_from_teacher_node()
    assert set(learner.known_nodes) == {teacher}


def test_learner_uses_both_nodes_from_storage_and_fallback_nodes(
    lonely_ursula_maker, tmpdir, mocker, test_registry, ursula_test_config, testerchain
):
    domain = "learner-domain"
    mocker.patch.dict(TEACHER_NODES, {domain: ("teacher-uri",)}, clear=True)

    # Create a local file-based node storage
    root = tmpdir.mkdir("known_nodes")
    metadata = root.mkdir("metadata")
    certs = root.mkdir("certs")
    node_storage = LocalFileBasedNodeStorage(metadata_dir=Path(metadata),
                                             certificates_dir=Path(certs),
                                             storage_root=Path(root))

    # Create some nodes and persist them to local storage
    other_nodes = make_ursulas(
        ursula_test_config,
        domain=domain,
        node_storage=node_storage,
        know_each_other=True,
        quantity=3,
        save_metadata=True,
        staking_provider_addresses=testerchain.stake_providers_accounts[:3],
        operator_addresses=testerchain.ursulas_accounts[:3],
    )

    # Create a teacher and a learner using existing node storage
    learner, teacher = lonely_ursula_maker(
        domain=domain,
        node_storage=node_storage,
        quantity=2,
        know_each_other=True,
        staking_provider_addresses=testerchain.stake_providers_accounts[3:],
        operator_addresses=testerchain.ursulas_accounts[3:],
    )
    mocker.patch.object(Ursula, 'from_teacher_uri', return_value=teacher)

    # The learner should learn about all nodes
    learner.learn_from_teacher_node()
    all_nodes = {teacher}
    all_nodes.update(other_nodes)
    assert set(learner.known_nodes) == all_nodes
