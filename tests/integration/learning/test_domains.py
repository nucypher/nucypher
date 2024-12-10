import pytest

import tests
from nucypher.blockchain.eth.domains import TACoDomain
from nucypher.blockchain.eth.registry import ContractRegistry
from tests.constants import TEMPORARY_DOMAIN, TESTERCHAIN_CHAIN_INFO
from tests.utils.registry import MockRegistrySource


@pytest.fixture(scope="module")
def domain_1():
    return TACoDomain(
        name="domain_uno",
        eth_chain=TESTERCHAIN_CHAIN_INFO,
        polygon_chain=TESTERCHAIN_CHAIN_INFO,
    )


@pytest.fixture(scope="module")
def domain_2():
    return TACoDomain(
        name="domain_dos",
        eth_chain=TESTERCHAIN_CHAIN_INFO,
        polygon_chain=TESTERCHAIN_CHAIN_INFO,
    )


@pytest.fixture(scope="module")
def test_registry(module_mocker, domain_1, domain_2):
    with tests.utils.registry.mock_registry_sources(
        mocker=module_mocker, _domains=[domain_1, domain_2, TEMPORARY_DOMAIN]
    ):
        # doesn't really matter what domain is used here
        registry = ContractRegistry(MockRegistrySource(domain=domain_1))
        yield registry


@pytest.fixture(scope="module")
def registry_1(domain_1, test_registry):
    return ContractRegistry(MockRegistrySource(domain=domain_1))


@pytest.fixture(scope="module")
def registry_2(domain_2, test_registry):
    return ContractRegistry(MockRegistrySource(domain=domain_2))


@pytest.mark.skip("inconsistent behaviour on CI - see #3289")
def test_learner_learns_about_domains_separately(
    lonely_ursula_maker, domain_1, domain_2, registry_1, registry_2, caplog
):
    hero_learner, other_first_domain_learner = lonely_ursula_maker(
        domain=domain_1,
        registry=registry_1,
        quantity=2,
    )
    _nobody = lonely_ursula_maker(
        domain=domain_1, registry=registry_1, quantity=1
    ).pop()
    other_first_domain_learner.remember_node(_nobody, eager=True)

    second_domain_learners = lonely_ursula_maker(
        domain=domain_2, registry=registry_2, know_each_other=True, quantity=3
    )

    assert len(hero_learner.known_nodes) == 0

    # Learn from a teacher in our domain.
    hero_learner.remember_node(other_first_domain_learner, eager=True)
    hero_learner.start_learning_loop(now=True)
    hero_learner.learn_from_teacher_node(eager=True)

    # All domain 1 nodes
    assert len(hero_learner.known_nodes) == 2

    # Learn about the second domain.
    hero_learner._current_teacher_node = second_domain_learners.pop()
    hero_learner.learn_from_teacher_node(eager=True)

    # All domain 1 nodes
    assert len(hero_learner.known_nodes) == 2

    new_first_domain_learner = lonely_ursula_maker(
        domain=domain_1, registry=registry_1, quantity=1
    ).pop()
    _new_second_domain_learner = lonely_ursula_maker(
        domain=domain_2, registry=registry_2, quantity=1
    ).pop()

    new_first_domain_learner.remember_node(hero_learner, eager=True)

    new_first_domain_learner.learn_from_teacher_node(eager=True)

    # This node, in the first domain, didn't learn about the second domain.
    assert not set(second_domain_learners).intersection(new_first_domain_learner.known_nodes)

    # However, it learned about *all* of the nodes in its own domain.
    assert hero_learner in new_first_domain_learner.known_nodes
    assert other_first_domain_learner in new_first_domain_learner.known_nodes
    assert _nobody in new_first_domain_learner.known_nodes
