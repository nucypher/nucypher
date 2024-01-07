import pytest

import tests
from nucypher.blockchain.eth.domains import TACoDomain
from nucypher.blockchain.eth.registry import ContractRegistry
from nucypher.characters.lawful import Ursula
from nucypher.network.nodes import TEACHER_NODES
from tests.constants import TEMPORARY_DOMAIN, TESTERCHAIN_CHAIN_INFO
from tests.utils.blockchain import ReservedTestAccountManager
from tests.utils.registry import MockRegistrySource
from tests.utils.ursula import make_ursulas


@pytest.fixture(scope="module")
def domain_1():
    return TACoDomain(
        name="domain_uno",
        eth_chain=TESTERCHAIN_CHAIN_INFO,
        polygon_chain=TESTERCHAIN_CHAIN_INFO,
        condition_chains=(TESTERCHAIN_CHAIN_INFO,),
    )


@pytest.fixture(scope="module")
def domain_2():
    return TACoDomain(
        name="domain_dos",
        eth_chain=TESTERCHAIN_CHAIN_INFO,
        polygon_chain=TESTERCHAIN_CHAIN_INFO,
        condition_chains=(TESTERCHAIN_CHAIN_INFO,),
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


def test_learner_learns_about_domains_separately(
    lonely_ursula_maker, domain_1, domain_2, registry_1, registry_2, caplog, accounts
):
    hero_learner, other_first_domain_learner = lonely_ursula_maker(
        accounts=accounts,
        domain=domain_1,
        registry=registry_1,
        quantity=2,
    )
    _nobody = lonely_ursula_maker(
        accounts=accounts,
        domain=domain_1,
        registry=registry_1,
        quantity=1,
        account_start_index=2
    ).pop()
    other_first_domain_learner.remember_peer(_nobody, eager=True)

    second_domain_learners = lonely_ursula_maker(
        accounts=accounts,
        domain=domain_2,
        registry=registry_2,
        know_each_other=True,
        quantity=3,
        account_start_index=3
    )

    assert len(hero_learner.peers) == 0

    # Learn from a peer in our domain.
    hero_learner.remember_peer(other_first_domain_learner, eager=True)
    hero_learner.start_peering(now=True)
    hero_learner.learn_from_peer(eager=True)

    # All domain 1 nodes
    assert len(hero_learner.peers) == 2

    # Learn about the second domain.
    hero_learner._current_peer = second_domain_learners.pop()
    hero_learner.learn_from_peer(eager=True)

    # All domain 1 nodes
    assert len(hero_learner.peers) == 2

    new_first_domain_learner = lonely_ursula_maker(
        accounts=accounts,
        domain=domain_1,
        registry=registry_1,
        quantity=1,
        account_start_index=6
    ).pop()
    _new_second_domain_learner = lonely_ursula_maker(
        accounts=accounts,
        domain=domain_2,
        registry=registry_2,
        quantity=1,
        account_start_index=7
    ).pop()

    new_first_domain_learner.remember_peer(hero_learner, eager=True)

    new_first_domain_learner.learn_from_peer(eager=True)

    # This node, in the first domain, didn't learn about the second domain.
    assert not set(second_domain_learners).intersection(new_first_domain_learner.peers)

    # However, it learned about *all* of the nodes in its own domain.
    assert hero_learner in new_first_domain_learner.peers
    assert other_first_domain_learner in new_first_domain_learner.peers
    assert _nobody in new_first_domain_learner.peers


def test_learner_uses_both_seed_nodes_and_fallback_sage_nodes(
    lonely_ursula_maker,
    domain_1,
    registry_1,
    tmpdir,
    mocker,
    test_registry,
    ursula_test_config,
    testerchain,
    accounts
):
    mocker.patch.dict(TEACHER_NODES, {domain_1: ("peer-uri",)}, clear=True)

    # Create some nodes and persist them to local storage
    other_nodes = make_ursulas(
        ursula_config=ursula_test_config,
        accounts=accounts,
        domain=domain_1,
        registry=registry_1,
        know_each_other=True,
        quantity=3,
        account_start_index=0,
    )

    # Create a peer and a learner using existing node storage
    learner, peer = lonely_ursula_maker(
        accounts=accounts,
        domain=domain_1,
        registry=registry_1,
        seed_nodes=other_nodes,
        quantity=2,
        account_start_index=4,
    )
    mocker.patch.object(Ursula, 'from_peer_uri', return_value=peer)

    # The learner should learn about all nodes
    learner.learn_from_peer()
    all_nodes = {peer}
    all_nodes.update(other_nodes)
    assert set(learner.peers) == all_nodes
